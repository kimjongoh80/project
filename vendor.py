"""BSSID(MAC) → 제조사 조회. data/oui.tsv.gz (IEEE MA-L/MA-M/MA-S) 사용."""
import gzip
import os
import sys

_BASE = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_BASE, "data", "oui.tsv.gz")

# 국내에서 제품 브랜드명이 더 익숙한 제조사
ALIASES = {
    "EFM Networks": "EFM Networks (ipTIME)",
}

_table = None


def _load():
    global _table
    if _table is None:
        _table = {}
        try:
            with gzip.open(_PATH, "rt", encoding="utf-8") as f:
                for line in f:
                    k, _, v = line.rstrip("\n").partition("\t")
                    _table[k] = ALIASES.get(v, v)
        except OSError:
            pass
    return _table


def is_local(mac):
    """로컬 관리(가상/랜덤) MAC 여부 - 첫 바이트의 bit1."""
    return bool(int(mac[:2], 16) & 0x02)


def lookup(mac):
    t = _load()
    h = mac.replace(":", "").replace("-", "").upper()
    for n in (9, 7, 6):           # MA-S(36bit) → MA-M(28bit) → MA-L(24bit)
        v = t.get(h[:n])
        if v:
            return v
    return None


def annotate(networks):
    """각 네트워크 dict에 vendor / vendor_guess / virtual_mac 필드를 채운다.

    멀티 SSID AP는 같은 장비에서 첫 바이트만 바꾼 가상 BSSID를 쓰는 경우가 많아서
    (예: 80:ca:4b:f7:cd:27 ↔ 86:ca:4b:f7:cd:27) 나머지 5바이트가 같은 실제 BSSID가 있으면 그 제조사로 추정한다.
    """
    by_tail = {}
    for n in networks:
        if not is_local(n["bssid"]):
            v = lookup(n["bssid"])
            if v:
                by_tail.setdefault(n["bssid"][3:], v)
    for n in networks:
        b = n["bssid"]
        n["virtual_mac"] = is_local(b)
        n["vendor_guess"] = False
        v = None if n["virtual_mac"] else lookup(b)
        if v is None and n["virtual_mac"]:
            v = by_tail.get(b[3:])
            n["vendor_guess"] = v is not None
        n["vendor"] = v
    return networks
