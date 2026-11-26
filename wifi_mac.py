"""macOS CoreWLAN 스캐너 (PyObjC 필요: pip install pyobjc-framework-CoreWLAN).

CWNetwork.informationElementData 로 비콘/프로브 응답의 IE 원본을 받아 Windows와 같은 공통 파서로 해석한다.
macOS 14(Sonoma)부터는 앱에 '위치 서비스' 권한이 없으면 SSID/BSSID가 비어서(nil) 온다.
"""
import threading

from wifi_scan import WlanError, build_network, channel_to_freq, quality_from_rssi

try:
    from CoreWLAN import CWWiFiClient
except ImportError as ex:  # pragma: no cover - 맥 이외 환경
    raise ImportError("macOS에서 pyobjc-framework-CoreWLAN 패키지가 필요합니다: "
                      "pip install pyobjc-framework-CoreWLAN pyobjc-framework-CoreLocation") from ex

# CWChannelBand: 1=2.4GHz, 2=5GHz, 3=6GHz
_BAND = {1: "2.4", 2: "5", 3: "6"}
_K_CW_SECURITY_WEP = 1

LOCATION_HELP = ("macOS가 주변 AP의 SSID/BSSID를 숨기고 있습니다. 시스템 설정 > 개인정보 보호 및 보안 > 위치 서비스에서 "
                 "'위치 서비스'를 켜고 WiFiScanner(또는 실행한 터미널/Python)를 허용한 뒤 앱을 다시 실행하세요.")


def _norm_mac(s):
    """CoreWLAN BSSID 문자열을 aa:bb:cc:dd:ee:ff 형식으로 맞춘다."""
    parts = str(s).strip().lower().replace("-", ":").split(":")
    if len(parts) != 6:
        return None
    try:
        return ":".join(f"{int(p, 16):02x}" for p in parts)
    except ValueError:
        return None


class WlanClient:
    """Windows 스캐너와 같은 인터페이스: interfaces / scan / bss_list / current_connection / close."""

    def __init__(self):
        self._client = CWWiFiClient.sharedWiFiClient()
        self._lock = threading.Lock()
        self._cache = []
        self._error = None

    def close(self):
        pass

    def _iface(self):
        itf = self._client.interface()
        if itf is None:
            raise WlanError("Wi-Fi 인터페이스를 찾을 수 없습니다. Wi-Fi가 켜져 있는지 확인하세요.")
        return itf

    def interfaces(self):
        itf = self._iface()
        name = str(itf.interfaceName() or "en0")
        return [{"guid": name, "description": f"Wi-Fi ({name})", "state": 1 if itf.powerOn() else 0}]

    def scan(self, guid):
        """동기 스캔(수 초 소요). 결과는 bss_list()가 돌려준다."""
        itf = self._iface()
        if not itf.powerOn():
            self._error = WlanError("Wi-Fi가 꺼져 있습니다. 메뉴 막대에서 Wi-Fi를 켜세요.")
            return
        try:
            nets, err = itf.scanForNetworksWithName_includeHidden_error_(None, True, None)
        except AttributeError:  # 구버전 macOS
            nets, err = itf.scanForNetworksWithName_error_(None, None)
        if nets is None:
            # 너무 잦은 스캔은 macOS가 거절할 수 있다 → 직전 결과 유지
            self._error = None if self._cache else WlanError(f"스캔 실패: {err}")
            return

        out, hidden_bssid = [], 0
        for n in nets:
            bssid = _norm_mac(n.bssid()) if n.bssid() else None
            if not bssid:
                hidden_bssid += 1
                continue
            ch = n.wlanChannel()
            band = _BAND.get(int(ch.channelBand()), "?") if ch is not None else "?"
            freq = channel_to_freq(band, int(ch.channelNumber())) if ch is not None else 0
            data = n.informationElementData()
            ies = bytes(data) if data is not None else b""
            rssi = int(n.rssiValue())
            cap = 0x0010 if n.supportsSecurity_(_K_CW_SECURITY_WEP) else 0
            out.append(build_network(
                ssid=str(n.ssid() or ""), bssid=bssid, rssi=rssi, quality=quality_from_rssi(rssi),
                freq_mhz=freq, beacon=int(n.beaconInterval()), cap_info=cap, ies_raw=ies))

        with self._lock:
            if out:
                self._cache, self._error = out, None
            elif hidden_bssid:
                self._cache, self._error = [], WlanError(LOCATION_HELP)
            else:
                self._cache, self._error = [], None

    def bss_list(self, guid):
        with self._lock:
            if self._error is not None and not self._cache:
                raise self._error
            return list(self._cache)

    def current_connection(self, guid):
        itf = self._iface()
        ssid, bssid = itf.ssid(), itf.bssid()
        if not ssid and not bssid:
            return None
        rate = float(itf.transmitRate() or 0)
        return {"ssid": str(ssid or ""), "bssid": _norm_mac(bssid) if bssid else "",
                "quality": quality_from_rssi(itf.rssiValue()), "rx_mbps": rate, "tx_mbps": rate}
