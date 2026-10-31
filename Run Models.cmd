@echo off
setlocal
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Run Setup Course.cmd first. The course Python is missing.
  if not "%~1"=="--no-pause" pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" -E "%~dp0scripts\course_setup.py" run-all
set "course_exit=%errorlevel%"
if not "%course_exit%"=="0" echo Model run failed. Read the run summary printed above.
if not "%~1"=="--no-pause" pause
exit /b %course_exit%
