"""WI-FI SCANNER - 백그라운드 스캔 + 로컬 웹 UI 서버.

실행:  python server.py            (브라우저 자동 열림)
옵션:  --port 8765 --interval 5 --no-browser
"""
import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from collections import deque
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

import vendor
from wlan import WlanClient, WlanError

# PyInstaller로 묶인 exe에서는 리소스가 임시 폴더(sys._MEIPASS)에 풀린다
HERE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
STATIC = os.path.join(HERE, "static")
HISTORY_SECONDS = 600       # 시간 그래프 보관 길이
FORGET_SECONDS = 180        # 이 시간 동안 안 보이면 목록에서 제거
# 사용자 설정(열 순서·너비 등). 앱은 실행마다 포트가 바뀌어 localStorage가 유지되지 않으므로 파일에 저장
if sys.platform == "darwin":
    _SETTINGS_DIR = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "WiFiScanner")
else:
    _SETTINGS_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "WiFiScanner")
SETTINGS_PATH = os.path.join(_SETTINGS_DIR, "settings.json")
_settings_lock = threading.Lock()


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    with _settings_lock:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)


class Scanner(threading.Thread):
    def __init__(self, interval):
        super().__init__(daemon=True)
        self.interval = interval
        self.lock = threading.Lock()
        self.networks = {}          # bssid -> dict
        self.history = {}           # bssid -> deque[(t, rssi|None)]
        self.interface = None
        self.connected = None
        self.error = None
        self.scan_count = 0
        self.updated = None

    def run(self):
        client = None
        while True:
            try:
                if client is None:
                    client = WlanClient()
                itfs = client.interfaces()
                if not itfs:
                    raise RuntimeError("무선 랜 어댑터를 찾을 수 없습니다.")
                itf = itfs[0]
                try:
                    client.scan(itf["guid"])
                except WlanError:
                    pass  # 스캔 요청이 거절돼도 캐시된 목록은 읽을 수 있음
                time.sleep(self.interval)
                nets = client.bss_list(itf["guid"])
                conn = client.current_connection(itf["guid"])
                self._update(itf["description"], nets, conn)
            except Exception as ex:  # noqa: BLE001
                with self.lock:
                    self.error = str(ex)
                if client:
                    client.close()
                client = None
                time.sleep(self.interval)

    def _update(self, desc, nets, conn):
        now = time.time()
        with self.lock:
            self.interface, self.connected, self.error = desc, conn, None
            self.scan_count += 1
            self.updated = now
            seen = set()
            for n in nets:
                b = n["bssid"]
                seen.add(b)
                prev = self.networks.get(b)
                n["first_seen"] = prev["first_seen"] if prev else now
                # 장치 정보(AP 이름·모델·WPS)는 비콘/프로브 응답마다 빠질 수 있으므로 이전에 본 값을 유지
                if prev:
                    for key in ("ap_name", "model", "wps", "dtim"):
                        if not n.get(key) and prev.get(key):
                            n[key] = prev[key]
                n["last_seen"] = now
                self.networks[b] = n
                self.history.setdefault(b, deque()).append((now, n["rssi"]))
            for b, n in list(self.networks.items()):
                if b not in seen:
                    self.history[b].append((now, None))
                    if now - n["last_seen"] > FORGET_SECONDS:
                        del self.networks[b]
                        del self.history[b]
                        continue
                h = self.history[b]
                while h and now - h[0][0] > HISTORY_SECONDS:
                    h.popleft()

    def snapshot(self):
        with self.lock:
            now = time.time()
            conn_bssid = self.connected["bssid"] if self.connected else None
            nets = []
            for b, n in self.networks.items():
                d = dict(n)
                d["age"] = round(now - n["last_seen"], 1)
                d["connected"] = b == conn_bssid
                d["history"] = [[round(t - now, 1), r] for t, r in self.history.get(b, ())]
                nets.append(d)
            vendor.annotate(nets)
            return {"interface": self.interface, "connected": self.connected,
                    "error": self.error, "scan_count": self.scan_count,
                    "interval": self.interval, "history_seconds": HISTORY_SECONDS,
                    "networks": nets}


def make_handler(scanner):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=STATIC, **kw)

        def end_headers(self):
            # 화면 파일(html/js/css)은 항상 최신본을 확인하게 해서, 업데이트 후 옛 화면이 캐시로 남지 않게 함
            if not self.path.startswith("/api/"):
                self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.startswith("/api/state"):
                return self._json(scanner.snapshot())
            if self.path.startswith("/api/settings"):
                return self._json(load_settings())
            super().do_GET()

        def do_POST(self):
            if not self.path.startswith("/api/settings"):
                return self._json({"error": "not found"}, 404)
            # application/json 요구 → 다른 웹사이트가 보내는 단순 폼 POST(CSRF) 차단
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                return self._json({"error": "json required"}, 415)
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > 64 * 1024:
                return self._json({"error": "bad size"}, 400)
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except ValueError:
                return self._json({"error": "bad json"}, 400)
            if not isinstance(data, dict):
                return self._json({"error": "object required"}, 400)
            merged = load_settings()
            merged.update(data)
            save_settings(merged)
            return self._json({"ok": True})

        def log_message(self, *a):
            pass
    return Handler


def start_server(port=0, interval=5.0):
    """스캐너와 HTTP 서버를 백그라운드로 시작하고 (httpd, url)을 돌려준다. port=0이면 빈 포트 자동 선택."""
    scanner = Scanner(interval)
    scanner.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(scanner))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}/"


def main():
    ap = argparse.ArgumentParser(description="WI-FI SCANNER")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--interval", type=float, default=5.0, help="스캔 주기(초)")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    scanner = Scanner(args.interval)
    scanner.start()
    httpd = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(scanner))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"WI-FI SCANNER 실행 중: {url}  (종료: Ctrl+C)")
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
