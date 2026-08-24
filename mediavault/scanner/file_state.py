"""
FileState: pure decision logic for classifying a discovered file against
what the database already knows. No I/O, no DB session -- fully unit-testable
in isolation.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from mediavault.database.models import FileScanState
from mediavault.scanner.filesystem_scanner import DiscoveredFile


@dataclass
class ExistingFileSnapshot:
    """Minimal view of a previously-known MediaFile row needed for comparison."""
    id: str
    relative_path: str
    file_size: int
    modified_time: Optional[float]  # epoch seconds
    fast_hash: Optional[str]


def compare_file_state(
    discovered: DiscoveredFile,
    existing: Optional[ExistingFileSnapshot],
) -> FileScanState:
    """
    Cheap-first comparison:
      - No existing record            -> NEW
      - size+mtime unchanged          -> UNCHANGED
      - size or mtime changed         -> MODIFIED
    MOVED/RENAMED detection is a separate cross-path comparison (see
    scanner.scan_manager._detect_moved_files) since it requires searching by
    size/hash rather than by matching relative_path.
    """
    if existing is None:
        return FileScanState.NEW

    size_matches = existing.file_size == discovered.size
    mtime_matches = (
        existing.modified_time is not None
        and abs(existing.modified_time - discovered.modified_time) < 2.0  # 2s tolerance (FAT rounding)
    )

    if size_matches and mtime_matches:
        return FileScanState.UNCHANGED
    return FileScanState.MODIFIED