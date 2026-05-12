#!/usr/bin/env bash
# ============================================================
# Yashi Setup Script for Linux/macOS
# ============================================================
set -e

echo ""
echo " Setting up Yashi..."
echo ""

# Python check
python3 --version >/dev/null 2>&1 || { echo "Python 3.10+ required"; exit 1; }

# Venv
[ -d venv ] || python3 -m venv venv
source venv/bin/activate

# Packages
pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt

# Directories
mkdir -p data/piper_models data/tts_cache logs

echo ""
echo " ============================================================"
echo "  Next steps:"
echo "  1. Install Ollama: curl -fsSL https://ollama.com/install.sh | sh"
echo "  2. ollama pull mistral:7b-instruct-v0.2-q4_K_M"
echo "  3. ollama pull phi3:mini"
echo "  4. Install piper-tts: pip install piper-tts"
echo "     Or download binary from github.com/rhasspy/piper/releases"
echo "  5. Download voice: en_US-amy-medium.onnx → data/piper_models/"
echo "  6. ollama serve  (in a separate terminal)"
echo "  7. python run.py"
echo " ============================================================"
echo ""
