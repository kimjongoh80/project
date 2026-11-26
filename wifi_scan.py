"""Wi-Fi 스캔 공통부: 802.11 Information Element 파서와 네트워크 정보 계산.

플랫폼별 스캐너(wifi_win.py: Windows, wifi_mac.py: macOS)가 비콘/프로브 응답의 IE를 넘기면
채널·폭·보안·속도·장치 정보를 같은 형식의 dict로 만들어 준다. 외부 패키지 없이 순수 파이썬.
"""


class WlanError(OSError):
    """플랫폼 공통 스캔 오류."""


# ---------------------------------------------------------------- IE 파싱

def parse_ies(buf):
    """{element_id: bytes}, 확장 IE(255)는 ('ext', ext_id) 키, 벤더 IE는 리스트로."""
    ies, vendor = {}, []
    i = 0
    while i + 2 <= len(buf):
        eid, ln = buf[i], buf[i + 1]
        body = buf[i + 2:i + 2 + ln]
        if len(body) < ln:
            break
        if eid == 221:
            vendor.append(body)
        elif eid == 255 and ln >= 1:
            ies.setdefault(("ext", body[0]), body[1:])
        else:
            ies.setdefault(eid, body)
        i += 2 + ln
    return ies, vendor


def freq_to_channel(mhz):
    if 2400 <= mhz <= 2500:
        return "2.4", 14 if mhz == 2484 else (mhz - 2407) // 5
    if 5900 < mhz <= 7125:
        return "6", (mhz - 5950) // 5
    if 4900 <= mhz <= 5900:
        return "5", (mhz - 5000) // 5
    return "?", 0


def channel_to_freq(band, ch):
    if band == "2.4":
        return 2484 if ch == 14 else 2407 + 5 * ch
    if band == "5":
        return 5000 + 5 * ch
    if band == "6":
        return 5950 + 5 * ch
    return 0


AKM_NAMES = {1: "802.1X", 2: "PSK", 3: "FT-802.1X", 4: "FT-PSK", 5: "802.1X-SHA256", 6: "PSK-SHA256",
             8: "SAE", 9: "FT-SAE", 11: "Suite-B", 12: "Suite-B-192", 18: "OWE", 24: "SAE-EXT", 25: "FT-SAE-EXT"}
CIPHER_NAMES = {1: "WEP40", 2: "TKIP", 4: "CCMP", 5: "WEP104", 8: "GCMP", 9: "GCMP-256", 10: "CCMP-256"}


def _suites(body, off):
    if off + 2 > len(body):
        return [], off
    cnt = int.from_bytes(body[off:off + 2], "little")
    off += 2
    out = []
    for _ in range(cnt):
        s = body[off:off + 4]
        if len(s) < 4:
            break
        out.append((bytes(s[:3]), s[3]))
        off += 4
    return out, off


