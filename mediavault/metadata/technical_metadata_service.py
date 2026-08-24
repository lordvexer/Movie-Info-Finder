"""
TechnicalMetadataService: bridges FFprobe parsing + Quality classification
into persisted database rows (VideoStream/AudioStream/SubtitleStream +
MediaFile.raw_media_metadata + quality label).

This is the piece that ScanManager's `on_file_ready_for_metadata` callback
invokes for every NEW/MODIFIED file, satisfying spec section 9's pipeline
steps "Technical Metadata Extraction" -> "Quality Analysis".

Failures here NEVER abort the scan (spec section 51/52): a file that fails
ffprobe extraction is marked with an error on the MediaFile row and the
scan simply continues to the next file.
"""
from __future__ import annotations
import logging

from sqlalchemy.orm import Session

from mediavault.database.models import MediaFile, VideoStream, AudioStream, SubtitleStream
from mediavault.metadata.ffprobe import extract_technical_metadata, FFprobeError
from mediavault.metadata.quality_classifier import classify_quality

logger = logging.getLogger("mediavault.technical_metadata_service")


class TechnicalMetadataService:
    def __init__(self, session: Session, ffprobe_path: str = "ffprobe"):
        self.session = session
        self.ffprobe_path = ffprobe_path

    def process_file(self, media_file_id: str) -> None:
        media_file = self.session.get(MediaFile, media_file_id)
        if media_file is None:
            logger.warning("MediaFile %s not found; skipping technical extraction", media_file_id)
            return

        full_path = media_file.full_path()
        try:
            raw_json, parsed = extract_technical_metadata(full_path, ffprobe_path=self.ffprobe_path)
        except FFprobeError as exc:
            media_file.last_error = f"FFprobe extraction failed: {exc}"
            media_file.error_count += 1
            self.session.flush()
            logger.error("FFprobe failed for %s: %s", full_path, exc)
            return

        media_file.raw_media_metadata = raw_json

        # Clear previous stream rows before re-inserting (handles re-scan / MODIFIED files).
        for stream in list(media_file.video_streams):
            self.session.delete(stream)
        for stream in list(media_file.audio_streams):
            self.session.delete(stream)
        for stream in list(media_file.subtitle_streams):
            self.session.delete(stream)
        self.session.flush()

        for v in parsed.video_streams:
            self.session.add(VideoStream(
                file_id=media_file.id, stream_index=v.stream_index, codec=v.codec,
                codec_profile=v.codec_profile, codec_level=v.codec_level, width=v.width, height=v.height,
                resolution_label=None, aspect_ratio=v.aspect_ratio, pixel_format=v.pixel_format,
                bit_depth=v.bit_depth, frame_rate=v.frame_rate, avg_frame_rate=v.avg_frame_rate,
                bitrate=v.bitrate, color_range=v.color_range, color_space=v.color_space,
                color_transfer=v.color_transfer, color_primaries=v.color_primaries, is_hdr=v.is_hdr,
                hdr_format=v.hdr_format, dolby_vision_profile=v.dolby_vision_profile,
                mastering_display_info=v.mastering_display_info, content_light_level=v.content_light_level,
                scan_type=v.scan_type,
            ))

        for a in parsed.audio_streams:
            self.session.add(AudioStream(
                file_id=media_file.id, stream_index=a.stream_index, codec=a.codec, language=a.language,
                title=a.title, channels=a.channels, channel_layout=a.channel_layout, bitrate=a.bitrate,
                sample_rate=a.sample_rate, bit_depth=a.bit_depth, profile=a.profile,
                is_default=a.is_default, is_forced=a.is_forced, is_commentary=a.is_commentary,
                is_lossless=a.is_lossless,
            ))

        for s in parsed.subtitle_streams:
            self.session.add(SubtitleStream(
                file_id=media_file.id, stream_index=s.stream_index, language=s.language, codec=s.codec,
                title=s.title, is_forced=s.is_forced, is_default=s.is_default,
                is_hearing_impaired=s.is_hearing_impaired, is_text_based=s.is_text_based,
            ))

        primary_video = parsed.video_streams[0] if parsed.video_streams else None
        quality = classify_quality(
            video=primary_video, audio_streams=parsed.audio_streams,
            container=parsed.container, filename=media_file.filename,
        )
        if primary_video is not None:
            self.session.flush()
            video_row = (
                self.session.query(VideoStream)
                .filter_by(file_id=media_file.id, stream_index=primary_video.stream_index)
                .first()
            )
            if video_row is not None:
                video_row.resolution_label = quality.resolution_label

        self.session.flush()
        logger.info("Technical metadata extracted for %s: %s", full_path, quality.normalized_label)