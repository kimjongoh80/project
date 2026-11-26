# WI-FI SCANNER (inSSIDer 스타일)

주변 AP를 스캔해 표·채널 그래프·시간 그래프로 보여 주는 무선신호 분석기입니다. **Windows와 macOS**를 지원합니다.
(Windows: Native Wifi API `wlanapi.dll`, macOS: CoreWLAN)

## macOS 앱 만들기 / 실행
맥에서 직접 빌드해야 합니다(PyInstaller는 다른 OS용 앱을 만들 수 없음).

1. `dist/WiFiScanner-mac-source.zip`(또는 이 폴더 전체)을 맥으로 복사해 압축을 풉니다.
2. 터미널에서 그 폴더로 이동한 뒤:
   ```
   bash build_mac.sh
   ```
   → `dist/WiFiScanner.app` 과 배포용 `dist/WiFiScanner-mac.zip` 생성. `open dist/WiFiScanner.app` 으로 실행
3. 처음 실행 시 **위치 권한 요청 → 허용**. macOS 14(Sonoma)부터는 위치 권한이 없으면 주변 AP의 SSID/BSSID가 숨겨집니다.
   나중에 바꾸려면: 시스템 설정 > 개인정보 보호 및 보안 > 위치 서비스 > WiFiScanner

- 빌드 없이 바로 실행(테스트용): `bash run_mac.sh`
- 필요 조건: macOS 11 이상, Python 3.9+ (`python3`; 없으면 python.org 설치 파일 또는 `brew install python`)
- 다른 맥으로 `WiFiScanner-mac.zip`을 옮기면 "확인되지 않은 개발자" 경고가 뜰 수 있습니다 → 앱을 **우클릭 > 열기**
  (Apple 개발자 인증서 서명·공증이 없는 ad-hoc 서명 앱이기 때문)
- 맥 버전 차이: 연결 속도는 송신 속도만 제공됨(수신 속도 없음), 스캔 1회에 수 초가 걸려 갱신 주기가 Windows보다 조금 깁니다.
- 설정 파일 위치: `~/Library/Application Support/WiFiScanner/settings.json`

## 실행 (Windows 데스크톱 앱)
- **`dist\WiFiScanner.exe` 더블클릭** — 단일 실행 파일, Python 설치 불필요. 다른 PC에 복사해서 써도 됩니다.
- 개발 중에는 `python app.py` (필요 패키지: `pip install pywebview`)
- exe 다시 만들기: `build.bat` 실행 → `dist\WiFiScanner.exe`

앱은 Windows 내장 WebView2(Edge 엔진) 창으로 화면을 띄우며, 브라우저는 열리지 않습니다.
(WebView2 런타임은 Windows 11에 기본 포함)

## 실행 (브라우저 모드, 선택)
```
python server.py
```
또는 `run.bat` → 브라우저에서 http://127.0.0.1:8765 열림.
옵션: `--interval 5` (스캔 주기, 초) · `--port 8765` · `--no-browser`

콘솔에서 스캔 결과만 보려면: `python wifi_scan.py`

## 기능
- SSID / BSSID / RSSI / 채널(주채널·중심채널) / 대역 / 채널폭(20~320MHz) / 보안(WPA2·WPA3·Enterprise·OWE·Open) / 802.11 규격(n·ac·ax·be) / BSS Load(단말 수, 채널 사용률)
- 채널 점유 그래프 (2.4 / 5 / 6 GHz), 시간별 신호 세기 그래프 (1·5·10분)
- 대역 필터, 검색, 정렬, 행 클릭으로 그래프 강조 (Ctrl+클릭 다중 선택), 현재 연결 AP ★ 표시
- **상세 화면** (inSSIDer 방식) — SSID 앞 🔭 클릭 → 같은 SSID의 AP 목록(AP 이름·모드·기본/최대 속도) →
  행 클릭 → AP 상세(식별 정보·상태·구성·기능, 신호 그래프). 메인 표에서 행 더블클릭 시 바로 AP 상세, Esc로 한 단계 위로
  - AP 이름: Cisco AP 이름 IE(133), HPE Aruba 벤더 IE(00:0B:86, 하위 타입 3).
    Aruba는 SSID 프로필의 "Advertise AP Name"(`advertise-ap-name`)을 켜야 방송됨
  - 모델: WPS 정보, LG U+ 계열·ipTIME 전용 IE
  - 최대 데이터 속도·공간 스트림·최대 MCS: HT/VHT/HE 능력 정보와 운용 채널폭으로 계산
  - ✎ 버튼으로 AP 이름·모델을 직접 지정 가능 (설정 파일 `aliases`에 저장, 비우면 자동 감지 값으로 복귀)
