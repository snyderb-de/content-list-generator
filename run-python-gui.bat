@echo off
setlocal

set "SCRIPT=%~dp0python\content_list_generator.py"

where py >nul 2>&1
if %ERRORLEVEL%==0 (
  py -3 "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

where python >nul 2>&1
if %ERRORLEVEL%==0 (
  python "%SCRIPT%" %*
  exit /b %ERRORLEVEL%
)

echo Python 3 was not found on this system.
echo Install Python 3, then run this launcher again.
exit /b 1
