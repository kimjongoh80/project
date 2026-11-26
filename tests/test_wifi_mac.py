"""wifi_mac(macOS CoreWLAN) 스캔 결과 변환 테스트.

CoreWLAN(PyObjC)을 가짜 모듈로 바꿔 맥이 아니어도 돌아간다. 위치 서비스 권한이 없어
SSID/BSSID가 nil로 오는 macOS 14+ 동작도 흉내낸다.
"""
import importlib
import sys
import types

import pytest

import ie_builder as b
from wifi_scan import WlanError

BAND_24, BAND_5, BAND_6 = 1, 2, 3
WEP = 1


class FakeChannel:
    def __init__(self, number, band):
        self._n, self._b = number, band

    def channelNumber(self):
        return self._n

    def channelBand(self):
        return self._b


class FakeNetwork:
    def __init__(self, ssid, bssid, rssi, channel, band, ies=b"", wep=False, beacon=100):
        self._ssid, self._bssid, self._rssi = ssid, bssid, rssi
        self._ch = FakeChannel(channel, band) if channel else None
        self._ies, self._wep, self._beacon = ies, wep, beacon

    def ssid(self):
        return self._ssid

    def bssid(self):
        return self._bssid

    def rssiValue(self):
        return self._rssi

    def wlanChannel(self):
        return self._ch

    def informationElementData(self):
        return self._ies

    def supportsSecurity_(self, mode):
        return self._wep and mode == WEP

    def beaconInterval(self):
        return self._beacon


class FakeInterface:
    def __init__(self, networks=(), power=True, ssid=None, bssid=None, rssi=-50, rate=0.0):
        self.networks = networks
        self.power = power
        self._ssid, self._bssid, self._rssi, self._rate = ssid, bssid, rssi, rate

    def interfaceName(self):
        return "en0"

    def powerOn(self):
        return self.power

    def scanForNetworksWithName_includeHidden_error_(self, name, hidden, err):
        if self.networks is None:
            return None, "Busy"
        return list(self.networks), None

    def ssid(self):
        return self._ssid

    def bssid(self):
        return self._bssid

    def rssiValue(self):
        return self._rssi

    def transmitRate(self):
        return self._rate


class FakeClient:
    iface = None

    @classmethod
    def sharedWiFiClient(cls):
        return cls()

    def interface(self):
        return FakeClient.iface


@pytest.fixture
def mac(monkeypatch):
    fake = types.ModuleType("CoreWLAN")
    fake.CWWiFiClient = FakeClient
    monkeypatch.setitem(sys.modules, "CoreWLAN", fake)
    monkeypatch.delitem(sys.modules, "wifi_mac", raising=False)
    mod = importlib.import_module("wifi_mac")
    yield mod
    sys.modules.pop("wifi_mac", None)
    FakeClient.iface = None


def scan(mac, networks, **kw):
    FakeClient.iface = FakeInterface(networks, **kw)
    c = mac.WlanClient()
    c.scan("en0")
    return c


@pytest.mark.parametrize("raw, expected", [
    ("AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"),
    ("a:b:c:d:e:f", "0a:0b:0c:0d:0e:0f"),
    ("00-11-22-33-44-55", "00:11:22:33:44:55"),
    ("", None), ("zz:11:22:33:44:55", None), ("00:11:22", None),
])
def test_norm_mac(mac, raw, expected):
    assert mac._norm_mac(raw) == expected


def test_scan_maps_fields(mac):
    ies = b.ssid("Office") + b.ht_cap(2) + b.ht_op(36, 1, True) + b.vht_cap(2) + b.vht_op(1, 42) + b.rsn([2, 8], rsn_cap=0x80)
    c = scan(mac, [
        FakeNetwork("Office", "A0:B1:C2:D3:E4:F5", -48, 36, BAND_5, ies),
        FakeNetwork("카페_무료와이파이", "a0:b1:c2:d3:e4:01", -71, 6, BAND_24, b.ds(6)),
    ])
    nets = {n["ssid"]: n for n in c.bss_list("en0")}

    office = nets["Office"]
    assert office["bssid"] == "a0:b1:c2:d3:e4:f5"
    assert (office["band"], office["channel"], office["freq"]) == ("5", 36, 5180)
    assert office["rssi"] == -48 and office["quality"] == 100
    assert office["width"] == 80
    assert office["security"] == "WPA2/WPA3-Personal"

    cafe = nets["카페_무료와이파이"]
    assert (cafe["band"], cafe["channel"], cafe["freq"]) == ("2.4", 6, 2437)
    assert cafe["quality"] == 58
    assert cafe["security"] == "Open"