def parse_security(cap, ies, vendor):
    akms, ciphers, proto = [], [], []
    pmf = None
    rsn = ies.get(48)
    if rsn and len(rsn) >= 8:
        pair, off = _suites(rsn, 6)
        akm, off = _suites(rsn, off)
        akms = [t for oui, t in akm if oui == b"\x00\x0f\xac"]
        ciphers = [CIPHER_NAMES.get(t, str(t)) for oui, t in pair]
        proto.append("RSN")
        if off + 2 <= len(rsn):
            rcap = int.from_bytes(rsn[off:off + 2], "little")
            pmf = "필수" if rcap & 0x40 else "지원" if rcap & 0x80 else "미지원"
    # WPA1(벤더 IE 00:50:F2 type 1): 버전(2) + 그룹 암호(4) + 페어와이즈 목록 + AKM 목록(1=802.1X, 2=PSK)
    wpa1 = next((v for v in vendor if v[:4] == b"\x00\x50\xf2\x01"), None)
    has_wpa1 = wpa1 is not None
    wpa1_akms = []
    if wpa1 is not None and len(wpa1) >= 12:
        pair1, off1 = _suites(wpa1, 10)
        akm1, _ = _suites(wpa1, off1)
        wpa1_akms = [t for oui, t in akm1 if oui == b"\x00\x50\xf2"]
        if not ciphers:
            ciphers = [CIPHER_NAMES.get(t, str(t)) for oui, t in pair1]
    wpa1_ent = 1 in wpa1_akms and 2 not in wpa1_akms

    sae = any(a in (8, 9, 24, 25) for a in akms)
    psk = any(a in (2, 4, 6) for a in akms)
    ent = any(a in (1, 3, 5) for a in akms)
    if 12 in akms or 11 in akms:
        label = "WPA3-Enterprise"
    elif sae and psk:
        label = "WPA2/WPA3-Personal"
    elif sae:
        label = "WPA3-Personal"
    elif psk:
        label = "WPA/WPA2-Personal" if has_wpa1 else "WPA2-Personal"
    elif ent:
        label = "WPA/WPA2-Enterprise" if wpa1_ent else "WPA2-Enterprise"
    elif 18 in akms:
        label = "OWE"
    elif has_wpa1:
        label = "WPA-Enterprise" if wpa1_ent else "WPA-Personal"
        if not akms:
            akms = [{1: 1, 2: 2}.get(a, a) for a in wpa1_akms]
    elif cap & 0x0010:
        label = "WEP"
    else:
        label = "Open"
    return {"security": label, "akm": [AKM_NAMES.get(a, str(a)) for a in akms],
            "ciphers": sorted(set(ciphers)), "pmf": pmf,
            "ft": any(a in (3, 4, 9, 25) for a in akms)}


# ---------------------------------------------------------------- 속도 / 기능 / 장치 정보

_BITS = {0: .5, 1: 1, 2: 1.5, 3: 2, 4: 3, 5: 4, 6: 4.5, 7: 5, 8: 6, 9: 20 / 3, 10: 7.5, 11: 25 / 3, 12: 9, 13: 10}
_NSD_HT = {20: 52, 40: 108, 80: 234, 160: 468}               # HT/VHT 데이터 서브캐리어 수
_NSD_HE = {20: 234, 40: 468, 80: 980, 160: 1960, 320: 3920}  # HE/EHT


def parse_rates(ies):
    """Supported Rates(1) + Extended(50) → (지원 속도, 기본 속도) Mbps."""
    sup, basic = set(), set()
    for eid in (1, 50):
        for r in ies.get(eid, b""):
            # BSS membership selector(121=EHT, 122=HE, 123=SAE-H2E, 124~127=EPD/GLK/VHT/HT)는 속도가 아니다
            if (r & 0x7F) >= 121 or not r & 0x7F:
                continue
            v = (r & 0x7F) * 0.5
            sup.add(v)
            if r & 0x80:
                basic.add(v)
    fmt = lambda s: [int(x) if x == int(x) else x for x in sorted(s)]
    return fmt(sup), fmt(basic)


def _mcs_map(m):
    """VHT/HE MCS map(16bit) → (공간 스트림 수, 값) 2비트씩, 3 = 미지원"""
    nss, best = 0, None
    for i in range(8):
        v = (m >> (2 * i)) & 3
        if v != 3:
            nss, best = i + 1, v if best is None else max(best, v)
    return nss, best


