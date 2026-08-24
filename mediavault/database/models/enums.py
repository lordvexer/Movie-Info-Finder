"""
Enumerations shared across the MediaVault data model.
Kept centralized so business logic and DB layer both import from the same source of truth.
"""
import enum


class DriveStatus(str, enum.Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"
    ERROR = "ERROR"


class FileScanState(str, enum.Enum):
    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    MODIFIED = "MODIFIED"
    MOVED = "MOVED"
    RENAMED = "RENAMED"
    MISSING = "MISSING"
    DELETED = "DELETED"
    ERROR = "ERROR"


class ScanJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    SCANNING = "SCANNING"
    PAUSED = "PAUSED"
    INTERRUPTED = "INTERRUPTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ScanJobType(str, enum.Enum):
    QUICK = "QUICK"
    FULL = "FULL"
    METADATA_REPAIR = "METADATA_REPAIR"
    DUPLICATE_SCAN = "DUPLICATE_SCAN"
    ARTWORK_SCAN = "ARTWORK_SCAN"
    FULL_MAINTENANCE = "FULL_MAINTENANCE"


class ScanItemStatus(str, enum.Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PipelineStage(str, enum.Enum):
    """Per-file pipeline progress, persisted so a crash mid-pipeline can resume the exact stage."""
    DISCOVERED = "DISCOVERED"
    IDENTIFIED = "IDENTIFIED"
    STATE_COMPARED = "STATE_COMPARED"
    TECH_EXTRACTED = "TECH_EXTRACTED"
    NAME_PARSED = "NAME_PARSED"
    MOVIE_MATCHED = "MOVIE_MATCHED"
    METADATA_FETCHED = "METADATA_FETCHED"
    METADATA_NORMALIZED = "METADATA_NORMALIZED"
    QUALITY_CLASSIFIED = "QUALITY_CLASSIFIED"
    DUPLICATE_CHECKED = "DUPLICATE_CHECKED"
    DB_UPDATED = "DB_UPDATED"
    FILE_METADATA_WRITTEN = "FILE_METADATA_WRITTEN"
    RENAMED = "RENAMED"
    VERIFIED = "VERIFIED"
    COMPLETED = "COMPLETED"


class HashTier(str, enum.Enum):
    NONE = "NONE"
    FAST = "FAST"
    FULL_SHA256 = "FULL_SHA256"


class MetadataFieldSource(str, enum.Enum):
    EXTERNAL_PROVIDER = "EXTERNAL_PROVIDER"
    DATABASE = "DATABASE"
    FILE_EMBEDDED = "FILE_EMBEDDED"
    FILENAME = "FILENAME"
    USER_OVERRIDE = "USER_OVERRIDE"


class DuplicateRelationType(str, enum.Enum):
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    SAME_MOVIE_DIFFERENT_VERSION = "SAME_MOVIE_DIFFERENT_VERSION"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"


class FileOperationType(str, enum.Enum):
    RENAME = "RENAME"
    MOVE = "MOVE"
    METADATA_UPDATE = "METADATA_UPDATE"
    METADATA_REMOVE = "METADATA_REMOVE"
    ARTWORK_UPDATE = "ARTWORK_UPDATE"
    DATABASE_CORRECTION = "DATABASE_CORRECTION"
    DUPLICATE_ACTION = "DUPLICATE_ACTION"
    DELETE = "DELETE"


class FileOperationResult(str, enum.Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    WARNING = "WARNING"
    ROLLED_BACK = "ROLLED_BACK"