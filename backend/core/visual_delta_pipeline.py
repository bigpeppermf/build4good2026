"""Visual-delta pipeline for live whiteboard frames."""

from __future__ import annotations

import csv
import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

from .frame_processor import FrameProcessor


@dataclass(slots=True)
class OCRLabel:
    text: str
    bbox: tuple[int, int, int, int]


@dataclass(slots=True)
class OCRAnnotation:
    text: str
    bbox: tuple[int, int, int, int]
    anchor_text: str | None = None


@dataclass(slots=True)
class OCRSnapshot:
    components: list[OCRLabel]
    annotations: list[OCRAnnotation]
    connections: list[str]


class OCRExtractor:
    """Extract visible components, annotations, and simple connections."""

    def __init__(
        self,
        *,
        tesseract_cmd: str = "tesseract",
        min_confidence: float = 35.0,
        max_connection_distance: float = 220.0,
        annotation_anchor_distance: float = 240.0,
        component_margin: int = 24,
    ) -> None:
        self.tesseract_cmd = tesseract_cmd
        self.min_confidence = min_confidence
        self.max_connection_distance = max_connection_distance
        self.annotation_anchor_distance = annotation_anchor_distance
        self.component_margin = component_margin

    def extract(self, image: bytes | np.ndarray) -> OCRSnapshot:
        decoded = self._decode_image(image)
        text_items = self._extract_text_items(decoded)
        component_boxes = self._detect_component_boxes(decoded)
        components, annotations = self._classify_text_items(text_items, component_boxes)
        connections = self._detect_connections(decoded, components)
        return OCRSnapshot(components=components, annotations=annotations, connections=connections)

    def _decode_image(self, image: bytes | np.ndarray) -> np.ndarray:
        if isinstance(image, np.ndarray):
            return image
        np_buffer = np.frombuffer(image, dtype=np.uint8)
        decoded = cv2.imdecode(np_buffer, cv2.IMREAD_COLOR)
        if decoded is None:
            raise ValueError("Failed to decode image for OCR.")
        return decoded

    def _extract_text_items(self, image: np.ndarray) -> list[OCRLabel]:
        processed = self._preprocess_for_ocr(image)
        rows = self._run_tesseract_tsv(processed)

        line_groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
        for row in rows:
            text = row.get("text", "").strip()
            if not text:
                continue
            confidence = self._parse_confidence(row.get("conf", "-1"))
            if confidence < self.min_confidence:
                continue
            key = (row.get("block_num", "0"), row.get("par_num", "0"), row.get("line_num", "0"))
            line_groups.setdefault(key, []).append(row)

        labels: list[OCRLabel] = []
        seen: set[str] = set()
        for words in line_groups.values():
            words.sort(key=lambda row: int(row.get("left", "0")))
            label = " ".join(word["text"].strip() for word in words if word.get("text", "").strip())
            normalized = label.strip()
            if not normalized:
                continue
            dedupe_key = normalized.casefold()
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            left = min(int(word.get("left", "0")) for word in words)
            top = min(int(word.get("top", "0")) for word in words)
            right = max(int(word.get("left", "0")) + int(word.get("width", "0")) for word in words)
            bottom = max(int(word.get("top", "0")) + int(word.get("height", "0")) for word in words)
            labels.append(OCRLabel(text=normalized, bbox=(left, top, right, bottom)))

        return labels

    def _detect_component_boxes(self, image: np.ndarray) -> list[tuple[int, int, int, int]]:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 75, 180)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        boxes: list[tuple[int, int, int, int]] = []
        for contour in contours:
            perimeter = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
            if len(approx) != 4:
                continue
            x, y, w, h = cv2.boundingRect(approx)
            if w < 50 or h < 24:
                continue
            area = w * h
            if area < 3000:
                continue
            boxes.append((x, y, x + w, y + h))

        return boxes

    def _classify_text_items(
        self,
        text_items: list[OCRLabel],
        component_boxes: list[tuple[int, int, int, int]],
    ) -> tuple[list[OCRLabel], list[OCRAnnotation]]:
        components: list[OCRLabel] = []
        annotations: list[OCRAnnotation] = []

        for item in text_items:
            if self._belongs_to_component_box(item, component_boxes):
                components.append(item)
                continue
            annotations.append(OCRAnnotation(text=item.text, bbox=item.bbox))

        # If rectangle detection misses boxes, keep the largest text items as components
        # so the pipeline still produces useful deltas instead of classifying everything
        # as free-floating annotation text.
        if not components and text_items:
            ranked = sorted(text_items, key=self._text_box_area, reverse=True)
            fallback_components = ranked[: max(1, min(2, len(ranked)))]
            component_ids = {id(item) for item in fallback_components}
            components = list(fallback_components)
            annotations = [
                OCRAnnotation(text=item.text, bbox=item.bbox)
                for item in text_items
                if id(item) not in component_ids
            ]

        for annotation in annotations:
            anchor = self._nearest_component(annotation.bbox, components, self.annotation_anchor_distance)
            if anchor is not None:
                annotation.anchor_text = anchor.text

        return components, annotations

    def _preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        scaled = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        blurred = cv2.GaussianBlur(scaled, (3, 3), 0)
        return cv2.adaptiveThreshold(
            blurred,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            11,
        )

    def _run_tesseract_tsv(self, image: np.ndarray) -> list[dict[str, str]]:
        with tempfile.NamedTemporaryFile(suffix=".png") as temp_file:
            temp_path = Path(temp_file.name)
            if not cv2.imwrite(str(temp_path), image):
                raise ValueError("Failed to prepare OCR image.")

            command = [
                self.tesseract_cmd,
                str(temp_path),
                "stdout",
                "--psm",
                "6",
                "tsv",
            ]
            result = subprocess.run(command, capture_output=True, text=True, check=True)

        reader = csv.DictReader(result.stdout.splitlines(), delimiter="\t")
        return list(reader)

    def _parse_confidence(self, value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return -1.0

    def _detect_connections(self, image: np.ndarray, labels: list[OCRLabel]) -> list[str]:
        if len(labels) < 2:
            return []

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 75, 200)
        lines = cv2.HoughLinesP(
            edges,
            rho=1,
            theta=np.pi / 180,
            threshold=70,
            minLineLength=50,
            maxLineGap=18,
        )
        if lines is None:
            return []

        connections: list[str] = []
        seen: set[str] = set()
        for line in lines[:, 0]:
            x1, y1, x2, y2 = [int(value) for value in line]
            source = self._nearest_label((x1, y1), labels)
            target = self._nearest_label((x2, y2), labels)
            if source is None or target is None or source.text == target.text:
                continue
            connection = f"{source.text} -> {target.text}"
            if connection not in seen:
                seen.add(connection)
                connections.append(connection)

        return connections

    def _nearest_label(self, point: tuple[int, int], labels: Iterable[OCRLabel]) -> OCRLabel | None:
        best_label: OCRLabel | None = None
        best_distance = float("inf")

        for label in labels:
            left, top, right, bottom = label.bbox
            center = ((left + right) / 2.0, (top + bottom) / 2.0)
            distance = math.dist(point, center)
            if distance < best_distance:
                best_distance = distance
                best_label = label

        if best_distance > self.max_connection_distance:
            return None
        return best_label

    def _belongs_to_component_box(
        self,
        item: OCRLabel,
        component_boxes: list[tuple[int, int, int, int]],
    ) -> bool:
        center_x, center_y = self._bbox_center(item.bbox)
        for left, top, right, bottom in component_boxes:
            if (
                left - self.component_margin <= center_x <= right + self.component_margin
                and top - self.component_margin <= center_y <= bottom + self.component_margin
            ):
                return True
        return False

    def _nearest_component(
        self,
        bbox: tuple[int, int, int, int],
        components: Iterable[OCRLabel],
        max_distance: float,
    ) -> OCRLabel | None:
        best_component: OCRLabel | None = None
        best_distance = float("inf")
        center = self._bbox_center(bbox)

        for component in components:
            distance = math.dist(center, self._bbox_center(component.bbox))
            if distance < best_distance:
                best_distance = distance
                best_component = component

        if best_distance > max_distance:
            return None
        return best_component

    def _bbox_center(self, bbox: tuple[int, int, int, int]) -> tuple[float, float]:
        left, top, right, bottom = bbox
        return ((left + right) / 2.0, (top + bottom) / 2.0)

    def _text_box_area(self, item: OCRLabel) -> int:
        left, top, right, bottom = item.bbox
        return max(1, right - left) * max(1, bottom - top)


