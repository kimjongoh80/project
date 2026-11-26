"""테스트용 802.11 Information Element 바이트 생성기 (실제 무선 장비 없이 비콘/프로브 응답을 흉내낸다)."""

RSN_OUI = b"\x00\x0f\xac"
MS_OUI = b"\x00\x50\xf2"


def ie(eid, body):
    body = bytes(body)
    return bytes([eid, len(body)]) + body


def ext_ie(ext_id, body):
    return ie(255, bytes([ext_id]) + bytes(body))


def ssid(name):
    return ie(0, name.encode("utf-8") if isinstance(name, str) else name)


def rates(*raw):
    """Supported Rates(1). raw는 500kbps 단위(+0x80 = 기본 속도) 값."""
    return ie(1, bytes(raw))


def ext_rates(*raw):
    return ie(50, bytes(raw))


def ds(channel):
    return ie(3, [channel])


def _suite_list(oui, types):
    return len(types).to_bytes(2, "little") + b"".join(oui + bytes([t]) for t in types)


def rsn(akms, pairwise=(4,), group=4, rsn_cap=None):
    body = (1).to_bytes(2, "little") + RSN_OUI + bytes([group])
    body += _suite_list(RSN_OUI, pairwise) + _suite_list(RSN_OUI, akms)
    if rsn_cap is not None:
        body += rsn_cap.to_bytes(2, "little")
    return ie(48, body)


def wpa1(akms, pairwise=(2,), group=2):
    body = MS_OUI + b"\x01" + (1).to_bytes(2, "little") + MS_OUI + bytes([group])
    body += _suite_list(MS_OUI, pairwise) + _suite_list(MS_OUI, akms)
    return ie(221, body)


def ht_cap(streams=2, sgi20=True, sgi40=True):
    cap = (0x20 if sgi20 else 0) | (0x40 if sgi40 else 0)
    mcs = bytes([0xFF] * streams + [0] * (16 - streams))
    return ie(45, cap.to_bytes(2, "little") + b"\x00" + mcs + bytes(26 - 3 - 16))


def ht_op(primary, sec_offset=0, any_width=False):
    info1 = sec_offset | (0x04 if any_width else 0)
    return ie(61, bytes([primary, info1]) + bytes(20))


def vht_cap(streams=2, mcs_code=2, sgi80=True):
    cap = 0x20 if sgi80 else 0
    m = 0
    for i in range(8):
        m |= (mcs_code if i < streams else 3) << (2 * i)
    return ie(191, cap.to_bytes(4, "little") + m.to_bytes(2, "little") + bytes(6))


def vht_op(width, seg0, seg1=0):
    return ie(192, bytes([width, seg0, seg1, 0, 0]))


def he_cap(streams=2, mcs_code=2):
    m = 0
    for i in range(8):
        m |= (mcs_code if i < streams else 3) << (2 * i)
    return ext_ie(35, bytes(17) + m.to_bytes(2, "little") + m.to_bytes(2, "little"))


def he_op_6ghz(primary, width_code, ccfs0, ccfs1=0):
    params = 1 << 17
    body = params.to_bytes(3, "little") + b"\x00" + b"\x00\x00"
    body += bytes([primary, width_code, ccfs0, ccfs1, 0])
    return ext_ie(36, body)


def bss_load(stations, util_raw):
    return ie(11, stations.to_bytes(2, "little") + bytes([util_raw]) + b"\x00\x00")


def wps(**attrs):
    tags = {"device_name": 0x1011, "manufacturer": 0x1021, "model_name": 0x1023, "model_number": 0x1024}
    body = MS_OUI + b"\x04"
    for k, v in attrs.items():
        val = v.encode()
        body += tags[k].to_bytes(2, "big") + len(val).to_bytes(2, "big") + val
    return ie(221, body)


def wmm():
    return ie(221, MS_OUI + b"\x02\x00\x01\x00")
