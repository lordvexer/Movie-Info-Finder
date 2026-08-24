"""
Application configuration. API keys and secrets are NEVER hardcoded; they are
read from environment variables (or a local .env file for development
convenience) -- never committed to source control.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

_ENV_FILE_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_FILE_PATH, override=False)


@dataclass
class AppConfig:
    db_path: str | None = None
    tmdb_api_key: str | None = None
    tmdb_language: str = "en-US"
    ffprobe_path: str = "ffprobe"
    mediainfo_path: str = "mediainfo"
    max_concurrent_metadata_workers: int = 2
    max_concurrent_hash_workers: int = 1
    http_proxy: str | None = None

    @classmethod
    def from_env(cls) -> "AppConfig":
        proxy = os.environ.get("MEDIAVAULT_HTTP_PROXY") or cls._detect_system_proxy()
        return cls(
            db_path=os.environ.get("MEDIAVAULT_DB_PATH"),
            tmdb_api_key=os.environ.get("TMDB_API_KEY"),
            tmdb_language=os.environ.get("TMDB_LANGUAGE", "en-US"),
            ffprobe_path=os.environ.get("MEDIAVAULT_FFPROBE_PATH", "ffprobe"),
            mediainfo_path=os.environ.get("MEDIAVAULT_MEDIAINFO_PATH", "mediainfo"),
            http_proxy=proxy,
        )

    @staticmethod
    def _detect_system_proxy() -> str | None:
        """
        Falls back to reading the Windows system proxy (the same one browsers /
        PowerShell use) when MEDIAVAULT_HTTP_PROXY is not explicitly set. This
        is what makes TMDB reachable through a local VPN/proxy tool (V2Ray,
        Clash, etc.) that only patches WinINet-based clients, not raw Python
        sockets used by the `requests` library.
        """
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if not proxy_enable:
                return None
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            if not proxy_server:
                return None
            # ProxyServer can be "host:port" (same proxy for all protocols) or
            # "http=host:port;https=host:port". Handle the common simple case.
            if "=" not in proxy_server:
                return f"http://{proxy_server}"
            parts = dict(p.split("=") for p in proxy_server.split(";") if "=" in p)
            chosen = parts.get("https") or parts.get("http")
            return f"http://{chosen}" if chosen else None
        except (ImportError, OSError, FileNotFoundError, ValueError):
            return None