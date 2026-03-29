"""Visual-delta pipeline for live whiteboard frames.

Uses Google Gemini Vision API to analyse whiteboard images and describe
changes between consecutive frames.  Replaces the old Tesseract OCR
approach with a single multimodal LLM call per accepted frame.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import cv2
import numpy as np
from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from .frame_processor import FrameProcessor

# ------------------------------------------------------------------ #
# Gemini vision prompts                                                #
# ------------------------------------------------------------------ #

_FIRST_FRAME_PROMPT = """\
You are analysing a whiteboard photo from a system design interview.

Describe every visible component (boxes, labels, text), every arrow or
connection between components, and any annotation text you can read.

Reply with a short, factual paragraph. Use the exact text you see on the
board — do not invent labels. If the board is blank or unreadable, reply
with exactly: BLANK"""

_DELTA_PROMPT_TEMPLATE = """\
You are analysing two consecutive whiteboard photos from a system design
interview.

Previous frame description:
{previous_description}

Look at the NEW photo and describe ONLY what changed compared to the
previous description. Focus on:
- New boxes or labels that appeared
- Boxes or labels that were removed or renamed
- New arrows or connections
- Removed arrows or connections
- New annotation text

Reply with a short, factual sentence or two describing the changes.
Use the exact text you see on the board. If nothing meaningful changed,
reply with exactly: NO_CHANGE"""


class GeminiVisionExtractor:
    """Use Gemini Vision to describe whiteboard contents from a frame."""

    def __init__(
        self,
        *,
        model_name: str = "gemini-2.5-flash-lite",
        temperature: float = 0,
    ) -> None:
        self._llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            google_api_key=os.environ.get("GOOGLE_API_KEY", ""),
        )

    def describe_frame(
        self,
        image_bytes: bytes,
        previous_description: str | None = None,
    ) -> str | None:
        """Analyse a frame and return a visual delta description.

        Args:
            image_bytes: JPEG-encoded image.
            previous_description: Description from the last accepted frame,
                or ``None`` for the first frame.

        Returns:
            A plain-English description of what is on / changed on the board,
            or ``None`` if the board is blank or nothing changed.
        """
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")

        if previous_description is None:
            prompt_text = _FIRST_FRAME_PROMPT
        else:
            prompt_text = _DELTA_PROMPT_TEMPLATE.format(
                previous_description=previous_description,
            )

        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                },
            ],
        )

        response = self._llm.invoke([message])
        text = (response.content or "").strip()

        if not text or text.upper() in ("BLANK", "NO_CHANGE"):
            return None

        return text


class VisualDeltaPipeline:
    """End-to-end pipeline from live image feed to plain-text visual_delta.

    1. ``FrameProcessor`` gates frames (person detection + dedup).
    2. ``GeminiVisionExtractor`` describes what changed via the Vision API.
    """

    def __init__(
        self,
        *,
        frame_processor: FrameProcessor | None = None,
        vision_extractor: GeminiVisionExtractor | None = None,
    ) -> None:
        self.frame_processor = frame_processor or FrameProcessor()
        self.vision_extractor = vision_extractor or GeminiVisionExtractor()
        self._last_description: str | None = None

    def process_frame(
        self, image: bytes | np.ndarray, timestamp: float | int
    ) -> dict[str, Any] | None:
        """Run one frame through the full pipeline.

        Returns a result dict on success, or ``None`` if the frame was
        discarded (person visible, duplicate, blank board, or no change).
        """
        accepted = self.frame_processor.process_frame(image, timestamp)
        if accepted is None:
            return None

        image_bytes: bytes = accepted["image"]
        visual_delta = self.vision_extractor.describe_frame(
            image_bytes,
            previous_description=self._last_description,
        )

        if visual_delta is None:
            return None

        # Keep a rolling description for the next delta comparison.
        if self._last_description is None:
            # First frame — the full description becomes our baseline.
            self._last_description = visual_delta
        else:
            # Append the delta so cumulative context grows.
            self._last_description = (
                f"{self._last_description}\n\nLatest change: {visual_delta}"
            )

        return {
            "timestamp": timestamp,
            "image": image_bytes,
            "visual_delta": visual_delta,
        }
