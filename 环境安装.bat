@echo off
chcp 65001 >nul
setlocal EnableExtensions

set "ROOT=%~dp0"
set "ENV_DIR=%ROOT%env"
set "PY=%ENV_DIR%\python.exe"
set "CPU_SRC=D:\Desktop\自动组货\bundle\python-cpu\Lib\site-packages"
set "HF_SRC=%USERPROFILE%\.cache\huggingface\hub\models--BAAI--bge-small-zh-v1.5"
set "HF_DST=%ENV_DIR%\hf-cache\hub\models--BAAI--bge-small-zh-v1.5"
set "TORCH_WEIGHT_SRC=%USERPROFILE%\.cache\torch\hub\checkpoints\resnet18-f37072fd.pth"
set "TORCH_WEIGHT_DST=%ENV_DIR%\torch-cache\hub\checkpoints"
set "PIP_NO_CACHE_DIR=1"

echo [1/5] 准备 env 目录...
if not exist "%PY%" (
  py -3.10 -m venv "%ENV_DIR%"
  if errorlevel 1 (
    py -3 -m venv "%ENV_DIR%"
  )
)

if not exist "%PY%" (
  echo 未找到可用 Python。请先安装 Python 3.10，然后重新运行本脚本。
  pause
  exit /b 1
)

echo [2/5] 升级 pip 基础工具...
"%PY%" -m ensurepip --upgrade
if errorlevel 1 goto fail
"%PY%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto fail

echo [3/5] 安装 CPU 版 torch...
set "USE_LOCAL_TORCH=0"
if exist "%CPU_SRC%\torch" (
  "%PY%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 10) else 1)" >nul 2>nul
  if not errorlevel 1 set "USE_LOCAL_TORCH=1"
)
if "%USE_LOCAL_TORCH%"=="1" (
  call :copy_dir torch
  call :copy_dir torch-2.5.1+cpu.dist-info
  call :copy_dir torchgen
  call :copy_dir functorch
  call :copy_dir torchvision
  call :copy_dir torchvision-0.20.1+cpu.dist-info
  call :copy_dir filelock
  call :copy_dir filelock-3.32.3.dist-info
  call :copy_dir fsspec
  call :copy_dir fsspec-2026.7.0.dist-info
  call :copy_dir jinja2
  call :copy_dir jinja2-3.1.6.dist-info
  call :copy_dir markupsafe
  call :copy_dir markupsafe-3.0.3.dist-info
  call :copy_dir networkx
  call :copy_dir networkx-3.4.2.dist-info
  call :copy_dir sympy
  call :copy_dir sympy-1.13.1.dist-info
  call :copy_dir mpmath
  call :copy_dir mpmath-1.3.0.dist-info
  call :copy_dir numpy
  call :copy_dir numpy-2.2.6.dist-info
  call :copy_dir numpy.libs
  call :copy_dir PIL
  call :copy_dir pillow-12.3.0.dist-info
  call :copy_file typing_extensions.py
  call :copy_dir typing_extensions-4.16.0.dist-info
) else (
  "%PY%" -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
  if errorlevel 1 goto fail
)

echo [4/5] 安装项目依赖...
"%PY%" -m pip install -r "%ROOT%screener\requirements.txt" scikit-learn typing_extensions filelock fsspec jinja2 networkx sympy
if errorlevel 1 goto fail

echo [5/5] 复制离线模型缓存（若本机已有）...
if exist "%HF_SRC%" (
  robocopy "%HF_SRC%" "%HF_DST%" /E /NFL /NDL /NJH /NJS /NC /NS /NP >nul
  if %ERRORLEVEL% GEQ 8 goto fail
)
if exist "%TORCH_WEIGHT_SRC%" (
  if not exist "%TORCH_WEIGHT_DST%" mkdir "%TORCH_WEIGHT_DST%"
  copy /Y "%TORCH_WEIGHT_SRC%" "%TORCH_WEIGHT_DST%\" >nul
)

echo 正在验证环境...
"%PY%" -c "import torch, torchvision, pandas, lightgbm, sklearn, zhconv, sentence_transformers, transformers; print('OK', torch.__version__, torchvision.__version__)"
if errorlevel 1 goto fail

echo.
echo CPU 环境安装完成。现在可以双击 模型训练.bat。
pause
exit /b 0

:copy_dir
if exist "%CPU_SRC%\%~1" (
  robocopy "%CPU_SRC%\%~1" "%ENV_DIR%\Lib\site-packages\%~1" /E /NFL /NDL /NJH /NJS /NC /NS /NP /XD __pycache__ include share /XF *.pyc *.pyo *.lib >nul
  if %ERRORLEVEL% GEQ 8 exit /b %ERRORLEVEL%
)
exit /b 0

:copy_file
if exist "%CPU_SRC%\%~1" (
  copy /Y "%CPU_SRC%\%~1" "%ENV_DIR%\Lib\site-packages\%~1" >nul
)
exit /b 0

:fail
echo.
echo 安装失败，请把上面的错误截图发给维护人员。
pause
exit /b 1

