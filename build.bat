@echo off
rem WI-FI SCANNER exe 빌드 (결과: dist\WiFiScanner.exe)
cd /d "%~dp0"
python -m pip install --quiet pywebview pyinstaller || goto :err
python make_icon.py || goto :err
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WiFiScanner --icon icon.ico ^
  --add-data "static;static" --add-data "data;data" ^
  --exclude-module CoreWLAN --exclude-module CoreLocation ^
  app.py || goto :err
echo.
echo 빌드 완료: dist\WiFiScanner.exe
pause
exit /b 0
:err
echo 빌드 실패
pause
exit /b 1
