@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv
  if errorlevel 1 (
    echo Install Python 3.12 for Windows from python.org, including the Python launcher.
    pause
    exit /b 1
  )
)
".venv\Scripts\python.exe" -c "import PySide6, keyring" >nul 2>&1
if errorlevel 1 (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Dependency installation failed. Check the error above and your connection.
    pause
    exit /b 1
  )
)
start "Biscuit" ".venv\Scripts\pythonw.exe" "%~dp0run_pet.py" %*
