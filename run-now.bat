@echo off
rem Manual run with a visible window (for debugging).
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% "scripts\runner.py" %*
echo.
echo ===== exit code: %ERRORLEVEL% =====
pause
