"""Aggregates all ORM models so `Base.metadata.create_all()` sees every table."""
from mediavault.database.models.base import Base, TimestampMixin
from mediavault.database.models.enums import (
    DriveStatus, FileScanState, ScanJobStatus, ScanJobType, ScanItemStatus,
    PipelineStage, HashTier, MetadataFieldSource, DuplicateRelationType,
    FileOperationType, FileOperationResult,
)
from mediavault.database.models.drive import Drive
from mediavault.database.models.media_file import MediaFile
from mediavault.database.models.movie import (
    Movie, Person, Genre, Collection, VideoStream, AudioStream, SubtitleStream,
    movie_genres, movie_cast, movie_crew,
)
from mediavault.database.models.scan_job import ScanJob, ScanItem
from mediavault.database.models.support import (
    DuplicateGroup, FileOperation, ProviderCache, MetadataSnapshot, Setting,
)

__all__ = [
    "Base", "TimestampMixin",
    "DriveStatus", "FileScanState", "ScanJobStatus", "ScanJobType", "ScanItemStatus",
    "PipelineStage", "HashTier", "MetadataFieldSource", "DuplicateRelationType",
    "FileOperationType", "FileOperationResult",
    "Drive", "MediaFile",
    "Movie", "Person", "Genre", "Collection", "VideoStream", "AudioStream", "SubtitleStream",
    "movie_genres", "movie_cast", "movie_crew",
    "ScanJob", "ScanItem",
    "DuplicateGroup", "FileOperation", "ProviderCache", "MetadataSnapshot", "Setting",
]