def test_scan_6ghz_channel(mac):
    c = scan(mac, [FakeNetwork("Six", "00:00:00:00:00:06", -60, 37, BAND_6, b.he_cap() + b.he_op_6ghz(37, 2, 39))])
    n = c.bss_list("en0")[0]
    assert (n["band"], n["channel"], n["freq"], n["generation"]) == ("6", 37, 6135, "Wi-Fi 6E")


def test_scan_wep_from_supports_security(mac):
    c = scan(mac, [FakeNetwork("Old", "00:00:00:00:00:01", -60, 1, BAND_24, wep=True)])
    assert c.bss_list("en0")[0]["security"] == "WEP"


def test_scan_hidden_ssid_kept_with_bssid(mac):
    c = scan(mac, [FakeNetwork(None, "00:00:00:00:00:02", -60, 11, BAND_24)])
    n = c.bss_list("en0")[0]
    assert n["ssid"] == "" and n["bssid"] == "00:00:00:00:00:02"


def test_scan_missing_ie_data_and_channel(mac):
    c = scan(mac, [FakeNetwork("NoIE", "00:00:00:00:00:03", -80, None, BAND_24, ies=None)])
    n = c.bss_list("en0")[0]
    assert n["band"] == "?" and n["freq"] == 0
    assert n["security"] == "Open"


def test_scan_location_denied_hides_all(mac):
    """위치 권한 없음: SSID/BSSID가 모두 nil → 안내 메시지로 오류."""
    c = scan(mac, [FakeNetwork(None, None, -50, 1, BAND_24), FakeNetwork(None, None, -60, 36, BAND_5)])
    with pytest.raises(WlanError) as ei:
        c.bss_list("en0")
    assert "위치 서비스" in str(ei.value)


def test_scan_partial_hidden_bssid_returns_visible(mac):
    c = scan(mac, [FakeNetwork(None, None, -50, 1, BAND_24), FakeNetwork("Vis", "00:00:00:00:00:04", -60, 1, BAND_24)])
    assert [n["ssid"] for n in c.bss_list("en0")] == ["Vis"]


def test_scan_empty_result(mac):
    assert scan(mac, []).bss_list("en0") == []


def test_scan_wifi_off(mac):
    c = scan(mac, [], power=False)
    with pytest.raises(WlanError, match="꺼져"):
        c.bss_list("en0")


def test_scan_failure_keeps_previous_cache(mac):
    c = scan(mac, [FakeNetwork("Keep", "00:00:00:00:00:05", -60, 1, BAND_24)])
    FakeClient.iface.networks = None
    c.scan("en0")
    assert [n["ssid"] for n in c.bss_list("en0")] == ["Keep"]


def test_scan_failure_without_cache_raises(mac):
    c = scan(mac, None)
    with pytest.raises(WlanError, match="스캔 실패"):
        c.bss_list("en0")


def test_no_interface(mac):
    FakeClient.iface = None
    with pytest.raises(WlanError):
        mac.WlanClient().interfaces()


def test_current_connection(mac):
    FakeClient.iface = FakeInterface([], ssid="Home", bssid="AA:BB:CC:00:11:22", rssi=-65, rate=866.0)
    cc = mac.WlanClient().current_connection("en0")
    assert cc == {"ssid": "Home", "bssid": "aa:bb:cc:00:11:22", "quality": 70, "rx_mbps": 866.0, "tx_mbps": 866.0}


def test_current_connection_location_denied(mac):
    FakeClient.iface = FakeInterface([], ssid=None, bssid=None)
    assert mac.WlanClient().current_connection("en0") is None
