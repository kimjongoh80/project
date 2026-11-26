#!/bin/bash
# WI-FI SCANNER macOS 앱 빌드  →  dist/WiFiScanner.app , dist/WiFiScanner-mac.zip
# 사용법: 터미널에서 이 폴더로 이동 후  bash build_mac.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== 1/5 Python 가상환경 준비"
PY=${PYTHON:-python3}
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "python3가 없습니다. https://www.python.org/downloads/macos/ 에서 설치하거나 'brew install python'을 실행하세요."
  exit 1
fi
"$PY" -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet pywebview pyinstaller pyobjc-framework-CoreWLAN pyobjc-framework-CoreLocation

echo "== 2/5 앱 아이콘 생성"
rm -rf build/mac && mkdir -p build/mac
python make_icon.py --iconset build/mac/WiFiScanner.iconset
iconutil -c icns build/mac/WiFiScanner.iconset -o build/mac/WiFiScanner.icns

echo "== 3/5 앱 번들 빌드 (PyInstaller)"
python -m PyInstaller --noconfirm --clean --windowed \
  --name WiFiScanner \
  --icon build/mac/WiFiScanner.icns \
  --osx-bundle-identifier com.wifiscanner.app \
  --add-data "static:static" --add-data "data:data" \
  --hidden-import CoreWLAN --hidden-import CoreLocation \
  --distpath dist --workpath build/mac/work --specpath build/mac \
  app.py

echo "== 4/5 Info.plist 설정 (위치 권한 안내 문구, 앱 이름)"
PLIST="dist/WiFiScanner.app/Contents/Info.plist"
MSG="주변 Wi-Fi의 이름(SSID)과 BSSID를 확인하려면 macOS 위치 서비스 권한이 필요합니다."
for KEY in NSLocationWhenInUseUsageDescription NSLocationUsageDescription NSLocationAlwaysAndWhenInUseUsageDescription; do
  /usr/libexec/PlistBuddy -c "Delete :$KEY" "$PLIST" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Add :$KEY string $MSG" "$PLIST"
done
/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName WI-FI SCANNER" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Add :CFBundleDisplayName string WI-FI SCANNER" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true" "$PLIST" 2>/dev/null || true

echo "== 5/5 서명(ad-hoc) 및 압축"
# Info.plist를 바꿨으므로 다시 서명해야 실행된다 (Apple Silicon은 서명 필수)
codesign --force --deep --sign - "dist/WiFiScanner.app"
xattr -dr com.apple.quarantine "dist/WiFiScanner.app" 2>/dev/null || true
rm -f dist/WiFiScanner-mac.zip
ditto -c -k --keepParent "dist/WiFiScanner.app" "dist/WiFiScanner-mac.zip"

echo
echo "완료: dist/WiFiScanner.app  (배포용 압축: dist/WiFiScanner-mac.zip)"
echo "처음 실행하면 위치 권한을 묻습니다 → '허용'을 눌러야 주변 AP 이름/BSSID가 보입니다."
echo "실행:  open dist/WiFiScanner.app"
