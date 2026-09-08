@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PYTHONHOME="
set "PYTHONPATH="
"%~dp0engine\py39\python.exe" -B -s "%~dp0avatar_runtime.py" check
set "result=%errorlevel%"
pause
exit /b %result%
