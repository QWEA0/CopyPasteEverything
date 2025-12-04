# -*- coding: utf-8 -*-
"""
tunnel.py - Internal network tunnel management
Provides auto tunnel functionality using serveo.net (SSH-based, no installation needed)
Falls back to localtunnel if serveo is unavailable
"""

import subprocess
import threading
import re
import time
import socket
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


class TunnelManager:
    """
    Manages tunnel connections for exposing local server to internet.
    Uses multiple providers with automatic fallback.
    """
    
    def __init__(self, local_port: int, on_status: Optional[Callable[[str], None]] = None):
        self.local_port = local_port
        self.on_status = on_status or (lambda x: None)
        self._tunnel_info: Optional[TunnelInfo] = None
        self._process: Optional[subprocess.Popen] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def _log(self, message: str):
        """Log status message"""
        self.on_status(message)
    
    def start(self) -> Optional[TunnelInfo]:
        """Start tunnel and return connection info"""
        if self._running:
            return self._tunnel_info
        
        self._running = True
        
        # Try different tunnel providers
        providers = [
            self._try_localtunnel,
            self._try_simple_relay,
        ]
        
        for provider in providers:
            try:
                info = provider()
                if info:
                    self._tunnel_info = info
                    self._log(f"[TUNNEL] Connected via {info.provider}: {info.public_url}")
                    return info
            except Exception as e:
                self._log(f"[TUNNEL] Provider failed: {e}")
                continue
        
        self._log("[TUNNEL] All providers failed, using local IP")
        # Fallback to local IP
        local_ip = self._get_local_ip()
        self._tunnel_info = TunnelInfo(
            public_url=f"ws://{local_ip}:{self.local_port}",
            local_port=self.local_port,
            provider="local"
        )
        return self._tunnel_info
    
    def _try_localtunnel(self) -> Optional[TunnelInfo]:
        """Try localtunnel.me service"""
        self._log("[TUNNEL] Trying localtunnel...")
        try:
            # Use npx localtunnel if available
            self._process = subprocess.Popen(
                ['npx', 'localtunnel', '--port', str(self.local_port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            
            # Wait for URL
            for _ in range(30):  # 30 second timeout
                if self._process.stdout:
                    line = self._process.stdout.readline()
                    if 'your url is:' in line.lower():
                        url = line.split('is:')[-1].strip()
                        # Convert to WebSocket URL
                        ws_url = url.replace('https://', 'wss://').replace('http://', 'ws://')
                        return TunnelInfo(
                            public_url=ws_url,
                            local_port=self.local_port,
                            provider="localtunnel"
                        )
                time.sleep(1)
        except FileNotFoundError:
            self._log("[TUNNEL] localtunnel not available (npx not found)")
        except Exception as e:
            self._log(f"[TUNNEL] localtunnel failed: {e}")
        return None
    
    def _try_simple_relay(self) -> Optional[TunnelInfo]:
        """Try to get public IP for direct connection"""
        self._log("[TUNNEL] Trying direct connection...")
        try:
            # Get public IP
            response = requests.get('https://api.ipify.org', timeout=5)
            public_ip = response.text.strip()
            
            return TunnelInfo(
                public_url=f"ws://{public_ip}:{self.local_port}",
                local_port=self.local_port,
                provider="direct"
            )
        except Exception:
            return None
    
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
            self._process = None
        if self._tunnel_info:
            self._tunnel_info.active = False
    
    @property
    def info(self) -> Optional[TunnelInfo]:
        """Get current tunnel info"""
        return self._tunnel_info

