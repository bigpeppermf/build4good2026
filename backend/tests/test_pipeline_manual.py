"""
Quick manual test for the Gemini Vision pipeline using a synthetic whiteboard image.

Run from the backend directory:
    uv run python tests/test_pipeline_manual.py

Requires GOOGLE_API_KEY in .env (Gemini Vision API).
"""

import sys
from pathlib import Path

# Ensure backend packages are importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np
from dotenv import load_dotenv

load_dotenv()


def make_fake_whiteboard() -> np.ndarray:
    """Draw a simple whiteboard with two labeled boxes and an arrow.

    Uses large text so Gemini Vision can reliably read the labels.
    """
    img = np.full((720, 1280, 3), 255, dtype=np.uint8)

    # Box 1: "Frontend"
    cv2.rectangle(img, (60, 180), (480, 420), (0, 0, 0), 2)
    cv2.putText(img, "Frontend", (90, 340), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 3)

    # Box 2: "Database"
    cv2.rectangle(img, (700, 180), (1200, 420), (0, 0, 0), 2)
    cv2.putText(img, "Database", (730, 340), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 0), 3)

    # Arrow from box 1 to box 2
    cv2.arrowedLine(img, (480, 300), (700, 300), (0, 0, 0), 2, tipLength=0.04)

    return img


def main():
    print("=== Gemini Vision Pipeline Manual Test ===\n")

    # --- Step 1: Generate test image ---
    img = make_fake_whiteboard()
    ok, jpg_bytes = cv2.imencode(".jpg", img)
    assert ok, "Failed to encode test image"
    jpg = jpg_bytes.tobytes()
    print(f"1. Generated fake whiteboard image ({len(jpg)} bytes JPEG)\n")

    # Save a copy so you can visually inspect it
    out_path = Path(__file__).parent / "test_whiteboard.jpg"
    cv2.imwrite(str(out_path), img)
    print(f"   Saved to: {out_path}\n")

    # --- Step 2: Test Gemini Vision extraction directly ---
    print("2. Running Gemini Vision extraction (first frame)...")
    from core.visual_delta_pipeline import GeminiVisionExtractor

    extractor = GeminiVisionExtractor()
    description = extractor.describe_frame(jpg, previous_description=None)
    print(f"   Description: {description}\n")

    # --- Step 3: Test frame processor (no person, should accept) ---
    print("3. Running frame processor...")
    from core.frame_processor import FrameProcessor

    fp = FrameProcessor()
    result = fp.process_frame(jpg, timestamp=0)
    if result is None:
        print("   REJECTED (person detected or too similar)\n")
    else:
        print(f"   ACCEPTED (output {len(result['image'])} bytes)\n")

    # --- Step 4: Test full pipeline ---
    print("4. Running full VisualDeltaPipeline...")
    from core.visual_delta_pipeline import VisualDeltaPipeline

    pipeline = VisualDeltaPipeline()

    # First frame
    result1 = pipeline.process_frame(jpg, timestamp=0)
    if result1 is None:
        print("   Frame 1: no delta produced (discarded or blank board)")
    else:
        print(f"   Frame 1 visual_delta: {result1['visual_delta']}")

    # Second identical frame (should be discarded as too similar by FrameProcessor)
    print()
    result2 = pipeline.process_frame(jpg, timestamp=15000)
    if result2 is None:
        print("   Frame 2 (identical): correctly discarded (no change)")
    else:
        print(f"   Frame 2 visual_delta: {result2['visual_delta']}")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
