"""Fast frame gatekeeping for the whiteboard pipeline."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from ultralytics import YOLO


@dataclass(slots=True)
class AcceptedFrame:
    timestamp: float | int
    image: bytes


class FrameProcessor:
    """Discard frames early unless they are new enough and person-free."""

    PERSON_CLASS_ID = 0

    def __init__(
        self,
        *,
        diff_threshold: float = 8.0,
        person_confidence: float = 0.5,
        diff_size: tuple[int, int] = (64, 64),
        detection_max_size: int = 640,
        output_format: str = ".jpg",
        model_name: str = "yolov8n.pt",
    ) -> None:
        self.diff_threshold = diff_threshold
        self.person_confidence = person_confidence
        self.diff_size = diff_size
        self.detection_max_size = detection_max_size
        self.output_format = output_format
        self.last_accepted_frame: np.ndarray | None = None
        self.last_accepted_timestamp: float | int | None = None
        self.discard_reason: str | None = None
        self._person_model = YOLO(model_name)

    def process_frame(self, image: str | bytes | np.ndarray, timestamp: float | int) -> dict[str, Any] | None:
        """
        Decode a frame, drop it if a person is visible or if it is too similar
        to the last accepted frame, otherwise return the accepted frame payload.
        Sets ``self.discard_reason`` to ``"person_detected"`` or ``"no_change"``
        when returning ``None``, and ``None`` on success.
        """
        self.discard_reason = None
        decoded = self._decode_image(image)

        if self.detect_person(decoded):
            self.discard_reason = "person_detected"
            return None

        normalized = self._prepare_for_diff(decoded)
        if self.last_accepted_frame is not None:
            diff = self.compute_diff(self.last_accepted_frame, normalized)
            if diff < self.diff_threshold:
                self.discard_reason = "no_change"
                return None

        encoded = self._encode_output(decoded)
        self.last_accepted_frame = normalized
        self.last_accepted_timestamp = timestamp
        return {"timestamp": timestamp, "image": encoded}

    def detect_person(self, image: np.ndarray) -> bool:
        """Return True if the detector finds a person above the confidence threshold."""
        detect_image = self._resize_for_detection(image)
        results = self._person_model.predict(
            source=detect_image,
            classes=[self.PERSON_CLASS_ID],
            conf=self.person_confidence,
            verbose=False,
        )
        for result in results:
            if result.boxes is not None and len(result.boxes) > 0:
                return True
        return False

    def compute_diff(self, img1: np.ndarray, img2: np.ndarray) -> float:
        """Mean absolute difference on normalized grayscale frames."""
        return float(np.mean(cv2.absdiff(img1, img2)))

    def _decode_image(self, image: str | bytes | np.ndarray) -> np.ndarray:
        if isinstance(image, np.ndarray):
            if image.size == 0:
                raise ValueError("Image array is empty.")
            return image

        raw_bytes = image
        if isinstance(image, str):
            raw_bytes = self._decode_base64(image)

        np_buffer = np.frombuffer(raw_bytes, dtype=np.uint8)
        decoded = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
        if decoded is None:
            raise ValueError("Failed to decode image.")
        return decoded

    def _decode_base64(self, image: str) -> bytes:
        if "," in image:
            image = image.split(",", 1)[1]
        try:
            return base64.b64decode(image, validate=True)
        except Exception as exc:  # pragma: no cover - OpenCV validates decode path
            raise ValueError("Invalid base64 image.") from exc

    def _prepare_for_diff(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, self.diff_size, interpolation=cv2.INTER_AREA)

    def _resize_for_detection(self, image: np.ndarray) -> np.ndarray:
        height, width = image.shape[:2]
        longest_side = max(height, width)
        if longest_side <= self.detection_max_size:
            return image

        scale = self.detection_max_size / longest_side
        resized_width = max(1, int(width * scale))
        resized_height = max(1, int(height * scale))
        return cv2.resize(image, (resized_width, resized_height), interpolation=cv2.INTER_AREA)

    def _encode_output(self, image: np.ndarray) -> bytes:
        ok, encoded = cv2.imencode(self.output_format, image)
        if not ok:
            raise ValueError("Failed to encode processed image.")
        return encoded.tobytes()
