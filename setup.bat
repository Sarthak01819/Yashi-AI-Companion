@echo off
REM ========================================================
REM  Yashi Setup Script for Windows
REM  Run once to install all dependencies
REM ========================================================

echo.
echo  Setting up Yashi...
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python 3.10+ required. Download from python.org
    pause & exit /b 1
)

REM Create virtual environment
if not exist "venv" (
    echo  Creating virtual environment...
    python -m venv venv
)

REM Activate and install
call venv\Scripts\activate.bat

echo  Installing Python packages...
pip install --upgrade pip
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

REM Create data folders
mkdir data 2>nul
mkdir data\piper_models 2>nul
mkdir data\tts_cache 2>nul
mkdir logs 2>nul

echo.
echo  ============================================================
echo   Next steps:
echo   1. Install Ollama: https://ollama.com/download
echo   2. Run: ollama pull mistral:7b-instruct-v0.2-q4_K_M
echo   3. Run: ollama pull phi3:mini
echo   4. Download Piper TTS: https://github.com/rhasspy/piper/releases
echo      Place piper.exe on your PATH
echo   5. Download a Piper voice model (en_US-amy-medium.onnx)
echo      and place in data\piper_models\
echo   6. Start Ollama: ollama serve
echo   7. Launch Yashi: python run.py
echo  ============================================================
echo.
pause
