"""
QualityClassifier: normalizes technical metadata + filename hints into a
single human-readable quality profile string, per spec section 11.

Pure function, no I/O, fully unit-testable: feed it a ParsedVideoStream +
audio list + filename, get back a label like "2160p Dolby Vision Remux".
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from mediavault.metadata.ffprobe import ParsedVideoStream, ParsedAudioStream, ParsedContainer


@dataclass
class QualityProfile:
    resolution_label: str          # "2160p" / "1080p" / "720p" / "SD"
    source_label: Optional[str]    # "BluRay Remux" / "WEB-DL" / "WEBRip" / "BluRay" / "HDTV" / None
    hdr_label: Optional[str]       # "HDR10" / "HDR10+" / "Dolby Vision" / None
    codec_label: Optional[str]     # "HEVC" / "H264" / "AV1" / etc
    normalized_label: str          # final combined string, e.g. "2160p Dolby Vision Remux"


_RESOLUTION_THRESHOLDS = [
    (3840, "2160p"),
    (2560, "1440p"),
    (1920, "1080p"),
    (1280, "720p"),
    (720, "480p"),
]

_CODEC_LABELS = {
    "hevc": "HEVC", "h265": "HEVC", "h264": "H264", "avc": "H264",
    "av1": "AV1", "vp9": "VP9", "mpeg2video": "MPEG2", "vc1": "VC1",
}

_SOURCE_KEYWORDS = [
    ("remux", "Remux"),
    ("bluray", "BluRay"), ("blu-ray", "BluRay"), ("bdrip", "BluRay"),
    ("web-dl", "WEB-DL"), ("webdl", "WEB-DL"),
    ("webrip", "WEBRip"),
    ("hdtv", "HDTV"),
    ("dvdrip", "DVD"),
]


def _resolution_label_from_dimensions(width: Optional[int], height: Optional[int]) -> str:
    if not width and not height:
        return "SD"
    reference = max(width or 0, height or 0)
    for threshold, label in _RESOLUTION_THRESHOLDS:
        if reference >= threshold:
            return label
    return "SD"


def _detect_source_from_filename(filename: str) -> Optional[str]:
    lowered = filename.lower()
    for keyword, label in _SOURCE_KEYWORDS:
        if keyword in lowered:
            return label
    return None


def _detect_hdr_label(video: ParsedVideoStream) -> Optional[str]:
    if not video.is_hdr:
        return None
    if video.hdr_format == "DolbyVision":
        return "Dolby Vision"
    return video.hdr_format or "HDR"


def classify_quality(
    video: Optional[ParsedVideoStream],
    audio_streams: list[ParsedAudioStream],
    container: Optional[ParsedContainer],
    filename: str,
) -> QualityProfile:
    if video is None:
        return QualityProfile(
            resolution_label="SD", source_label=_detect_source_from_filename(filename),
            hdr_label=None, codec_label=None, normalized_label="SD",
        )

    resolution_label = _resolution_label_from_dimensions(video.width, video.height)
    codec_key = (video.codec or "").lower()
    codec_label = _CODEC_LABELS.get(codec_key, video.codec.upper() if video.codec else None)
    hdr_label = _detect_hdr_label(video)
    source_label = _detect_source_from_filename(filename)

    is_remux = source_label == "Remux"
    parts = [resolution_label]
    if hdr_label:
        parts.append(hdr_label)
    if source_label:
        parts.append(source_label)
    elif container and container.bitrate and container.bitrate > 40_000_000:
        # very high bitrate with no explicit source tag: likely a remux-quality file
        parts.append("Remux")
        is_remux = True

    normalized_label = " ".join(parts) if parts else resolution_label

    return QualityProfile(
        resolution_label=resolution_label,
        source_label=source_label,
        hdr_label=hdr_label,
        codec_label=codec_label,
        normalized_label=normalized_label,
    )