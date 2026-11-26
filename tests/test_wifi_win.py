"""wifi_win(Windows wlanapi.dll) BSS 목록 변환 테스트.

wlanapi.dll을 가짜로 바꾸고 WLAN_BSS_LIST를 메모리에 직접 만들어 넘긴다. 리눅스/맥에서도 돌도록
Windows의 32비트 DWORD/ULONG/LONG/BOOL 크기를 맞춰 준다(구조체 크기 360바이트 검사 통과용).
"""
import ctypes
import importlib
import sys
from ctypes import wintypes

import pytest

import ie_builder as b
from wifi_scan import WlanError

ENTRY_SIZE = 360
HEADER_SIZE = 8


class FakeFunc:
    def __init__(self, impl=None):
        self.impl = impl or (lambda *a: 0)

    def __call__(self, *args):
        return self.impl(*args)


class FakeDLL:
    def __init__(self):
        self.funcs = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self.funcs.setdefault(name, FakeFunc())


@pytest.fixture
def win(monkeypatch):
    dll = FakeDLL()
    monkeypatch.setattr(ctypes, "WinDLL", lambda name: dll, raising=False)
    if sys.platform != "win32":
        for name, t in (("DWORD", ctypes.c_uint32), ("ULONG", ctypes.c_uint32),
                        ("LONG", ctypes.c_int32), ("BOOL", ctypes.c_int32)):
            monkeypatch.setattr(wintypes, name, t)
    monkeypatch.delitem(sys.modules, "wifi_win", raising=False)
    mod = importlib.import_module("wifi_win")
    mod._fake_dll = dll
    yield mod
    sys.modules.pop("wifi_win", None)


def make_entry(mod, ssid=b"", bssid=(0, 0, 0, 0, 0, 0), rssi=-50, quality=100, freq_khz=2437000,
               cap=0, beacon=100, rates=()):
    e = mod.WLAN_BSS_ENTRY()
    e.dot11Ssid.uSSIDLength = len(ssid)
    e.dot11Ssid.ucSSID[:len(ssid)] = list(ssid)
    e.dot11Bssid[:] = list(bssid)
    e.lRssi, e.uLinkQuality = rssi, quality
    e.ulChCenterFrequency = freq_khz
    e.usCapabilityInformation, e.usBeaconPeriod = cap, beacon
    e.wlanRateSet.uRateSetLength = 2 * len(rates)
    e.wlanRateSet.usRateSet[:len(rates)] = list(rates)
    return e


def install_bss_list(mod, entries_with_ies):
    """WlanGetNetworkBssList가 돌려줄 메모리 블록(헤더 + 엔트리 + IE 원본)을 만든다."""
    n = len(entries_with_ies)
    ie_base = HEADER_SIZE + n * ENTRY_SIZE
    blob = bytearray(ie_base)
    blob[0:4] = len(blob).to_bytes(4, "little")
    blob[4:8] = n.to_bytes(4, "little")
    pos = ie_base
    for i, (e, ies) in enumerate(entries_with_ies):
        start = HEADER_SIZE + i * ENTRY_SIZE
        e.ulIeOffset, e.ulIeSize = pos - start, len(ies)
        blob[start:start + ENTRY_SIZE] = bytes(e)
        blob += ies
        pos += len(ies)
    size = max(len(blob), ctypes.sizeof(mod.WLAN_BSS_LIST))  # 항목 0개여도 구조체 크기만큼은 필요
    buf = ctypes.create_string_buffer(bytes(blob), size)

    def get_list(handle, guid, profile, flags, sec, reserved, out):
        out._obj.contents = mod.WLAN_BSS_LIST.from_buffer(buf)
        return 0

    mod._fake_dll.funcs["WlanGetNetworkBssList"] = FakeFunc(get_list)
    mod._keepalive = buf


def test_struct_size(win):
    assert ctypes.sizeof(win.WLAN_BSS_ENTRY) == ENTRY_SIZE


def test_ssid_decoding(win):
    mk = lambda raw: win.DOT11_SSID(len(raw), (ctypes.c_ubyte * 32)(*raw))
    assert win._ssid(mk(b"Office")) == "Office"
    assert win._ssid(mk("우리집".encode())) == "우리집"
    assert win._ssid(mk(b"")) == ""
    assert win._ssid(mk(b"\x00\x00\x00\x00")) == ""      # 숨김 SSID(널 채움)
    assert win._ssid(mk(b"\xff\xfeAP")) == "��AP"  # 깨진 바이트는 대체 문자


def test_mac_format(win):
    assert win._mac((ctypes.c_ubyte * 6)(0, 0x1A, 0x2B, 0xC, 0xD, 0xFF)) == "00:1a:2b:0c:0d:ff"


def test_bss_list_maps_fields(win):
    ies_a = b.ssid("Office") + b.ht_cap(2) + b.ht_op(36, 1, True) + b.vht_cap(2) + b.vht_op(1, 42) + b.rsn([2], rsn_cap=0)
    ies_b = b.ssid("카페") + b.ds(11) + b.rates(0x82, 0x84, 0x8B, 0x96)
    install_bss_list(win, [
        (make_entry(win, b"Office", (0xA0, 0xB1, 0xC2, 0xD3, 0xE4, 0xF5), -45, 100, 5180000, cap=0x11), ies_a),
        (make_entry(win, "카페".encode(), (0, 0x11, 0x22, 0x33, 0x44, 0x55), -82, 36, 2462000), ies_b),
        (make_entry(win, b"", (2, 0, 0, 0, 0, 1), -90, 20, 2412000, cap=0x10,
                    rates=(0x8002, 0x8004, 0x000B, 0x0016)), b""),
    ])
    nets = win.WlanClient().bss_list(win.GUID())
    assert len(nets) == 3
    a, c, h = nets

    assert a["ssid"] == "Office" and a["bssid"] == "a0:b1:c2:d3:e4:f5"
    assert (a["rssi"], a["quality"]) == (-45, 100)
    assert (a["band"], a["channel"], a["freq"], a["width"]) == ("5", 36, 5180, 80)
    assert a["security"] == "WPA2-Personal"

    assert c["ssid"] == "카페" and c["bssid"] == "00:11:22:33:44:55"
    assert (c["band"], c["channel"], c["freq"]) == ("2.4", 11, 2462)
    assert c["quality"] == 36 and c["security"] == "Open"

    assert h["ssid"] == "" and h["bssid"] == "02:00:00:00:00:01"
    assert h["security"] == "WEP"
    assert h["rates"] == [1, 2, 5.5, 11]                 # IE가 없으면 wlanRateSet 사용


def test_bss_list_empty(win):
    install_bss_list(win, [])
    assert win.WlanClient().bss_list(win.GUID()) == []


def test_access_denied_message(win):
    win._fake_dll.funcs["WlanGetNetworkBssList"] = FakeFunc(lambda *a: win.ERROR_ACCESS_DENIED)
    with pytest.raises(WlanError) as ei:
        win.WlanClient().bss_list(win.GUID())
    assert ei.value.code == 5
    assert "위치" in str(ei.value)
