"""WI-FI SCANNER - 데스크톱 앱 진입점 (Windows / macOS).

내부에서 스캐너 + 로컬 서버(빈 포트 자동 선택)를 띄우고,
OS 내장 웹 엔진 창(Windows: WebView2, macOS: WKWebView) 안에 UI를 표시한다. 브라우저는 열리지 않는다.

실행:  python app.py   (macOS: python3 app.py)
빌드:  Windows build.bat → dist\\WiFiScanner.exe   /   macOS build_mac.sh → dist/WiFiScanner.app
"""
import os
import subprocess
import sys

import webview

from server import load_settings, start_server


def system_prefers_light():
    """OS가 라이트 모드인지. Windows: 앱 모드 레지스트리, macOS: AppleInterfaceStyle(다크일 때만 'Dark')."""
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
                return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 1
        except OSError:
            return False
    if sys.platform == "darwin":
        try:
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                               capture_output=True, text=True, timeout=3)
            return "dark" not in r.stdout.lower()
        except (OSError, subprocess.SubprocessError):
            return True
    return False


def window_background():
    """창이 뜰 때 화면이 로드되기 전 잠깐 보이는 바탕색을 테마에 맞춘다."""
    theme = load_settings().get("theme", "system")
    light = theme == "light" or (theme not in ("light", "dark") and system_prefers_light())
    return "#f3f5f8" if light else "#0e1217"


_location_manager = None   # 참조를 유지해야 권한 요청이 사라지지 않음


def request_mac_location_permission():
    """macOS 14+는 위치 권한이 없으면 주변 AP의 SSID/BSSID를 숨긴다 → 앱 시작 시 권한 요청."""
    global _location_manager
    if sys.platform != "darwin":
        return
    try:
        from CoreLocation import CLLocationManager
    except ImportError:
        return
    m = CLLocationManager.alloc().init()
    if hasattr(m, "requestWhenInUseAuthorization"):
        m.requestWhenInUseAuthorization()
    else:  # 구버전 macOS: 위치 업데이트를 시작하면 권한 창이 뜸
        m.startUpdatingLocation()
        m.stopUpdatingLocation()
    _location_manager = m


class Api:
    """JS에서 window.pywebview.api.* 로 호출되는 함수들."""

    def save_csv(self, content, filename):
        win = webview.windows[0]
        try:
            kind = webview.FileDialog.SAVE
        except AttributeError:  # 구버전 pywebview
            kind = webview.SAVE_DIALOG
        result = win.create_file_dialog(
            kind,
            directory=os.path.join(os.path.expanduser("~"), "Documents"),
            save_filename=filename,
            file_types=("CSV 파일 (*.csv)", "모든 파일 (*.*)"),
        )
        if not result:
            return None
        path = result if isinstance(result, str) else result[0]
        if not path.lower().endswith(".csv"):
            path += ".csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:  # BOM: 엑셀 한글 깨짐 방지
            f.write(content)
        return path


def main():
    interval = 5.0
    if "--interval" in sys.argv:
        interval = float(sys.argv[sys.argv.index("--interval") + 1])
    request_mac_location_permission()
    _, url = start_server(port=0, interval=interval)
    webview.create_window(
        "WI-FI SCANNER",
        url,
        js_api=Api(),
        width=1360,
        height=880,
        min_size=(960, 640),
        background_color=window_background(),
        text_select=True,
    )
    webview.start()  # 창을 닫으면 반환되고, 데몬 스레드(스캐너/서버)도 함께 종료된다


if __name__ == "__main__":
    main()
