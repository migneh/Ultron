@echo off
REM ultron-doctor.cmd — Windows wrapper for `python -m ultron doctor`
REM Finds the correct Python interpreter and forwards all arguments.

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

REM Run the module with all passed arguments
%PY_CMD% -m ultron doctor %*
exit /b %ERRORLEVEL%