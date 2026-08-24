"""
FFprobe wrapper: extracts complete technical metadata (container, video,
audio, subtitle streams) from a media file, per spec section 10.

This module is intentionally I/O-only (subprocess) and returns plain
dict/dataclasses -- no database session, no SQLAlchemy imports -- so it can
be unit-tested by feeding it a canned ffprobe JSON string.
"""
from __future__ import annotations
import json
import subprocess
from dataclasses import dataclass, field
from typing import Optional


class FFprobeError(Exception):
    pass


def run_ffprobe(file_path: str, ffprobe_path: str = "ffprobe", timeout: int = 60) -> dict:
    """
    Runs ffprobe and returns the raw parsed JSON. This raw JSON is what gets
    stored in MediaFile.raw_media_metadata (spec section 56 -- raw metadata
    preservation), so nothing is lost even if our parser below misses a field.
    """
    cmd = [
        ffprobe_path,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        "-show_chapters",
        file_path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise FFprobeError(
            f"ffprobe executable not found at '{ffprobe_path}'. "
            f"Install FFmpeg and/or set MEDIAVAULT_FFPROBE_PATH."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FFprobeError(f"ffprobe timed out after {timeout}s on {file_path}") from exc

    if result.returncode != 0:
        raise FFprobeError(f"ffprobe failed (code {result.returncode}) on {file_path}: {result.stderr[:500]}")

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FFprobeError(f"ffprobe returned invalid JSON for {file_path}") from exc


@dataclass
class ParsedContainer:
    format_name: Optional[str] = None
    format_long_name: Optional[str] = None
    duration_seconds: Optional[float] = None
    bitrate: Optional[int] = None
    size_bytes: Optional[int] = None
    creation_time: Optional[str] = None
    encoder: Optional[str] = None
    tags: dict = field(default_factory=dict)
    chapter_count: int = 0


@dataclass
class ParsedVideoStream:
    stream_index: int
    codec: Optional[str] = None
    codec_profile: Optional[str] = None
    codec_level: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[str] = None
    pixel_format: Optional[str] = None
    bit_depth: Optional[int] = None
    frame_rate: Optional[float] = None
    avg_frame_rate: Optional[float] = None
    bitrate: Optional[int] = None
    color_range: Optional[str] = None
    color_space: Optional[str] = None
    color_transfer: Optional[str] = None
    color_primaries: Optional[str] = None
    is_hdr: bool = False
    hdr_format: Optional[str] = None
    dolby_vision_profile: Optional[str] = None
    mastering_display_info: Optional[str] = None
    content_light_level: Optional[str] = None
    scan_type: Optional[str] = None


@dataclass
class ParsedAudioStream:
    stream_index: int
    codec: Optional[str] = None
    language: Optional[str] = None
    title: Optional[str] = None
    channels: Optional[int] = None
    channel_layout: Optional[str] = None
    bitrate: Optional[int] = None
    sample_rate: Optional[int] = None
    bit_depth: Optional[int] = None
    profile: Optional[str] = None
    is_default: bool = False
    is_forced: bool = False
    is_commentary: bool = False
    is_lossless: Optional[bool] = None


@dataclass
class ParsedSubtitleStream:
    stream_index: int
    language: Optional[str] = None
    codec: Optional[str] = None
    title: Optional[str] = None
    is_forced: bool = False
    is_default: bool = False
    is_hearing_impaired: bool = False
    is_text_based: Optional[bool] = None


@dataclass
class ParsedTechnicalMetadata:
    container: ParsedContainer
    video_streams: list[ParsedVideoStream]
    audio_streams: list[ParsedAudioStream]
    subtitle_streams: list[ParsedSubtitleStream]


_LOSSLESS_AUDIO_CODECS = {"flac", "truehd", "pcm_s16le", "pcm_s24le", "mlp", "dts_hd_ma"}
_TEXT_SUBTITLE_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text"}
_IMAGE_SUBTITLE_CODECS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle"}


def _to_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _to_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _parse_frame_rate(value: Optional[str]) -> Optional[float]:
    """ffprobe returns frame rates as fractions like '24000/1001'."""
    if not value:
        return None
    if "/" in value:
        try:
            num, denom = value.split("/")
            denom_f = float(denom)
            return round(float(num) / denom_f, 3) if denom_f else None
        except (ValueError, ZeroDivisionError):
            return None
    return _to_float(value)


def _detect_hdr(video_stream: dict) -> tuple[bool, Optional[str], Optional[str]]:
    """Returns (is_hdr, hdr_format, dolby_vision_profile) from ffprobe stream + side_data."""
    color_transfer = (video_stream.get("color_transfer") or "").lower()
    is_hdr = color_transfer in {"smpte2084", "arib-std-b67"}
    hdr_format = None
    dv_profile = None

    for side_data in video_stream.get("side_data_list", []) or []:
        side_type = (side_data.get("side_data_type") or "").lower()
        if "dolby vision" in side_type:
            is_hdr = True
            hdr_format = "DolbyVision"
            dv_profile = str(side_data.get("dv_profile") or "") or None
        elif "mastering display" in side_type or "content light" in side_type:
            is_hdr = True

    if is_hdr and hdr_format is None:
        codec_tag = (video_stream.get("codec_tag_string") or "").lower()
        hdr_format = "HDR10+" if "hdr10plus" in codec_tag else "HDR10"

    return is_hdr, hdr_format, dv_profile


def parse_technical_metadata(raw: dict) -> ParsedTechnicalMetadata:
    fmt = raw.get("format", {}) or {}
    container = ParsedContainer(
        format_name=fmt.get("format_name"),
        format_long_name=fmt.get("format_long_name"),
        duration_seconds=_to_float(fmt.get("duration")),
        bitrate=_to_int(fmt.get("bit_rate")),
        size_bytes=_to_int(fmt.get("size")),
        creation_time=(fmt.get("tags") or {}).get("creation_time"),
        encoder=(fmt.get("tags") or {}).get("encoder"),
        tags=fmt.get("tags") or {},
        chapter_count=len(raw.get("chapters", []) or []),
    )

    video_streams: list[ParsedVideoStream] = []
    audio_streams: list[ParsedAudioStream] = []
    subtitle_streams: list[ParsedSubtitleStream] = []

    for stream in raw.get("streams", []) or []:
        codec_type = stream.get("codec_type")
        tags = stream.get("tags", {}) or {}
        disposition = stream.get("disposition", {}) or {}

        if codec_type == "video":
            is_hdr, hdr_format, dv_profile = _detect_hdr(stream)
            mastering = next(
                (sd for sd in (stream.get("side_data_list") or [])
                 if "mastering display" in (sd.get("side_data_type") or "").lower()),
                None,
            )
            cll = next(
                (sd for sd in (stream.get("side_data_list") or [])
                 if "content light" in (sd.get("side_data_type") or "").lower()),
                None,
            )
            video_streams.append(ParsedVideoStream(
                stream_index=stream.get("index", 0),
                codec=stream.get("codec_name"),
                codec_profile=stream.get("profile"),
                codec_level=str(stream.get("level")) if stream.get("level") is not None else None,
                width=stream.get("width"),
                height=stream.get("height"),
                aspect_ratio=stream.get("display_aspect_ratio"),
                pixel_format=stream.get("pix_fmt"),
                bit_depth=_to_int(stream.get("bits_per_raw_sample")),
                frame_rate=_parse_frame_rate(stream.get("r_frame_rate")),
                avg_frame_rate=_parse_frame_rate(stream.get("avg_frame_rate")),
                bitrate=_to_int(stream.get("bit_rate")),
                color_range=stream.get("color_range"),
                color_space=stream.get("color_space"),
                color_transfer=stream.get("color_transfer"),
                color_primaries=stream.get("color_primaries"),
                is_hdr=is_hdr,
                hdr_format=hdr_format,
                dolby_vision_profile=dv_profile,
                mastering_display_info=json.dumps(mastering) if mastering else None,
                content_light_level=json.dumps(cll) if cll else None,
                scan_type="interlaced" if stream.get("field_order", "progressive") != "progressive" else "progressive",
            ))
        elif codec_type == "audio":
            codec_name = (stream.get("codec_name") or "").lower()
            audio_streams.append(ParsedAudioStream(
                stream_index=stream.get("index", 0),
                codec=stream.get("codec_name"),
                language=tags.get("language"),
                title=tags.get("title"),
                channels=stream.get("channels"),
                channel_layout=stream.get("channel_layout"),
                bitrate=_to_int(stream.get("bit_rate")),
                sample_rate=_to_int(stream.get("sample_rate")),
                bit_depth=_to_int(stream.get("bits_per_raw_sample")),
                profile=stream.get("profile"),
                is_default=bool(disposition.get("default")),
                is_forced=bool(disposition.get("forced")),
                is_commentary=bool(disposition.get("comment")) or "commentary" in (tags.get("title") or "").lower(),
                is_lossless=codec_name in _LOSSLESS_AUDIO_CODECS if codec_name else None,
            ))
        elif codec_type == "subtitle":
            codec_name = (stream.get("codec_name") or "").lower()
            is_text = None
            if codec_name in _TEXT_SUBTITLE_CODECS:
                is_text = True
            elif codec_name in _IMAGE_SUBTITLE_CODECS:
                is_text = False
            subtitle_streams.append(ParsedSubtitleStream(
                stream_index=stream.get("index", 0),
                language=tags.get("language"),
                codec=stream.get("codec_name"),
                title=tags.get("title"),
                is_forced=bool(disposition.get("forced")),
                is_default=bool(disposition.get("default")),
                is_hearing_impaired=bool(disposition.get("hearing_impaired"))
                or "sdh" in (tags.get("title") or "").lower(),
                is_text_based=is_text,
            ))

    return ParsedTechnicalMetadata(
        container=container,
        video_streams=video_streams,
        audio_streams=audio_streams,
        subtitle_streams=subtitle_streams,
    )


def extract_technical_metadata(file_path: str, ffprobe_path: str = "ffprobe") -> tuple[dict, ParsedTechnicalMetadata]:
    """Convenience entrypoint: runs ffprobe AND parses it. Returns (raw_json, parsed)."""
    raw = run_ffprobe(file_path, ffprobe_path=ffprobe_path)
    parsed = parse_technical_metadata(raw)
    return raw, parsed