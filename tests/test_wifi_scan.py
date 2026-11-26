"""wifi_scan 공통 파서 단위 테스트: SSID/BSSID/채널/신호/보안 필드를 목업 IE로 검증."""
import pytest

import ie_builder as b
from wifi_scan import (build_network, channel_to_freq, freq_to_channel, parse_ies, parse_rates,
                       parse_security, quality_from_rssi)


def net(ies, freq=2437, cap=0, ssid="TestAP", bssid="aa:bb:cc:dd:ee:ff", rssi=-55, **kw):
    return build_network(ssid=ssid, bssid=bssid, rssi=rssi, quality=quality_from_rssi(rssi),
                         freq_mhz=freq, beacon=100, cap_info=cap, ies_raw=ies, **kw)


# ---------------------------------------------------------------- IE 파싱

def test_parse_ies_splits_vendor_and_extension():
    raw = b.ssid("A") + b.ds(6) + b.wmm() + b.he_cap() + b.wps(device_name="X")
    ies, vendor = parse_ies(raw)
    assert ies[0] == b"A"
    assert ies[3] == b"\x06"
    assert ("ext", 35) in ies
    assert len(vendor) == 2


def test_parse_ies_keeps_first_and_stops_on_truncated_element():
    raw = b.ds(1) + b.ds(11) + bytes([7, 10, ord("K")])  # 마지막 IE는 길이보다 짧다
    ies, _ = parse_ies(raw)
    assert ies[3] == b"\x01"
    assert 7 not in ies


def test_parse_ies_empty():
    assert parse_ies(b"") == ({}, [])


# ---------------------------------------------------------------- 주파수/채널

@pytest.mark.parametrize("mhz, expected", [
    (2412, ("2.4", 1)), (2437, ("2.4", 6)), (2472, ("2.4", 13)), (2484, ("2.4", 14)),
    (5180, ("5", 36)), (5745, ("5", 149)), (5825, ("5", 165)),
    (5955, ("6", 1)), (6115, ("6", 33)), (7115, ("6", 233)),
    (0, ("?", 0)),
])
def test_freq_to_channel(mhz, expected):
    assert freq_to_channel(mhz) == expected


@pytest.mark.parametrize("band, ch", [("2.4", 1), ("2.4", 13), ("2.4", 14), ("5", 36), ("5", 165), ("6", 37)])
def test_channel_freq_roundtrip(band, ch):
    assert freq_to_channel(channel_to_freq(band, ch)) == (band, ch)


@pytest.mark.parametrize("rssi, q", [(-30, 100), (-50, 100), (-75, 50), (-100, 0), (-110, 0)])
def test_quality_from_rssi(rssi, q):
    assert quality_from_rssi(rssi) == q


# ---------------------------------------------------------------- 보안

def sec(ies_raw, cap=0):
    ies, vendor = parse_ies(ies_raw)
    return parse_security(cap, ies, vendor)


def test_security_open():
    s = sec(b"")
    assert s["security"] == "Open"
    assert s["akm"] == [] and s["ciphers"] == [] and s["pmf"] is None


def test_security_wep_from_privacy_bit():
    assert sec(b"", cap=0x0010)["security"] == "WEP"


def test_security_wpa2_personal():
    s = sec(b.rsn([2], rsn_cap=0))
    assert s["security"] == "WPA2-Personal"
    assert s["akm"] == ["PSK"]
    assert s["ciphers"] == ["CCMP"]
    assert s["pmf"] == "미지원"


def test_security_wpa3_personal_pmf_required():
    s = sec(b.rsn([8], rsn_cap=0xC0))
    assert s["security"] == "WPA3-Personal"
    assert s["akm"] == ["SAE"]
    assert s["pmf"] == "필수"


def test_security_wpa2_wpa3_transition():
    s = sec(b.rsn([2, 8], rsn_cap=0x80))
    assert s["security"] == "WPA2/WPA3-Personal"
    assert s["pmf"] == "지원"


def test_security_wpa_wpa2_mixed_personal():
    s = sec(b.rsn([2], pairwise=(4, 2)) + b.wpa1([2]))
    assert s["security"] == "WPA/WPA2-Personal"
    assert s["ciphers"] == ["CCMP", "TKIP"]


def test_security_wpa1_only_personal():
    s = sec(b.wpa1([2]))
    assert s["security"] == "WPA-Personal"
    assert s["akm"] == ["PSK"]
    assert s["ciphers"] == ["TKIP"]


def test_security_wpa1_only_enterprise():
    assert sec(b.wpa1([1]))["security"] == "WPA-Enterprise"


def test_security_wpa2_enterprise_with_ft():
    s = sec(b.rsn([1, 3]))
    assert s["security"] == "WPA2-Enterprise"
    assert s["ft"] is True


def test_security_wpa3_enterprise_192():
    assert sec(b.rsn([12], pairwise=(9,)))["security"] == "WPA3-Enterprise"


def test_security_owe():
    assert sec(b.rsn([18]))["security"] == "OWE"


def test_security_rsn_wins_over_privacy_bit():
    assert sec(b.rsn([2]), cap=0x0010)["security"] == "WPA2-Personal"


