"""
DriveIdentifier: resolves a persistent identity for a Windows mount point.

Strategy (in order of reliability):
  1. Volume serial number via GetVolumeInformationW (survives drive-letter
     changes, unplug/replug, moving to another USB port -- only changes on
     reformat).
  2. Filesystem UUID -- extension point (e.g. WMI Win32_Volume.DeviceID).
  3. Fallback fingerprint -- label + total capacity, used only if serial
     number retrieval fails.

CRITICAL FIX: GetVolumeInformationW only returns a valid serial number when
called on the actual DRIVE ROOT (e.g. "D:\\"), not on an arbitrary sub-folder
(e.g. "D:\\Movies"). Previously, scanning a sub-folder via Browse produced a
fingerprint with serial_number=None, which caused the app to register a
SECOND, different Drive row for the same physical disk -- resulting in
duplicate-looking entries. Now we ALWAYS compute the fingerprint from the
drive root, regardless of which folder the user actually selected to scan.
"""
from __future__ import annotations
import ctypes
import platform
import shutil
import ntpath
from dataclasses import dataclass
from typing import Optional


@dataclass
class DriveFingerprint:
    mount_point: str
    volume_serial_number: Optional[str]
    filesystem_uuid: Optional[str]
    fallback_fingerprint: Optional[str]
    label: Optional[str]
    filesystem: Optional[str]
    capacity_bytes: Optional[int]
    free_bytes: Optional[int]


def get_drive_root(path: str) -> str:
    """
    Reduces any path (drive root or any sub-folder) to its drive root, e.g.
    "D:\\Film Test\\Movies" -> "D:\\". This is the anchor used for BOTH the
    fingerprint lookup AND for computing relative_path in the scanner, so a
    physical disk always resolves to exactly one Drive row no matter which
    folder inside it was selected for scanning.
    """
    normalized = ntpath.normpath(path)
    drive, _ = ntpath.splitdrive(normalized)
    if not drive:
        # UNC paths or already-relative paths: fall back to the path itself.
        return normalized
    return drive + "\\"


def _get_volume_info_windows(mount_point: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Returns (label, filesystem, serial_hex) using GetVolumeInformationW. MUST be called with a drive root."""
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

    volume_name_buf = ctypes.create_unicode_buffer(261)
    fs_name_buf = ctypes.create_unicode_buffer(261)
    serial_number = ctypes.c_uint(0)
    max_component_len = ctypes.c_uint(0)
    fs_flags = ctypes.c_uint(0)

    root = mount_point if mount_point.endswith("\\") else mount_point + "\\"

    ok = kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root),
        volume_name_buf, ctypes.sizeof(volume_name_buf),
        ctypes.byref(serial_number),
        ctypes.byref(max_component_len),
        ctypes.byref(fs_flags),
        fs_name_buf, ctypes.sizeof(fs_name_buf),
    )
    if not ok:
        return None, None, None

    serial_hex = f"{serial_number.value:08X}"
    label = volume_name_buf.value or None
    fs_name = fs_name_buf.value or None
    return label, fs_name, serial_hex


def get_drive_fingerprint(path: str) -> DriveFingerprint:
    """
    Compute a persistent fingerprint for whatever drive contains `path`.
    `path` may be a drive root ("D:\\") or any sub-folder ("D:\\Movies") --
    it is always normalized to the drive root FIRST, so the exact same
    Drive row is found/reused regardless of which folder the user picked.
    The returned `mount_point` is always the drive root, never the sub-folder.
    """
    drive_root = get_drive_root(path)

    label: Optional[str] = None
    fs_name: Optional[str] = None
    serial_hex: Optional[str] = None

    if platform.system() == "Windows":
        try:
            label, fs_name, serial_hex = _get_volume_info_windows(drive_root)
        except OSError:
            pass

    capacity_bytes: Optional[int] = None
    free_bytes: Optional[int] = None
    try:
        usage = shutil.disk_usage(drive_root)
        capacity_bytes, free_bytes = usage.total, usage.free
    except OSError:
        pass

    fallback_fingerprint = None
    if serial_hex is None:
        fallback_fingerprint = f"{label or 'UNKNOWN'}::{capacity_bytes or 0}"

    return DriveFingerprint(
        mount_point=drive_root,
        volume_serial_number=serial_hex,
        filesystem_uuid=None,
        fallback_fingerprint=fallback_fingerprint,
        label=label,
        filesystem=fs_name,
        capacity_bytes=capacity_bytes,
        free_bytes=free_bytes,
    )


def list_connected_drives() -> list[str]:
    """Returns currently connected drive letters, e.g. ["C:\\\\", "H:\\\\", "J:\\\\"]."""
    if platform.system() != "Windows":
        return []
    drives = []
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
    for i in range(26):
        if bitmask & (1 << i):
            letter = chr(ord("A") + i)
            drives.append(f"{letter}:\\")
    return drives