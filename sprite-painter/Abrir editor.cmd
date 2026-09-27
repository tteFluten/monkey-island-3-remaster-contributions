@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Necesitas Python 3.11 o posterior instalado.
  pause
  exit /b 1
)
python server.py
if errorlevel 1 (
  echo.
  echo No se pudo iniciar. Si ya esta abierto, visita http://127.0.0.1:5215
  pause
)
