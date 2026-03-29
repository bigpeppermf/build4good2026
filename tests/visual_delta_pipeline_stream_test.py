"""Watch a folder of frames and append visual_delta lines to a text file."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from core.visual_delta_pipeline import VisualDeltaPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the visual-delta pipeline on a folder of frames.")
    parser.add_argument("--frames-dir", default="tests/input_frames", help="Folder containing jpg/png frames.")
    parser.add_argument("--output", default="tests/output/visual_delta_log.txt", help="Text file for visual_delta output.")
    parser.add_argument("--follow", action="store_true", help="Keep watching for new frames.")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Seconds between folder scans in follow mode.")
    return parser.parse_args()


def append_visual_delta(output_path: Path, timestamp_ms: int, visual_delta: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[{timestamp_ms}ms] {visual_delta}\n")


def iter_frame_paths(frames_dir: Path) -> list[Path]:
    patterns = ("*.jpg", "*.jpeg", "*.png")
    paths: list[Path] = []
    for pattern in patterns:
        paths.extend(frames_dir.glob(pattern))
    return sorted(paths)


def run_stream(frames_dir: Path, output_path: Path, follow: bool, poll_interval: float) -> None:
    pipeline = VisualDeltaPipeline()
    seen: set[Path] = set()

    frames_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("", encoding="utf-8")

    while True:
        frame_paths = iter_frame_paths(frames_dir)
        for frame_path in frame_paths:
            if frame_path in seen:
                continue
            frame_bytes = frame_path.read_bytes()
            timestamp_ms = int(frame_path.stat().st_mtime * 1000)
            result = pipeline.process_frame(frame_bytes, timestamp_ms)
            if result is not None:
                append_visual_delta(output_path, timestamp_ms, result["visual_delta"])
            seen.add(frame_path)

        if not follow:
            break

        time.sleep(poll_interval)


def main() -> None:
    args = parse_args()
    run_stream(
        frames_dir=Path(args.frames_dir),
        output_path=Path(args.output),
        follow=args.follow,
        poll_interval=args.poll_interval,
    )


if __name__ == "__main__":
    main()
