# -*- coding: utf-8 -*-
"""
tunnel.py - Internal network tunnel management
Provides auto tunnel functionality using Cloudflare Tunnel (cloudflared).
Automatically downloads cloudflared if not present.
"""

import subprocess
import threading
import re
import time
import socket
import os
import sys
import shutil
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
import requests


@dataclass
class TunnelInfo:
    """Tunnel connection information"""
    public_url: str
    local_port: int
    provider: str
    active: bool = True


# Cloudflared download URLs
CLOUDFLARED_URLS = {
    "win32": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    "darwin": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz",
    "linux": "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
}


def get_app_dir() -> Path:
    """Get application data directory"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~/.local/share")
    app_dir = Path(base) / "CopyPasteEverything"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


class TunnelManager:
    """
    Manages Cloudflare Tunnel for exposing local server to internet.
    Automatically downloads and manages cloudflared binary.
    """

    def __init__(self, local_port: int, on_status: Optional[Callable[[str], None]] = None):
        self.local_port = local_port
        self.on_status = on_status or (lambda _: None)
        self._tunnel_info: Optional[TunnelInfo] = None
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._cloudflared_path: Optional[Path] = None

    def _log(self, message: str):
        """Log status message"""
        self.on_status(message)

    def _get_cloudflared_path(self) -> Optional[Path]:
        """Get path to cloudflared binary, download if needed"""
        app_dir = get_app_dir()

        if sys.platform == "win32":
            binary_name = "cloudflared.exe"
        else:
            binary_name = "cloudflared"

        binary_path = app_dir / binary_name

        # Check if already exists
        if binary_path.exists():
            return binary_path

        # Check if in PATH
        which_result = shutil.which("cloudflared")
        if which_result:
            return Path(which_result)

        # Download cloudflared
        self._log("[TUNNEL] Downloading cloudflared...")
        try:
            url = CLOUDFLARED_URLS.get(sys.platform)
            if not url:
                self._log(f"[TUNNEL] Unsupported platform: {sys.platform}")
                return None

            response = requests.get(url, stream=True, timeout=60)
            response.raise_for_status()

            with open(binary_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            # Make executable on Unix
            if sys.platform != "win32":
                os.chmod(binary_path, 0o755)

            self._log("[TUNNEL] cloudflared downloaded successfully")
            return binary_path

        except Exception as e:
            self._log(f"[TUNNEL] Failed to download cloudflared: {e}")
            return None

    def start(self) -> Optional[TunnelInfo]:
        """Start tunnel and return connection info"""
        if self._running:
            return self._tunnel_info

        self._running = True

        # Get cloudflared binary
        self._cloudflared_path = self._get_cloudflared_path()
        if not self._cloudflared_path:
            self._log("[TUNNEL] cloudflared not available")
            return self._fallback_local()

        # Start tunnel in background thread
        self._thread = threading.Thread(target=self._run_tunnel, daemon=True)
        self._thread.start()

        # Wait for tunnel to establish (max 15 seconds)
        for _ in range(30):
            if self._tunnel_info:
                return self._tunnel_info
            time.sleep(0.5)

        # Return None to indicate still connecting
        return None

    def _run_tunnel(self):
        """Run cloudflared tunnel"""
        try:
            self._log("[TUNNEL] Starting Cloudflare Tunnel...")

            # Start cloudflared with quick tunnel
            self._process = subprocess.Popen(
                [str(self._cloudflared_path), 'tunnel', '--url', f'http://localhost:{self.local_port}'],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )

            # Read output to find tunnel URL
            while self._running and self._process.poll() is None:
                line = self._process.stdout.readline()
                if not line:
                    continue

                # Look for tunnel URL in output
                # Format: "... https://xxxxx.trycloudflare.com ..."
                match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
                if match:
                    https_url = match.group(0)
                    # Convert to WSS for WebSocket
                    wss_url = https_url.replace('https://', 'wss://')

                    self._tunnel_info = TunnelInfo(
                        public_url=wss_url,
                        local_port=self.local_port,
                        provider="Cloudflare"
                    )
                    self._log(f"[TUNNEL] Connected: {wss_url}")

        except Exception as e:
            self._log(f"[TUNNEL] Error: {e}")

    def _fallback_local(self) -> TunnelInfo:
        """Fallback to local IP"""
        local_ip = self._get_local_ip()
        self._tunnel_info = TunnelInfo(
            public_url=f"ws://{local_ip}:{self.local_port}",
            local_port=self.local_port,
            provider="local"
        )
        return self._tunnel_info

    def _get_local_ip(self) -> str:
        """Get local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def stop(self):
        """Stop tunnel"""
        self._running = False
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        if self._tunnel_info:
            self._tunnel_info.active = False
        self._log("[TUNNEL] Stopped")

    @property
    def info(self) -> Optional[TunnelInfo]:
        """Get current tunnel info"""
        return self._tunnel_info

