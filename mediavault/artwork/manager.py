"""
ArtworkManager: downloads poster/backdrop images ONCE and caches them on local
disk, per spec sections 22/58 (metadata/artwork must be stored permanently,
not re-fetched from the internet on every view).

Cache layout: ~/.mediavault/artwork/<movie_id>_poster.jpg
              ~/.mediavault/artwork/<movie_id>_backdrop.jpg

The Movie row keeps `poster_url` (the original remote URL, for reference/
re-download if needed) but the GUI should always prefer the local cached
file when present -- see get_local_poster_path().
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

import requests

ARTWORK_DIR = Path(os.path.expanduser("~")) / ".mediavault" / "artwork"


def _cache_path(movie_id: str, kind: str) -> Path:
    ARTWORK_DIR.mkdir(parents=True, exist_ok=True)
    return ARTWORK_DIR / f"{movie_id}_{kind}.jpg"


def get_local_poster_path(movie_id: str) -> Optional[Path]:
    path = _cache_path(movie_id, "poster")
    return path if path.exists() and path.stat().st_size > 0 else None


def get_local_backdrop_path(movie_id: str) -> Optional[Path]:
    path = _cache_path(movie_id, "backdrop")
    return path if path.exists() and path.stat().st_size > 0 else None


def download_and_cache(
    movie_id: str, url: str, kind: str, proxy: Optional[str] = None, timeout: int = 20
) -> Optional[Path]:
    """
    Downloads `url` to the local artwork cache for this movie/kind if not
    already cached. Returns the local path on success, None on failure
    (never raises -- artwork is a nice-to-have, must never break a scan).
    """
    path = _cache_path(movie_id, kind)
    if path.exists() and path.stat().st_size > 0:
        return path

    try:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        response = requests.get(url, timeout=timeout, proxies=proxies)
        response.raise_for_status()
        path.write_bytes(response.content)
        return path
    except Exception:  # noqa: BLE001
        return None