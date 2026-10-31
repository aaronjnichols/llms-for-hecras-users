@echo off
setlocal
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_course.ps1"
set "course_exit=%errorlevel%"
if not "%~1"=="--no-pause" pause
exit /b %course_exit%
