"""Windows Native Wifi API(wlanapi.dll) 스캐너. 외부 패키지 없이 ctypes만 사용."""
import ctypes
from ctypes import wintypes as wt

from wifi_scan import WlanError, build_network

_wlan = ctypes.WinDLL("wlanapi.dll")

ERROR_SUCCESS = 0
ERROR_ACCESS_DENIED = 5
ERROR_INVALID_STATE = 5023


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wt.DWORD), ("Data2", wt.WORD), ("Data3", wt.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [("InterfaceGuid", GUID),
                ("strInterfaceDescription", ctypes.c_wchar * 256),
                ("isState", ctypes.c_uint)]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [("dwNumberOfItems", wt.DWORD), ("dwIndex", wt.DWORD),
                ("InterfaceInfo", WLAN_INTERFACE_INFO * 1)]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [("uSSIDLength", wt.ULONG), ("ucSSID", ctypes.c_ubyte * 32)]


class WLAN_RATE_SET(ctypes.Structure):
    _fields_ = [("uRateSetLength", wt.ULONG), ("usRateSet", wt.USHORT * 126)]


class WLAN_BSS_ENTRY(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("uPhyId", wt.ULONG),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11BssType", ctypes.c_uint),
        ("dot11BssPhyType", ctypes.c_uint),
        ("lRssi", wt.LONG),
        ("uLinkQuality", wt.ULONG),
        ("bInRegDomain", ctypes.c_ubyte),
        ("usBeaconPeriod", wt.USHORT),
        ("ullTimestamp", ctypes.c_ulonglong),
        ("ullHostTimestamp", ctypes.c_ulonglong),
        ("usCapabilityInformation", wt.USHORT),
        ("ulChCenterFrequency", wt.ULONG),   # kHz
        ("wlanRateSet", WLAN_RATE_SET),
        ("ulIeOffset", wt.ULONG),            # 엔트리 시작 기준 오프셋
        ("ulIeSize", wt.ULONG),
    ]


class WLAN_BSS_LIST(ctypes.Structure):
    _fields_ = [("dwTotalSize", wt.DWORD), ("dwNumberOfItems", wt.DWORD),
                ("wlanBssEntries", WLAN_BSS_ENTRY * 1)]


class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("dot11Ssid", DOT11_SSID), ("dot11BssType", ctypes.c_uint),
                ("dot11Bssid", ctypes.c_ubyte * 6), ("dot11PhyType", ctypes.c_uint),
                ("uDot11PhyIndex", wt.ULONG), ("wlanSignalQuality", wt.ULONG),
                ("ulRxRate", wt.ULONG), ("ulTxRate", wt.ULONG)]


class WLAN_SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("bSecurityEnabled", wt.BOOL), ("bOneXEnabled", wt.BOOL),
                ("dot11AuthAlgorithm", ctypes.c_uint), ("dot11CipherAlgorithm", ctypes.c_uint)]


class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("isState", ctypes.c_uint), ("wlanConnectionMode", ctypes.c_uint),
                ("strProfileName", ctypes.c_wchar * 256),
                ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
                ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES)]


assert ctypes.sizeof(WLAN_BSS_ENTRY) == 360, ctypes.sizeof(WLAN_BSS_ENTRY)

