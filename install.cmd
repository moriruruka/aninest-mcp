@echo off
rem One-click installer wrapper: double-click this file on Windows.
rem It hands over to install.ps1 with the execution policy relaxed for this run only.
setlocal
set PS1=%~dp0install.ps1
if not exist "%PS1%" (
  echo [x] install.ps1 not found next to this file.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
if errorlevel 1 (
  echo.
  echo [x] Installation did not finish. Read the messages above.
  pause
  exit /b 1
)
echo.
pause
