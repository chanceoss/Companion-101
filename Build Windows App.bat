@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 goto :failed
)
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm Biscuit.spec
if errorlevel 1 goto :failed
powershell -NoProfile -Command "Compress-Archive -Path 'dist\Biscuit' -DestinationPath 'dist\Biscuit-Windows-x64.zip' -Force"
if errorlevel 1 goto :failed
echo Ready: dist\Biscuit\Biscuit.exe
echo Share the entire Biscuit folder or dist\Biscuit-Windows-x64.zip.
pause
exit /b 0
:failed
echo Build failed. See the error above. Requires Python 3.12 x64 on Windows.
pause
exit /b 1
