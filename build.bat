@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Install 64-bit Python 3.12 or newer, including the Python Launcher.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,12), 'Python 3.12 or newer is required'"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\prepare_resources.py
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\collect_licenses.py
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean Nexo.spec
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\check_package.py dist\Nexo.exe
if errorlevel 1 exit /b 1
echo.
echo Portable executable built: %CD%\dist\Nexo.exe
echo Copy Nexo.exe to a writable folder.
endlocal
