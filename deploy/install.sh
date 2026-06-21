#!/bin/bash
set -e

# Crypto Alert Bot - Installation Script
# Usage: sudo bash deploy/install.sh

INSTALL_DIR="/opt/crypto-alert"
SERVICE_NAME="crypto-alert"

echo "🚀 Crypto Alert Bot - Installation"

# 1. Install dependencies
echo "📦 Installing system packages..."
apt update && apt install -y python3 python3-venv python3-pip git

# 2. Create user
echo "👤 Creating service user..."
if ! id "crypto-alert" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" crypto-alert
fi

# 3. Create directory
echo "📁 Setting up directory..."
mkdir -p "$INSTALL_DIR"
chown crypto-alert:crypto-alert "$INSTALL_DIR"

# 4. Copy files
echo "📋 Copying project files..."
SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cp -r "$SCRIPT_DIR"/* "$INSTALL_DIR/"
cp -r "$SCRIPT_DIR"/.env.example "$INSTALL_DIR/" 2>/dev/null || true
chown -R crypto-alert:crypto-alert "$INSTALL_DIR"

# 5. Create venv and install requirements
echo "🐍 Setting up Python environment..."
sudo -u crypto-alert python3 -m venv "$INSTALL_DIR/venv"
sudo -u crypto-alert "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
sudo -u crypto-alert "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# 6. Create .env if not exists
if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "⚙️ Creating .env from template..."
    sudo -u crypto-alert cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your settings:"
    echo "    sudo -u crypto-alert nano $INSTALL_DIR/.env"
    echo ""
fi

# 7. Install systemd service
echo "🔧 Installing systemd service..."
cp "$INSTALL_DIR/deploy/$SERVICE_NAME.service" "/etc/systemd/system/$SERVICE_NAME.service"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

echo ""
echo "✅ Installation complete!"
echo ""
echo "📊 Service status:"
systemctl status "$SERVICE_NAME" --no-pager
echo ""
echo "📝 Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME    # Check status"
echo "  sudo systemctl restart $SERVICE_NAME   # Restart bot"
echo "  sudo journalctl -u $SERVICE_NAME -f    # View logs"
echo "  sudo nano $INSTALL_DIR/.env            # Edit config"