def capabilities(band, width, ies, sup_rates):
    """(모드 문자열, 공간 스트림, 최대 MCS, 최대 데이터 속도 Mbps)"""
    w = 160 if width > 160 and width != 320 else width
    ht, vht, he = ies.get(45), ies.get(191), ies.get(("ext", 35))
    eht = ("ext", 108) in ies or ("ext", 106) in ies

    modes = []
    if band == "2.4":
        if any(r in (1, 2, 5.5, 11) for r in sup_rates):
            modes.append("b")
        if any(r >= 6 and r not in (11, 5.5) for r in sup_rates):
            modes.append("g")
    elif band == "5":
        modes.append("a")
    if ht and band != "6":
        modes.append("n")
    if vht and band == "5":
        modes.append("ac")
    if he:
        modes.append("ax")
    if eht:
        modes.append("be")

    ht_nss, sgi20, sgi40 = 0, False, False
    if ht and len(ht) >= 7:
        cap = int.from_bytes(ht[0:2], "little")
        sgi20, sgi40 = bool(cap & 0x20), bool(cap & 0x40)
        ht_nss = sum(1 for b in ht[3:7] if b)

    nss = mcs = rate = None
    if he and len(he) >= 19:
        n, v = _mcs_map(int.from_bytes(he[17:19], "little"))
        if n:
            nss, mcs = n, (13 if eht else {0: 7, 1: 9, 2: 11}[v])
            ww = width if eht and width == 320 else min(w, 160)
            rate = nss * _NSD_HE[ww] * _BITS[mcs] / 13.6
    elif vht and band == "5" and len(vht) >= 6:
        vcap = int.from_bytes(vht[0:4], "little")
        n, v = _mcs_map(int.from_bytes(vht[4:6], "little"))
        if n:
            nss, mcs = n, 7 + v
            if w == 20 and mcs == 9 and nss not in (3, 6):
                mcs = 8
            sgi = {20: sgi20, 40: sgi40, 80: bool(vcap & 0x20), 160: bool(vcap & 0x40)}[w]
            rate = nss * _NSD_HT[w] * _BITS[mcs] / (3.6 if sgi else 4.0)
    elif ht_nss:
        nss, mcs = ht_nss, 7
        ww = 40 if w >= 40 else 20
        sgi = sgi40 if ww == 40 else sgi20
        rate = nss * _NSD_HT[ww] * _BITS[7] / (3.6 if sgi else 4.0)
    if rate is None and sup_rates:
        rate = max(sup_rates)
    return "/".join(modes), nss, mcs, (round(rate, 1) if rate else None)


def _printable(b):
    s = bytes(b).split(b"\x00")[0].decode("utf-8", errors="replace").strip()
    return s if s and all(c.isprintable() for c in s) else ""


GENERIC_MODELS = {"0", "AP_11N", "SoftAP", "AP", "123456", "1234"}


def device_info(ies, vendor):
    """AP 이름(Cisco 등), WPS 정보, 제조사별 모델 정보 추출."""
    info = {"ap_name": None, "model": None, "wps": None, "clients_vendor": None}

    # Cisco Aironet IE(133): 10바이트 뒤 16바이트가 AP 이름, 그 다음 1바이트가 접속 단말 수
    c = ies.get(133)
    if c and len(c) >= 26:
        info["ap_name"] = _printable(c[10:26]) or None
        if len(c) >= 27:
            info["clients_vendor"] = c[26]

    for v in vendor:
        # HPE Aruba (00:0B:86): OUI 타입(1) + 하위 타입(1, 3=AP 이름) + 예약(1) + AP 이름(ASCII)
        # 컨트롤러/Instant의 SSID 프로필에서 "Advertise AP Name"(advertise-ap-name)을 켜야 방송된다.
        if v[:3] == b"\x00\x0b\x86" and len(v) > 6 and v[4] == 3:
            name = _printable(v[6:]) or _printable(v[5:])
            if name and not info["ap_name"]:
                info["ap_name"] = name
            continue
        # WPS (Microsoft OUI, type 4): TLV(빅엔디언)
        if v[:4] == b"\x00\x50\xf2\x04":
            tl, i = {}, 4
            while i + 4 <= len(v):
                t = int.from_bytes(v[i:i + 2], "big")
                ln = int.from_bytes(v[i + 2:i + 4], "big")
                tl[t] = v[i + 4:i + 4 + ln]
                i += 4 + ln
            wps = {k: _printable(tl[t]) for k, t in
                   (("device_name", 0x1011), ("manufacturer", 0x1021), ("model_name", 0x1023), ("model_number", 0x1024))
                   if t in tl and _printable(tl[t])}
            info["wps"] = wps
            mn, num = wps.get("model_name", ""), wps.get("model_number", "")
            if mn and mn not in GENERIC_MODELS:
                info["model"] = mn + (f" ({num})" if num and num not in GENERIC_MODELS and num != mn and ":" not in num else "")
        # LG U+ 계열 AP(da:19:b3): type 0x10 뒤 TLV  01=제조사, 02=모델
        elif v[:4] == b"\xda\x19\xb3\x10" and not info["model"]:
            i, maker, model = 4, "", ""
            while i + 2 <= len(v):
                t, ln = v[i], v[i + 1]
                val = _printable(v[i + 2:i + 2 + ln])
                maker = val if t == 1 else maker
                model = val if t == 2 else model
                i += 2 + ln
            if model:
                info["model"] = f"{model} ({maker})" if maker else model
        # ipTIME(EFM Networks, 88:36:6c): 4바이트 + MAC 6 + MAC 6 뒤에 모델명
        elif v[:3] == b"\x88\x36\x6c" and len(v) > 19 and not info["model"]:
            m = _printable(v[19:])
            if m:
                info["model"] = f"ipTIME {m}" if not m.lower().startswith("iptime") else m
    return info