_wlan.WlanOpenHandle.argtypes = [wt.DWORD, ctypes.c_void_p, ctypes.POINTER(wt.DWORD), ctypes.POINTER(wt.HANDLE)]
_wlan.WlanOpenHandle.restype = wt.DWORD
_wlan.WlanCloseHandle.argtypes = [wt.HANDLE, ctypes.c_void_p]
_wlan.WlanCloseHandle.restype = wt.DWORD
_wlan.WlanFreeMemory.argtypes = [ctypes.c_void_p]
_wlan.WlanFreeMemory.restype = None
_wlan.WlanEnumInterfaces.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(WLAN_INTERFACE_INFO_LIST))]
_wlan.WlanEnumInterfaces.restype = wt.DWORD
_wlan.WlanScan.argtypes = [wt.HANDLE, ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
_wlan.WlanScan.restype = wt.DWORD
_wlan.WlanGetNetworkBssList.argtypes = [wt.HANDLE, ctypes.POINTER(GUID), ctypes.c_void_p, ctypes.c_uint,
                                        wt.BOOL, ctypes.c_void_p, ctypes.POINTER(ctypes.POINTER(WLAN_BSS_LIST))]
_wlan.WlanGetNetworkBssList.restype = wt.DWORD
_wlan.WlanQueryInterface.argtypes = [wt.HANDLE, ctypes.POINTER(GUID), ctypes.c_uint, ctypes.c_void_p,
                                     ctypes.POINTER(wt.DWORD), ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
_wlan.WlanQueryInterface.restype = wt.DWORD


class WinWlanError(WlanError):
    def __init__(self, func, code):
        msg = f"{func} 실패 (오류 코드 {code})"
        if code == ERROR_ACCESS_DENIED:
            msg += " - Windows 설정 > 개인 정보 > 위치에서 '위치 서비스'와 '데스크톱 앱의 위치 액세스 허용'을 켜야 합니다."
        super().__init__(code, msg)
        self.code = code


def _mac(arr):
    return ":".join(f"{b:02x}" for b in arr)


def _ssid(s):
    raw = bytes(s.ucSSID[:s.uSSIDLength])
    if not raw.strip(b"\x00"):
        return ""
    return raw.decode("utf-8", errors="replace")


class WlanClient:
    def __init__(self):
        self.handle = wt.HANDLE()
        neg = wt.DWORD()
        rc = _wlan.WlanOpenHandle(2, None, ctypes.byref(neg), ctypes.byref(self.handle))
        if rc != ERROR_SUCCESS:
            raise WinWlanError("WlanOpenHandle", rc)

    def close(self):
        if self.handle:
            _wlan.WlanCloseHandle(self.handle, None)
            self.handle = wt.HANDLE()

    def interfaces(self):
        p = ctypes.POINTER(WLAN_INTERFACE_INFO_LIST)()
        rc = _wlan.WlanEnumInterfaces(self.handle, None, ctypes.byref(p))
        if rc != ERROR_SUCCESS:
            raise WinWlanError("WlanEnumInterfaces", rc)
        try:
            n = p.contents.dwNumberOfItems
            arr = ctypes.cast(ctypes.byref(p.contents.InterfaceInfo), ctypes.POINTER(WLAN_INTERFACE_INFO))
            out = []
            for i in range(n):
                info = arr[i]
                out.append({"guid": GUID.from_buffer_copy(bytes(info.InterfaceGuid)),
                            "description": info.strInterfaceDescription,
                            "state": info.isState})
            return out
        finally:
            _wlan.WlanFreeMemory(p)

    def scan(self, guid):
        rc = _wlan.WlanScan(self.handle, ctypes.byref(guid), None, None, None)
        if rc != ERROR_SUCCESS:
            raise WinWlanError("WlanScan", rc)

    def current_connection(self, guid):
        size = wt.DWORD()
        data = ctypes.c_void_p()
        rc = _wlan.WlanQueryInterface(self.handle, ctypes.byref(guid), 7, None,
                                      ctypes.byref(size), ctypes.byref(data), None)
        if rc == ERROR_INVALID_STATE:
            return None
        if rc != ERROR_SUCCESS:
            raise WinWlanError("WlanQueryInterface", rc)
        try:
            ca = ctypes.cast(data, ctypes.POINTER(WLAN_CONNECTION_ATTRIBUTES)).contents
            a = ca.wlanAssociationAttributes
            return {"ssid": _ssid(a.dot11Ssid), "bssid": _mac(a.dot11Bssid),
                    "quality": a.wlanSignalQuality,
                    "rx_mbps": a.ulRxRate / 1000, "tx_mbps": a.ulTxRate / 1000}
        finally:
            _wlan.WlanFreeMemory(data)

    def bss_list(self, guid):
        p = ctypes.POINTER(WLAN_BSS_LIST)()
        rc = _wlan.WlanGetNetworkBssList(self.handle, ctypes.byref(guid), None, 3, False, None, ctypes.byref(p))
        if rc != ERROR_SUCCESS:
            raise WinWlanError("WlanGetNetworkBssList", rc)
        try:
            n = p.contents.dwNumberOfItems
            arr = ctypes.cast(ctypes.byref(p.contents.wlanBssEntries), ctypes.POINTER(WLAN_BSS_ENTRY))
            out = []
            for i in range(n):
                e = arr[i]
                ies = ctypes.string_at(ctypes.addressof(e) + e.ulIeOffset, e.ulIeSize) if e.ulIeSize else b""
                rates = sorted({(r & 0x7FFF) * 0.5 for r in e.wlanRateSet.usRateSet[:e.wlanRateSet.uRateSetLength // 2]})
                out.append(build_network(
                    ssid=_ssid(e.dot11Ssid), bssid=_mac(e.dot11Bssid), rssi=e.lRssi, quality=e.uLinkQuality,
                    freq_mhz=round(e.ulChCenterFrequency / 1000), beacon=e.usBeaconPeriod,
                    cap_info=e.usCapabilityInformation, ies_raw=ies, fallback_rates=rates))
            return out
        finally:
            _wlan.WlanFreeMemory(p)

