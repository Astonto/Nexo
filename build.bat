@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Instala Python 3.12 o superior de 64 bits y su Python Launcher.
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  py -3 -m venv .venv
  if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info >= (3,12), 'Se requiere Python 3.12 o superior'"
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
echo Ejecutable portable generado: %CD%\dist\Nexo.exe
echo Copia Nexo.exe a una carpeta con permisos de escritura.
endlocal
