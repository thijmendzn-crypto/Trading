#!/bin/bash
# Trading Platform Setup Script

set -e

echo ""
echo "Trading Intelligence Platform — Setup"
echo "======================================"
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
REQUIRED="3.11"

if python3 -c "import sys; exit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo "Python $PYTHON_VERSION — OK"
else
    echo "Python 3.11+ required. Current: $PYTHON_VERSION"
    exit 1
fi

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

# Create .env if not exists
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "Created .env file. Please fill in your API keys:"
    echo "  ANTHROPIC_API_KEY  — https://console.anthropic.com"
    echo "  TELEGRAM_BOT_TOKEN — Create via @BotFather on Telegram"
    echo "  TELEGRAM_CHAT_ID   — Your Telegram chat/channel ID"
    echo ""
else
    echo ".env already exists — skipping"
fi

# Create data directory
mkdir -p data

echo ""
echo "Setup complete."
echo ""
echo "Next steps:"
echo "  1. Edit .env and add your ANTHROPIC_API_KEY"
echo "  2. (Optional) Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID"
echo "  3. Run: source venv/bin/activate"
echo "  4. Run: python main.py scan"
echo ""
