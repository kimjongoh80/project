"""운영체제에 맞는 Wi-Fi 스캐너를 고른다. (Windows: wlanapi.dll, macOS: CoreWLAN)"""
import sys

from wifi_scan import WlanError

if sys.platform == "win32":
    from wifi_win import WlanClient
elif sys.platform == "darwin":
    from wifi_mac import WlanClient
else:
    class WlanClient:  # noqa: D101
        def __init__(self):
            raise WlanError(f"지원하지 않는 운영체제입니다: {sys.platform} (Windows, macOS 지원)")

__all__ = ["WlanClient", "WlanError"]
