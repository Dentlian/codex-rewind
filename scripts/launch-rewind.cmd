@echo off
setlocal
if not exist "%~dp0app\ChatGPT.exe" (
  echo Missing app\ChatGPT.exe. Keep this launcher beside the app folder.
  if /I not "%~1"=="--check" pause
  exit /b 1
)
tasklist.exe /FI "IMAGENAME eq ChatGPT.exe" /NH >nul 2>&1
if errorlevel 1 (
  echo Cannot inspect running processes. Launch cancelled; no process was closed.
  if /I not "%~1"=="--check" pause
  exit /b 3
)
tasklist.exe /FI "IMAGENAME eq ChatGPT.exe" /NH | findstr.exe /I /C:"ChatGPT.exe" >nul
if not errorlevel 1 (
  echo Please completely exit the original Codex app, including its tray icon, then run this launcher again.
  echo No existing process was closed.
  if /I not "%~1"=="--check" pause
  exit /b 2
)
if /I "%~1"=="--check" exit /b 0
start "" /D "%~dp0app" "%~dp0app\ChatGPT.exe" --disable-http-cache
endlocal
