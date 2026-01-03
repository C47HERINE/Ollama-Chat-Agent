@echo off
setlocal
cd /d "%~dp0"

REM --- Create venv explicitly with Python 3.11 ---
if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment with Python 3.11...
    py -3.11 -m venv .venv
)

call .venv\Scripts\activate

python -m pip install --upgrade pip
REM --- Install the rest of your deps ---
python -m pip install -r requirements.txt

pip install dotenv

pip install chatterbox-tts

pip uninstall -y torch torchvision torchaudio

pip install ^
 torch==2.7.1+cu128 ^
 torchvision==0.22.1+cu128 ^
 torchaudio==2.7.1+cu128 ^
 --index-url https://download.pytorch.org/whl/cu128

echo.
python -c "import sys; print('Python:', sys.version)"
python -c "import torch; print('Torch:', torch.__version__); print('CUDA available:', torch.cuda.is_available())"
pause