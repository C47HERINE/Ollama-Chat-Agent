@echo off
setlocal
cd /d "%~dp0"

REM
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
)

call .venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

echo.
python -c "import sys; print('Python:', sys.version)"
python -c "import torch; print('Torch:', torch.__version__); print('CUDA available:', torch.cuda.is_available())"
pause