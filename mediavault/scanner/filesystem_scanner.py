"""
FilesystemScanner: walks a root path and discovers candidate movie files.
Pure filesystem I/O -- no database writes here, so it stays independently
testable. ScanManager consumes its output.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Iterator

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".m2ts", ".vob", ".webm",
}

# Directories commonly present that should never be treated as movie content.
IGNORED_DIR_NAMES = {"$RECYCLE.BIN", "System Volume Information", ".mediavault"}


@dataclass
class DiscoveredFile:
    full_path: str
    relative_path: str
    filename: str
    extension: str
    size: int
    modified_time: float
    created_time: float


def walk_video_files(root_path: str) -> Iterator[DiscoveredFile]:
    # Critical: normalize BEFORE walking/relpath. QFileDialog on Windows returns
    # forward-slash paths (e.g. "D:/Film Test"), while os.walk emits backslash
    # paths. Mixing the two breaks os.path.relpath and silently produces a
    # different relative_path on every run, causing duplicate MediaFile rows.
    root_path = os.path.normpath(root_path)
    for dirpath, dirnames, filenames in os.walk(root_path):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIR_NAMES]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in VIDEO_EXTENSIONS:
                continue
            full_path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(full_path)
            except OSError:
                continue  # unreadable file: skip, do not crash the whole scan
            relative_path = os.path.relpath(full_path, root_path)
            yield DiscoveredFile(
                full_path=full_path,
                relative_path=relative_path,
                filename=filename,
                extension=ext,
                size=stat.st_size,
                modified_time=stat.st_mtime,
                created_time=stat.st_ctime,
            )


def count_video_files(root_path: str) -> int:
    return sum(1 for _ in walk_video_files(root_path))