class VisualDeltaDescriber:
    """Convert OCR snapshots into concise visual_delta strings."""

    def describe(self, previous: OCRSnapshot | None, current: OCRSnapshot) -> str | None:
        previous_components = [label.text for label in previous.components] if previous else []
        current_components = [label.text for label in current.components]
        previous_annotations = [annotation.text for annotation in previous.annotations] if previous else []
        current_annotations = [annotation.text for annotation in current.annotations]
        previous_connections = previous.connections if previous else []
        current_connections = current.connections

        added_components = [label for label in current_components if label not in previous_components]
        removed_components = [label for label in previous_components if label not in current_components]
        added_annotations = [text for text in current_annotations if text not in previous_annotations]
        removed_annotations = [text for text in previous_annotations if text not in current_annotations]
        added_connections = [connection for connection in current_connections if connection not in previous_connections]
        removed_connections = [connection for connection in previous_connections if connection not in current_connections]

        if (
            previous
            and len(previous_components) == len(current_components)
            and len(added_components) == 1
            and len(removed_components) == 1
            and not added_connections
            and not removed_connections
            and not added_annotations
            and not removed_annotations
        ):
            return f"The label '{removed_components[0]}' changed to '{added_components[0]}'."

        if len(added_components) == 1 and added_connections:
            related = self._find_related_connection(added_components[0], added_connections)
            if related is not None:
                source, target = related
                if target == added_components[0]:
                    return f"A box labeled '{target}' was drawn with an arrow from '{source}'."
                return f"A box labeled '{source}' was drawn with an arrow to '{target}'."

        if len(added_components) == 1 and added_annotations:
            annotation = self._find_annotation(current.annotations, added_annotations[0])
            if annotation is not None and annotation.anchor_text:
                return (
                    f"A box labeled '{added_components[0]}' was drawn, and text "
                    f"'{annotation.text}' was added near '{annotation.anchor_text}'."
                )

        if len(added_components) == 1:
            return f"A box labeled '{added_components[0]}' was drawn."

        if len(added_connections) == 1:
            source, target = self._split_connection(added_connections[0])
            return f"An arrow was drawn from '{source}' to '{target}'."

        if len(added_annotations) == 1:
            annotation = self._find_annotation(current.annotations, added_annotations[0])
            if annotation is not None and annotation.anchor_text:
                return f"Text '{annotation.text}' was added near '{annotation.anchor_text}'."
            return f"Text '{added_annotations[0]}' was added to the whiteboard."

        if len(removed_components) == 1:
            return f"The box labeled '{removed_components[0]}' was removed."

        if len(removed_connections) == 1:
            source, target = self._split_connection(removed_connections[0])
            return f"The arrow from '{source}' to '{target}' was removed."

        if len(removed_annotations) == 1:
            annotation = self._find_annotation(previous.annotations if previous else [], removed_annotations[0])
            if annotation is not None and annotation.anchor_text:
                return f"Text '{annotation.text}' was removed from near '{annotation.anchor_text}'."
            return f"Text '{removed_annotations[0]}' was removed from the whiteboard."

        if added_components:
            return self._describe_multiple_boxes(added_components)

        if added_connections:
            return self._describe_multiple_connections(added_connections)

        if added_annotations:
            return self._describe_multiple_annotations(current.annotations, added_annotations)

        return None

    def _find_related_connection(self, label: str, connections: list[str]) -> tuple[str, str] | None:
        for connection in connections:
            source, target = self._split_connection(connection)
            if source == label or target == label:
                return source, target
        return None

    def _split_connection(self, connection: str) -> tuple[str, str]:
        source, target = connection.split(" -> ", 1)
        return source, target

    def _find_annotation(
        self,
        annotations: Iterable[OCRAnnotation],
        text: str,
    ) -> OCRAnnotation | None:
        for annotation in annotations:
            if annotation.text == text:
                return annotation
        return None

    def _describe_multiple_boxes(self, labels: list[str]) -> str:
        if len(labels) == 2:
            return f"Boxes labeled '{labels[0]}' and '{labels[1]}' were drawn."
        head = ", ".join(f"'{label}'" for label in labels[:-1])
        return f"Boxes labeled {head}, and '{labels[-1]}' were drawn."

    def _describe_multiple_connections(self, connections: list[str]) -> str:
        if len(connections) == 2:
            first_source, first_target = self._split_connection(connections[0])
            second_source, second_target = self._split_connection(connections[1])
            return (
                f"Arrows were drawn from '{first_source}' to '{first_target}' "
                f"and from '{second_source}' to '{second_target}'."
            )
        rendered = [self._split_connection(connection) for connection in connections]
        head = ", ".join(f"'{source}' to '{target}'" for source, target in rendered[:-1])
        tail_source, tail_target = rendered[-1]
        return f"Arrows were drawn from {head}, and from '{tail_source}' to '{tail_target}'."

    def _describe_multiple_annotations(
        self,
        annotations: list[OCRAnnotation],
        added_texts: list[str],
    ) -> str:
        rendered: list[str] = []
        for text in added_texts:
            annotation = self._find_annotation(annotations, text)
            if annotation is not None and annotation.anchor_text:
                rendered.append(f"'{annotation.text}' near '{annotation.anchor_text}'")
            else:
                rendered.append(f"'{text}'")

        if len(rendered) == 1:
            return f"Text {rendered[0]} was added to the whiteboard."
        if len(rendered) == 2:
            return f"Text {rendered[0]} and {rendered[1]} were added to the whiteboard."
        head = ", ".join(rendered[:-1])
        return f"Text {head}, and {rendered[-1]} were added to the whiteboard."


