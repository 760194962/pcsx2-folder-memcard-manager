@echo off
rem Launch the GUI. Prefers the Python from the python.org install manager
rem (%LOCALAPPDATA%\Python\bin), then falls back to the py launcher / PATH.
setlocal
cd /d "%~dp0"

set "PY="
set "PYW="
if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" (
    set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
    set "PYW=%LOCALAPPDATA%\Python\bin\pythonw.exe"
    goto check
)
where pyw >nul 2>nul && (set "PY=py" & set "PYW=pyw" & goto check)
where pythonw >nul 2>nul && (set "PY=python" & set "PYW=pythonw" & goto check)
echo Python 3 not found. Install it from https://www.python.org/downloads/
pause
exit /b 1

:check
"%PY%" -c "import mymcplusplus" >nul 2>nul
if errorlevel 1 (
    echo Installing dependency mymcplusplus ...
    "%PY%" -m pip install --user mymcplusplus
    if errorlevel 1 (
        echo Failed to install mymcplusplus.
        pause
        exit /b 1
    )
)
start "" "%PYW%" "%~dp0run_gui.pyw"
