# Tests

## Visual Delta Pipeline Stream Test

This test harness exercises the full backend visual-delta pipeline:

- live image feed from a folder of frames
- valid-frame filtering
- OCR extraction
- change description
- plain-text `visual_delta` output to a text file

It does not call graph mutation or the HTTP server.

### Why this is a good Mac-side test

It isolates the exact pipeline you just asked for:

- incoming frame images
- valid frame selection
- OCR on accepted frames
- short visual change descriptions written to a text file

That makes it a good first test while you are wiring up your Mac stream and before graph mutation is involved.

### Input format

The script reads `.jpg`, `.jpeg`, or `.png` files from a folder in sorted order.

### Run once on a folder of frames

```bash
python3 tests/visual_delta_pipeline_stream_test.py --frames-dir tests/input_frames
```

This writes output to:

```text
tests/output/visual_delta_log.txt
```

### Follow mode for a live-ish local stream

If you have another process on your Mac continuously saving frames into a folder, you can keep this test running in follow mode:

```bash
python3 tests/visual_delta_pipeline_stream_test.py --frames-dir tests/input_frames --output tests/output/live_visual_delta_log.txt --follow
```

Each accepted frame with a detected structural change appends one line to the output text file.

### Practical setup idea for your Mac stream

If your Mac stream pipeline saves frames to disk, point it at `tests/input_frames/` or another folder and let this test harness watch that directory. It will continuously turn accepted frames into plain-English `visual_delta` lines in a text file.

That gives you a simple debug loop:

1. Stream or capture frames
2. Save them into a folder
3. Let the pipeline OCR and compare them
4. Watch `tests/output/live_visual_delta_log.txt`