class VisualDeltaPipeline:
    """End-to-end pipeline from live image feed to plain-text visual_delta."""

    def __init__(
        self,
        *,
        frame_processor: FrameProcessor | None = None,
        ocr_extractor: OCRExtractor | None = None,
        visual_delta_describer: VisualDeltaDescriber | None = None,
    ) -> None:
        self.frame_processor = frame_processor or FrameProcessor()
        self.ocr_extractor = ocr_extractor or OCRExtractor()
        self.visual_delta_describer = visual_delta_describer or VisualDeltaDescriber()
        self.last_snapshot: OCRSnapshot | None = None

    def process_frame(self, image: bytes | np.ndarray, timestamp: float | int) -> dict | None:
        accepted = self.frame_processor.process_frame(image, timestamp)
        if accepted is None:
            return None

        snapshot = self.ocr_extractor.extract(accepted["image"])
        visual_delta = self.visual_delta_describer.describe(self.last_snapshot, snapshot)
        self.last_snapshot = snapshot

        if visual_delta is None:
            return None

        return {
            "timestamp": timestamp,
            "image": accepted["image"],
            "visual_delta": visual_delta,
            "labels": [label.text for label in snapshot.components],
            "annotations": [annotation.text for annotation in snapshot.annotations],
            "connections": snapshot.connections,
        }
