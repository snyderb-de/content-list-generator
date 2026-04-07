@echo off

if exist "%~dp0content-list-generator.bat" (
  call "%~dp0content-list-generator.bat" %*
  exit /b %errorlevel%
)

setlocal

set "SCRIPT=%USERPROFILE%\scripts\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%USERPROFILE%\scripts\content-list-gen\content_list_generator.py"
if not exist "%SCRIPT%" set "SCRIPT=%~dp0python\content_list_generator.py"

if not exist "%SCRIPT%" (
  echo Could not find content_list_generator.py.
  echo Expected one of:
  echo   %USERPROFILE%\scripts\content_list_generator.py
  echo   %USERPROFILE%\scripts\content-list-gen\content_list_generator.py
  echo   %~dp0python\content_list_generator.py
  echo.
  echo Copy these files into %USERPROFILE%\scripts\:
  echo   content_list_generator.py
  echo   content_list_core.py
  exit /b 1
)

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