def features(ies, vendor, sec):
    f = []
    if 70 in ies:
        f.append("802.11k")
    ext = ies.get(127)
    if ext and len(ext) >= 3 and ext[2] & 0x08:
        f.append("802.11v")
    if 54 in ies or sec.get("ft"):
        f.append("802.11r")
    if any(v[:4] == b"\x00\x50\xf2\x02" for v in vendor):
        f.append("WMM")
    if any(v[:4] == b"\x00\x50\xf2\x04" for v in vendor):
        f.append("WPS")
    if sec.get("pmf") in ("필수", "지원"):
        f.append("PMF")
    return f


def compute_channel(band, primary, ies):
    """(width_mhz:int, center_channel:int, width_label:str)"""
    width, center, label = 20, primary, "20"

    ht = ies.get(61)
    if ht and len(ht) >= 2:
        off = ht[1] & 0x3
        if (ht[1] >> 2) & 1 and off in (1, 3):
            width, label = 40, "40"
            center = primary + 2 if off == 1 else primary - 2

    vht = ies.get(192)
    if band == "5" and vht and len(vht) >= 3:
        w, s0, s1 = vht[0], vht[1], vht[2]
        if w == 1:
            width, center, label = 80, s0, "80"
            if s1:
                if abs(s1 - s0) == 8:
                    width, center, label = 160, s1, "160"
                elif abs(s1 - s0) > 16:
                    label = "80+80"
        elif w == 2:
            width, center, label = 160, s0, "160"
        elif w == 3:
            width, center, label = 80, s0, "80+80"

    he = ies.get(("ext", 36))
    if he and len(he) >= 6:
        params = int.from_bytes(he[0:3], "little")
        off = 6
        if params & (1 << 14):
            off += 3
        if params & (1 << 15):
            off += 1
        if params & (1 << 17) and len(he) >= off + 5:
            ctrl, c0, c1 = he[off + 1], he[off + 2], he[off + 3]
            w = ctrl & 0x3
            if w == 0:
                width, center, label = 20, c0, "20"
            elif w == 1:
                width, center, label = 40, c0, "40"
            elif w == 2:
                width, center, label = 80, c0, "80"
            else:
                if c1 and abs(c1 - c0) == 8:
                    width, center, label = 160, c1, "160"
                else:
                    width, center, label = 80, c0, "80+80"

    eht = ies.get(("ext", 106))
    if eht and len(eht) >= 8 and eht[0] & 0x1:
        ctrl, c0, c1 = eht[5], eht[6], eht[7]
        w = ctrl & 0x7
        if w == 4:
            width, center, label = 320, c1, "320"
        elif w == 3:
            width, center, label = 160, (c1 or c0), "160"
        elif w == 2 and width < 80:
            width, center, label = 80, c0, "80"
    return width, center, label


