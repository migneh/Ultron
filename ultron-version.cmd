@echo off
REM ultron-version.cmd — Windows wrapper for `python -m ultron version` + update check
REM Shows version info and checks for new versions from GitHub releases.

setlocal enabledelayedexpansion

REM Prefer active virtualenv Python, else `python`, else `py -3`
set "PY_CMD="
if not "%VIRTUAL_ENV%"=="" (
    if exist "%VIRTUAL_ENV%\Scripts\python.exe" (
        set "PY_CMD=%VIRTUAL_ENV%\Scripts\python.exe"
    )
)
if "%PY_CMD%"=="" (
    for %%I in (python.exe) do set "PY_CMD=%%~$PATH:I"
)
if "%PY_CMD%"=="" (
    for %%I in (py.exe) do set "PY_CMD=%%~$PATH:I"
    if "%PY_CMD%"=="" (
        echo ERROR: Python not found in PATH or virtualenv.
        exit /b 9009
    ) else (
        set "PY_CMD=%PY_CMD% -3"
    )
)

REM Show version info
echo =========================================
echo Ultron Version Information
echo =========================================
%PY_CMD% -m ultron version %*

echo.
echo Checking for updates...
echo.

REM Check for updates
%PY_CMD% -m ultron update --check-only

exit /b %ERRORLEVEL%