- **그래프 높이 조절** — 표와 아래 그래프 사이의 막대를 위아래로 드래그(더블클릭 시 기본값: 창 높이의 32%). 설정 파일에 저장
- **화면 테마** — 상단 메뉴에서 🖥 시스템 설정(기본, Windows 라이트/다크를 자동으로 따름) / ☀ 라이트 / 🌙 다크 선택.
  선택은 설정 파일에 저장되고, 시스템 모드에서는 Windows 테마를 바꾸면 즉시 반영
- **표 열 편집** — 머리글을 드래그해 순서 이동, 머리글 오른쪽 경계를 드래그해 너비 조절(더블클릭 시 기본 너비),
  머리글 클릭은 정렬. "↺ 열 초기화"로 기본값 복원. 설정은 `%APPDATA%\WiFiScanner\settings.json`에 저장되어 다음 실행에도 유지
- **제조사 표시** — IEEE OUI 레지스트리(약 4만 개, 오프라인 내장)로 BSSID 제조사 조회.
  가상 MAC(멀티 SSID용 로컬 관리 주소)은 같은 장비의 실제 BSSID를 찾아 "(추정)"으로 표시
- **CSV 저장** — 현재 표에 보이는 목록(필터·정렬 반영)을 엑셀용 CSV(UTF-8 BOM)로 저장
- **채널 분석** 탭 — 대역별 추천 채널, 현재 연결 채널과 비교, 채널별 간섭 막대 그래프
  - 간섭 점수: 후보 채널과 주파수가 겹치는 AP의 최근 60초 평균 수신 전력(mW)을 겹친 비율만큼 합산 → dBm
  - 등급: 좋음 ≤ −85 · 양호 ≤ −75 · 혼잡 ≤ −65 · 매우 혼잡 > −65 dBm
  - 2.4 GHz는 1·6·11 중 추천, 5 GHz는 기본적으로 DFS(52–144) 제외 (옵션으로 포함), 6 GHz 20 MHz는 PSC 채널
  - "내 AP 제외": 연결된 AP와 같은 장비의 다른 BSSID는 간섭원에서 제외

## 제조사 DB 갱신
IEEE 원본을 받아 `python tools/build_oui.py oui.csv mam.csv oui36.csv` 실행 → `data/oui.tsv.gz` 갱신 후 `build.bat`.
원본: https://standards-oui.ieee.org/oui/oui.csv , /oui28/mam.csv , /oui36/oui36.csv

## 구조
- `app.py` — 데스크톱 앱 진입점 (내부 서버 + WebView2/WKWebView 창, 맥 위치 권한 요청)
- `make_icon.py` / `build.bat` / `build_mac.sh` — 아이콘 생성(.ico / .iconset), Windows exe·macOS app 빌드
- `vendor.py` + `data/oui.tsv.gz` — 제조사 조회, `tools/build_oui.py` — DB 변환 도구
- `wifi_scan.py` — 공통 802.11 IE 파서 (HT/VHT/HE/EHT Operation, RSN, BSS Load, 속도·장치 정보)
- `wlan.py` — OS별 스캐너 선택 · `wifi_win.py` — Windows WLAN API(ctypes) · `wifi_mac.py` — macOS CoreWLAN(PyObjC)
- `server.py` — 백그라운드 스캔 스레드 + `/api/state` JSON + 정적 파일 서버
- `static/` — UI (HTML/CSS/Canvas JS)

## 참고
- Windows 11 24H2 이후로는 **설정 > 개인 정보 및 보안 > 위치**에서 위치 서비스와 "데스크톱 앱의 위치 액세스 허용"이 켜져 있어야 스캔 목록을 받을 수 있습니다.
- 서버는 127.0.0.1에만 바인딩되어 외부에서 접근할 수 없습니다.

## 자동 빌드 (GitHub Actions)

`.github/workflows/build.yml` 이 push·PR 때마다 macOS(`build_mac.sh`)와 Windows(`build.bat`) 빌드를 실행합니다.

- 결과물: Actions 실행 화면의 **Artifacts** 에서 `WiFiScanner-mac`(WiFiScanner-mac.zip), `WiFiScanner-windows`(WiFiScanner.exe) 다운로드
- 릴리스: `git tag v1.0.0 && git push origin v1.0.0` 처럼 `v`로 시작하는 태그를 push하면 두 파일이 GitHub Release에 첨부됩니다.
- macOS 앱은 ad-hoc 서명이라 처음 실행 시 Finder에서 우클릭 → 열기 로 실행해야 할 수 있습니다.
