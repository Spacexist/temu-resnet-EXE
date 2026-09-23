@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
if exist "%ROOT%env\python.exe" (
  "%ROOT%env\python.exe" "%ROOT%KitchenApp.py"
) else if exist "%ROOT%runtime\base-python\Scripts\python.exe" (
  "%ROOT%runtime\base-python\Scripts\python.exe" "%ROOT%KitchenApp.py"
) else if exist "%ROOT%runtime\base-python\python.exe" (
  "%ROOT%runtime\base-python\python.exe" "%ROOT%KitchenApp.py"
) else if exist "%ROOT%环境安装.bat" (
  call "%ROOT%环境安装.bat"
  if errorlevel 1 goto end
  if exist "%ROOT%env\python.exe" "%ROOT%env\python.exe" "%ROOT%KitchenApp.py"
) else (
  py -3 "%ROOT%KitchenApp.py"
)
:end
pause
