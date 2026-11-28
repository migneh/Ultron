@echo off
REM ultron.cmd — Windows wrapper for `python -m ultron`
REM Runs setup if not already configured, then launches the assistant.

setlocal enabledelayedexpansion

REM Determine repo root (directory of this script)
set "REPO_ROOT=%~dp0"

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

REM Check if setup is needed (no API keys configured)
if not exist "%REPO_ROOT%config\api_keys.json" (
    echo =========================================
    echo First run detected - running setup...
    echo =========================================
    echo.
    %PY_CMD% "%REPO_ROOT%scripts\setup_environment.py"
    if errorlevel 1 (
        echo.
        echo Setup failed. Please check the output above.
        exit /b 1
    )
    echo.
    echo Setup complete!
    echo.
)

REM Run the module with all passed arguments
%PY_CMD% -m ultron %*
exit /b %ERRORLEVEL%