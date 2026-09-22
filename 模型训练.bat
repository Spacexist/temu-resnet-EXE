@echo off
chcp 65001 >nul
set "ROOT=%~dp0"
if exist "%ROOT%runtime\base-python\Scripts\python.exe" (
  "%ROOT%runtime\base-python\Scripts\python.exe" "%ROOT%KitchenApp.py"
) else if exist "%ROOT%runtime\base-python\python.exe" (
  "%ROOT%runtime\base-python\python.exe" "%ROOT%KitchenApp.py"
) else (
  py -3 "%ROOT%KitchenApp.py"
)
pause
