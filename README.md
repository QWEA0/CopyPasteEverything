# ⚡ CopyPasteEverything

A lightweight, geek-style clipboard synchronization tool for Windows. Seamlessly sync your clipboard across multiple devices with real-time updates and zero friction.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

## ✨ Features

- **🚀 Lightweight & Fast** - Minimal resource usage, instant clipboard sync
- **🔄 Real-time Sync** - Automatic clipboard synchronization across devices
- **🌐 Auto Tunnel** - Built-in Cloudflare Tunnel for remote connections (no port forwarding needed)
- **📜 History Management** - Browse, search, and restore clipboard history
- **🎨 Geek-style UI** - Terminal/Matrix-inspired dark theme with animated status indicators
- **📊 Live Status** - Real-time status indicators for server, tunnel, and sync states
- **🔒 Secure** - WSS encrypted connections via Cloudflare Tunnel
- **💾 Persistent Storage** - SQLite-based history that survives restarts

## 📸 Screenshots

![CopyPasteEverything Screenshot](assets/screenshot.png)

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/QWEA0/CopyPasteEverything.git
cd CopyPasteEverything

# Run the installer (Windows)
install.bat

# Or manually install
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### Usage

```bash
# Quick launch
run.bat

# Or run directly
python main.py
```

## 🎮 How to Use

### As a Server (Host)
1. Open the application
2. Go to **SERVER** tab
3. Click **START SERVER**
4. Share the connection URL with clients

### As a Client
1. Open the application
2. Go to **CLIENT** tab
3. Enter the server URL
4. Click **CONNECT**

Once connected, any text you copy on one device will automatically appear on all connected devices!

## 📁 Project Structure

```
CopyPasteEverything/
├── main.py              # Application entry point
├── run.bat              # Quick launch script
├── install.bat          # Installation script
├── requirements.txt     # Python dependencies
└── src/
    ├── app.py           # Main application controller
    ├── server.py        # WebSocket server
    ├── client.py        # WebSocket client
    ├── clipboard_monitor.py  # Clipboard monitoring
    ├── history.py       # History management (SQLite)
    ├── tunnel.py        # Tunnel support
    ├── config.py        # Configuration management
    ├── tray.py          # System tray icon
    └── ui/
        ├── main_window.py  # Main window
        ├── components.py   # UI components
        └── theme.py        # Geek theme configuration
```

## ⚙️ Configuration

Configuration is stored in `%APPDATA%/CopyPasteEverything/config.json`:

| Option | Default | Description |
|--------|---------|-------------|
| `server_port` | 2580 | WebSocket server port |
| `tunnel_enabled` | true | Enable auto tunnel |
| `auto_sync` | true | Auto sync clipboard |
| `max_history_items` | 100 | Max history entries |
| `encryption_enabled` | true | Enable encryption |

## 📦 Building Executable

Build standalone executable using Nuitka (compiles Python to C):

```bash
# Install build dependencies
pip install -r requirements-build.txt

# Option 1: Single-file executable (portable, slower startup)
python build_nuitka.py

# Option 2: Standalone folder (faster startup, recommended)
python build_nuitka_fast.py

# Or use the batch file
build_nuitka.bat
```

**Build outputs:**
- Single-file: `nuitka_dist/CopyPasteEverything.exe` (~23 MB)
- Standalone: `nuitka_dist_fast/main.dist/CopyPasteEverything.exe` (instant startup)

## 🔧 Requirements

- Windows 10/11
- Python 3.11+ (for development)
- Dependencies (auto-installed):
  - customtkinter
  - websockets
  - pyperclip
  - pillow
  - pystray

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) - Modern UI toolkit
- [websockets](https://github.com/python-websockets/websockets) - WebSocket library

