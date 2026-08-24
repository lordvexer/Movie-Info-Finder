"""
Tiered hashing: never blindly SHA-256 every file on every scan of a
multi-terabyte archive. Fast hash is used for cheap MOVED/RENAMED detection;
full SHA-256 is reserved for exact-duplicate confirmation or when explicitly
configured.
"""
from __future__ import annotations
import hashlib
from enum import Enum


class HashPolicy(str, Enum):
    NEVER = "NEVER"
    NEW_FILES_ONLY = "NEW_FILES_ONLY"
    ALL_FILES = "ALL_FILES"
    DUPLICATE_ANALYSIS_ONLY = "DUPLICATE_ANALYSIS_ONLY"


_FAST_HASH_CHUNK = 1024 * 1024  # 1 MB from head and tail


def compute_fast_hash(file_path: str, file_size: int) -> str:
    """
    Cheap fingerprint: hash of (first 1MB + last 1MB + file_size), not the
    whole file. Enough to distinguish real content changes from a mere
    touch/rename, at a tiny fraction of the I/O cost of full SHA-256.
    """
    hasher = hashlib.sha256()
    hasher.update(str(file_size).encode())
    with open(file_path, "rb") as f:
        hasher.update(f.read(_FAST_HASH_CHUNK))
        if file_size > _FAST_HASH_CHUNK:
            f.seek(max(0, file_size - _FAST_HASH_CHUNK))
            hasher.update(f.read(_FAST_HASH_CHUNK))
    return hasher.hexdigest()


def compute_full_sha256(file_path: str, chunk_size: int = 8 * 1024 * 1024) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def should_hash(policy: HashPolicy, is_new_file: bool, is_duplicate_pass: bool) -> bool:
    if policy == HashPolicy.NEVER:
        return False
    if policy == HashPolicy.ALL_FILES:
        return True
    if policy == HashPolicy.NEW_FILES_ONLY:
        return is_new_file
    if policy == HashPolicy.DUPLICATE_ANALYSIS_ONLY:
        return is_duplicate_pass
    return False