def phy_generation(band, ies, rates):
    if ("ext", 108) in ies or ("ext", 106) in ies:
        return "be", "Wi-Fi 7"
    if ("ext", 35) in ies:
        return "ax", "Wi-Fi 6E" if band == "6" else "Wi-Fi 6"
    if 191 in ies and band == "5":
        return "ac", "Wi-Fi 5"
    if 45 in ies:
        return "n", "Wi-Fi 4"
    if band == "5":
        return "a", ""
    return ("g", "") if max(rates or [0]) > 11 else ("b", "")


def build_network(ssid, bssid, rssi, quality, freq_mhz, beacon, cap_info, ies_raw, fallback_rates=()):
    """한 BSS의 기본 값 + IE 원본 → 화면/CSV에 쓰는 네트워크 정보 dict."""
    ies, vendor = parse_ies(ies_raw)
    mhz = int(freq_mhz)
    band, ch = freq_to_channel(mhz)
    ds = ies.get(3)
    if band == "2.4" and ds:
        ch = ds[0]
    ht_op = ies.get(61)
    if ht_op and band != "6":
        ch = ht_op[0] or ch
    width, center, wlabel = compute_channel(band, ch, ies)

    sup_rates, basic_rates = parse_rates(ies)
    if not sup_rates:
        sup_rates = sorted(fallback_rates)
    phy, gen = phy_generation(band, ies, sup_rates)
    sec = parse_security(cap_info, ies, vendor)
    modes, nss, max_mcs, max_rate = capabilities(band, width, ies, sup_rates)
    dev = device_info(ies, vendor)

    stations = util = None
    bl = ies.get(11)
    if bl and len(bl) >= 3:
        stations = int.from_bytes(bl[0:2], "little")
        util = round(bl[2] * 100 / 255)
    if stations is None and dev["clients_vendor"] is not None:
        stations = dev["clients_vendor"]

    tim = ies.get(5)
    dtim = tim[1] if tim and len(tim) >= 2 else None

    country = None
    c = ies.get(7)
    if c and len(c) >= 2:
        country = bytes(c[:2]).decode("ascii", errors="replace")

    return {
        "ssid": ssid,
        "bssid": bssid,
        "rssi": rssi,
        "quality": quality,
        "band": band,
        "channel": ch,
        "freq": mhz,
        "width": width,
        "width_label": wlabel,
        "center_channel": center,
        "center_freq": channel_to_freq(band, center),
        "phy": phy,
        "generation": gen,
        "modes": modes,
        "max_rate": max_rate,         # 최대 PHY 데이터 속도(Mbps)
        "nss": nss,
        "max_mcs": max_mcs,
        "rates": sup_rates,
        "basic_rates": basic_rates,
        "beacon": beacon,
        "dtim": dtim,
        "stations": stations,
        "utilization": util,
        "country": country,
        "ap_name": dev["ap_name"],
        "model": dev["model"],
        "wps": dev["wps"],
        "features": features(ies, vendor, sec),
        **sec,
    }


def quality_from_rssi(rssi):
    """RSSI(dBm) → 0~100% (Windows 방식과 같은 선형 환산: -100 dBm=0%, -50 dBm=100%)."""
    return max(0, min(100, 2 * (int(rssi) + 100)))


if __name__ == "__main__":
    import time
    from wlan import WlanClient
    c = WlanClient()
    for itf in c.interfaces():
        print(itf["description"])
        c.scan(itf["guid"])
        time.sleep(4)
        nets = sorted(c.bss_list(itf["guid"]), key=lambda n: -n["rssi"])
        for n in nets:
            print(f"{n['rssi']:>4} dBm  ch{n['channel']:>3} ({n['band']}G, {n['width_label']:>5}MHz)  "
                  f"{n['phy']:<2} {n['security']:<20} {n['bssid']}  {n['ssid'] or '(숨김)'}")
        print("connected:", c.current_connection(itf["guid"]))
