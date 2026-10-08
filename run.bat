@echo off
rem ============================================================
rem FreeNodeMailer daily runner (entry point for Task Scheduler)
rem Usage: run.bat [extra args passed to main.py]
rem ============================================================
chcp 65001 >nul
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

if not exist "logs" mkdir "logs"

echo [%date% %time%] FreeNodeMailer run start >> "logs\runner.out.log"
%PY% "scripts\runner.py" %* >> "logs\runner.out.log" 2>&1
set "RC=%ERRORLEVEL%"
echo [%date% %time%] FreeNodeMailer run end rc=%RC% >> "logs\runner.out.log"

endlocal & exit /b %RC%