def test_security_truncated_rsn_does_not_crash():
    assert sec(b.ie(48, b"\x01\x00\x00\x0f\xac\x04\x01\x00"))["security"] == "Open"


# ---------------------------------------------------------------- 속도

def test_parse_rates_basic_and_supported():
    sup, basic = parse_rates(parse_ies(b.rates(0x82, 0x84, 0x8B, 0x96, 12, 18, 24, 36) + b.ext_rates(48, 72, 96, 108))[0])
    assert sup == [1, 2, 5.5, 6, 9, 11, 12, 18, 24, 36, 48, 54]
    assert basic == [1, 2, 5.5, 11]


@pytest.mark.parametrize("selector", [0xFF, 0xFE, 0xFB, 0xFA, 0xF9])
def test_parse_rates_ignores_bss_membership_selectors(selector):
    """HT(127)/VHT(126)/SAE-H2E(123)/HE(122)/EHT(121) 선택자는 속도가 아니다."""
    sup, basic = parse_rates(parse_ies(b.rates(0x8C, 0x98, 0xB0, selector))[0])
    assert sup == [6, 12, 24]
    assert basic == [6, 12, 24]


# ---------------------------------------------------------------- build_network 종합

def test_build_network_basic_fields():
    raw = b.ssid("TestAP") + b.rates(0x82, 0x84, 0x8B, 0x96) + b.ds(6) + b.rsn([2])
    n = net(raw, freq=2437, rssi=-60, bssid="00:11:22:33:44:55")
    assert n["ssid"] == "TestAP"
    assert n["bssid"] == "00:11:22:33:44:55"
    assert n["rssi"] == -60
    assert n["quality"] == 80
    assert (n["band"], n["channel"], n["freq"]) == ("2.4", 6, 2437)
    assert n["security"] == "WPA2-Personal"
    assert n["width"] == 20 and n["center_channel"] == 6
    assert n["phy"] == "b"


def test_build_network_korean_ssid_passthrough():
    n = net(b.ssid("우리집_와이파이"), ssid="우리집_와이파이")
    assert n["ssid"] == "우리집_와이파이"


def test_build_network_ds_overrides_frequency_channel_on_24ghz():
    assert net(b.ds(11), freq=2437)["channel"] == 11


def test_build_network_ht40_above():
    raw = b.ht_cap(streams=2) + b.ht_op(36, sec_offset=1, any_width=True)
    n = net(raw, freq=5180)
    assert (n["band"], n["channel"], n["width"], n["center_channel"]) == ("5", 36, 40, 38)
    assert n["phy"] == "n" and n["generation"] == "Wi-Fi 4"
    assert n["nss"] == 2 and n["max_rate"] == 300.0


def test_build_network_ht40_below_on_24ghz():
    raw = b.ds(11) + b.ht_cap(1) + b.ht_op(11, sec_offset=3, any_width=True)
    n = net(raw, freq=2462)
    assert (n["width"], n["center_channel"], n["width_label"]) == (40, 9, "40")


def test_build_network_vht80():
    raw = b.ht_cap(2) + b.ht_op(36, 1, True) + b.vht_cap(2, 2) + b.vht_op(1, 42)
    n = net(raw, freq=5180)
    assert (n["width"], n["center_channel"], n["center_freq"]) == (80, 42, 5210)
    assert n["phy"] == "ac" and n["generation"] == "Wi-Fi 5"
    assert n["modes"] == "a/n/ac"
    assert n["nss"] == 2 and n["max_mcs"] == 9 and n["max_rate"] == 866.7


def test_build_network_vht160_via_seg1():
    raw = b.ht_cap(2) + b.ht_op(36, 1, True) + b.vht_cap(2, 2) + b.vht_op(1, 42, 50)
    n = net(raw, freq=5180)
    assert (n["width"], n["center_channel"], n["width_label"]) == (160, 50, "160")


def test_build_network_wifi6e():
    raw = b.he_cap(2, 2) + b.he_op_6ghz(37, 2, 39)
    n = net(raw, freq=channel_to_freq("6", 37))
    assert (n["band"], n["channel"], n["width"], n["center_channel"]) == ("6", 37, 80, 39)
    assert n["generation"] == "Wi-Fi 6E"
    assert n["nss"] == 2 and n["max_mcs"] == 11 and n["max_rate"] == 1201.0


def test_build_network_hidden_ssid_and_fallback_rates():
    n = net(b"", ssid="", freq=2412, fallback_rates=[1, 2, 5.5, 11])
    assert n["ssid"] == ""
    assert n["rates"] == [1, 2, 5.5, 11]
    assert n["security"] == "Open"


def test_build_network_bss_load_wps_wmm():
    raw = (b.ds(1) + b.rsn([2], rsn_cap=0x80) + b.bss_load(7, 128) + b.wmm()
           + b.wps(manufacturer="EFM", model_name="A3004NS", model_number="1.0"))
    n = net(raw, freq=2412)
    assert n["stations"] == 7 and n["utilization"] == 50
    assert n["model"] == "A3004NS (1.0)"
    assert n["wps"]["manufacturer"] == "EFM"
    assert {"WMM", "WPS", "PMF"} <= set(n["features"])
