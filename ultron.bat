@echo off
rem ── ultron — start Ultron from this checkout ────────────────────────────────
rem
rem Prefers the project virtual environment when there is one, because that is
rem where `python setup.py` installed the dependencies. Falls back to whatever
rem `python` is on PATH so a fresh clone still gives a real error message
rem instead of "not recognised as a command".
rem
rem Every argument is forwarded unchanged, so ultron --pick, --provider,
rem --model and --doctor all behave exactly as they do on the command line.
setlocal
set "HERE=%~dp0"
set "PY=%HERE%.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "%HERE%main.py" %*
set "CODE=%ERRORLEVEL%"

if not "%CODE%"=="0" (
    echo.
    echo Ultron exited with code %CODE%.
    rem Double-clicking this file closes the window the moment the app stops,
    rem taking the reason with it. Keep it open when something went wrong.
    pause
)
endlocal & exit /b %CODE%
