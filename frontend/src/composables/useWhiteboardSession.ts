import { computed, nextTick, onUnmounted, ref, shallowRef } from "vue";

/** Downscaled analysis grid (speed over fidelity). */
const ANALYSIS_W = 160;
const ANALYSIS_H = 90;

/** Mean luminance delta (0–255) above which we treat the board as “active”. */
const MOTION_THRESHOLD = 14;

/** Minimum gap between snapshots so bursts of motion do not flood the server. */
const CAPTURE_COOLDOWN_MS = 1400;

const JPEG_QUALITY = 0.82;
const EXPORT_MAX_WIDTH = 1280;

export type CapturedFrame = {
  blob: Blob;
  timestampMs: number;
  motionMean: number;
};

function pickAudioMime(): string | undefined {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
  ];
  for (const t of candidates) {
    if (MediaRecorder.isTypeSupported(t)) {
      return t;
    }
  }
  return undefined;
}

function grayFromImageData(data: ImageData, out: Uint8Array): void {
  const { data: px, width, height } = data;
  let j = 0;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      const r = px[i];
      const g = px[i + 1];
      const b = px[i + 2];
      out[j++] = (r + r + g + g + g + b) / 6;
    }
  }
}

function meanAbsDiff(a: Uint8Array, b: Uint8Array): number {
  const n = Math.min(a.length, b.length);
  if (n === 0) {
    return 0;
  }
  let s = 0;
  for (let i = 0; i < n; i++) {
    s += Math.abs(a[i] - b[i]);
  }
  return s / n;
}

function captureJpegFromVideo(video: HTMLVideoElement): Promise<Blob | null> {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw <= 0 || vh <= 0) {
    return Promise.resolve(null);
  }

  const scale = Math.min(1, EXPORT_MAX_WIDTH / vw);
  const cw = Math.round(vw * scale);
  const ch = Math.round(vh * scale);

  const canvas = document.createElement("canvas");
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return Promise.resolve(null);
  }
  ctx.drawImage(video, 0, 0, cw, ch);

  return new Promise((resolve) => {
    canvas.toBlob(
      (blob) => resolve(blob),
      "image/jpeg",
      JPEG_QUALITY,
    );
  });
}

async function uploadPracticeSession(
  audio: Blob,
  frames: CapturedFrame[],
): Promise<{ ok: boolean; message: string }> {
  const fd = new FormData();
  fd.append(
    "audio",
    audio,
    audio.type.includes("webm") ? "session.webm" : "session.audio",
  );

  const meta = frames.map((f, i) => ({
    t: f.timestampMs,
    m: Math.round(f.motionMean * 100) / 100,
    i,
  }));
  fd.append("framesMeta", JSON.stringify(meta));

  frames.forEach((f, i) => {
    fd.append(`frame_${i}`, f.blob, `frame_${i}.jpg`);
  });

  try {
    const res = await fetch("/api/practice/upload", {
      method: "POST",
      body: fd,
    });
    if (res.ok) {
      return { ok: true, message: "Server accepted the session." };
    }
    if (res.status === 404) {
      return {
        ok: false,
        message:
          "Upload endpoint not implemented yet (404). Backend can add POST /api/practice/upload.",
      };
    }
    const text = await res.text().catch(() => "");
    return {
      ok: false,
      message: `Upload failed (${res.status})${text ? `: ${text.slice(0, 200)}` : ""}`,
    };
  } catch (e) {
    return {
      ok: false,
      message:
        e instanceof Error ? e.message : "Network error while uploading.",
    };
  }
}

export function useWhiteboardSession() {
  const videoRef = ref<HTMLVideoElement | null>(null);

  const activeStream = shallowRef<MediaStream | null>(null);
  const isSettingUp = ref(false);
  const isSessionActive = ref(false);
  const errorMessage = ref<string | null>(null);

  const capturedFrames = ref<CapturedFrame[]>([]);
  const lastMotionMean = ref(0);
  const uploadMessage = ref<string | null>(null);
  const uploadOk = ref<boolean | null>(null);
  const uploadState = ref<"idle" | "uploading" | "done">("idle");

  const audioPlaybackUrl = ref<string | null>(null);
  const thumbUrls = ref<string[]>([]);

  let audioRecorder: MediaRecorder | null = null;
  const audioChunks: Blob[] = [];
  let rafId = 0;

  const analysisCanvas = document.createElement("canvas");
  analysisCanvas.width = ANALYSIS_W;
  analysisCanvas.height = ANALYSIS_H;
  const analysisCtx = analysisCanvas.getContext("2d", {
    willReadFrequently: true,
  });

  const grayA = new Uint8Array(ANALYSIS_W * ANALYSIS_H);
  let prevGray: Uint8Array | null = null;
  let lastCaptureAt = 0;
  let captureBusy = false;
  let sessionStartPerf = 0;

  const sessionElapsedMs = ref(0);
  let sessionTimerId: ReturnType<typeof setInterval> | null = null;

  const sessionTimeLabel = computed(() => {
    const totalSec = Math.floor(sessionElapsedMs.value / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  });

  function clearSessionTimer() {
    if (sessionTimerId !== null) {
      clearInterval(sessionTimerId);
      sessionTimerId = null;
    }
  }

  function startSessionTimer() {
    clearSessionTimer();
    const t0 = Date.now();
    sessionElapsedMs.value = 0;
    sessionTimerId = setInterval(() => {
      sessionElapsedMs.value = Date.now() - t0;
    }, 250);
  }

  function revokeAudioUrl() {
    if (audioPlaybackUrl.value) {
      URL.revokeObjectURL(audioPlaybackUrl.value);
      audioPlaybackUrl.value = null;
    }
  }

  function revokeThumbs() {
    thumbUrls.value.forEach((u) => URL.revokeObjectURL(u));
    thumbUrls.value = [];
  }

  function stopMotionLoop() {
    if (rafId) {
      cancelAnimationFrame(rafId);
      rafId = 0;
    }
    prevGray = null;
    lastCaptureAt = 0;
    captureBusy = false;
    clearSessionTimer();
  }

  function teardownStream() {
    stopMotionLoop();
    activeStream.value?.getTracks().forEach((t) => t.stop());
    activeStream.value = null;
    if (videoRef.value) {
      videoRef.value.srcObject = null;
    }
  }

  function tickMotion() {
    const video = videoRef.value;
    const stream = activeStream.value;
    if (!video || !stream || !analysisCtx || !isSessionActive.value) {
      return;
    }
    if (video.readyState < 2 || video.videoWidth <= 0) {
      rafId = requestAnimationFrame(tickMotion);
      return;
    }

    analysisCtx.drawImage(video, 0, 0, ANALYSIS_W, ANALYSIS_H);
    const snapshot = analysisCtx.getImageData(0, 0, ANALYSIS_W, ANALYSIS_H);
    grayFromImageData(snapshot, grayA);

    if (prevGray !== null) {
      const motion = meanAbsDiff(prevGray, grayA);
      lastMotionMean.value = motion;

      const now = performance.now();
      if (
        motion >= MOTION_THRESHOLD &&
        now - lastCaptureAt >= CAPTURE_COOLDOWN_MS &&
        !captureBusy
      ) {
        lastCaptureAt = now;
        captureBusy = true;
        const motionSnapshot = motion;
        const timeSnapshot = now;
        captureJpegFromVideo(video).then((blob) => {
          captureBusy = false;
          if (blob && blob.size > 0 && isSessionActive.value) {
            capturedFrames.value = [
              ...capturedFrames.value,
              {
                blob,
                timestampMs: Math.round(timeSnapshot - sessionStartPerf),
                motionMean: motionSnapshot,
              },
            ];
          }
        });
      }
    }

    if (!prevGray || prevGray.length !== grayA.length) {
      prevGray = new Uint8Array(grayA.length);
    }
    prevGray.set(grayA);

    rafId = requestAnimationFrame(tickMotion);
  }

  async function startSession() {
    errorMessage.value = null;
    uploadMessage.value = null;
    uploadOk.value = null;
    uploadState.value = "idle";
    revokeAudioUrl();
    revokeThumbs();
    capturedFrames.value = [];
    audioChunks.length = 0;
    stopMotionLoop();
    sessionElapsedMs.value = 0;

    if (!navigator.mediaDevices?.getUserMedia) {
      errorMessage.value =
        "Camera access is not available in this browser or context. Try HTTPS or localhost.";
      return;
    }

    if (isSessionActive.value || isSettingUp.value) {
      return;
    }

    isSettingUp.value = true;

    let stream: MediaStream | null = null;

    try {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        });
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: true,
          video: true,
        });
      }
      activeStream.value = stream;

      await nextTick();
      const el = videoRef.value;
      if (el) {
        el.srcObject = stream;
        await el.play().catch(() => undefined);
      }

      const audioOnly = new MediaStream(stream.getAudioTracks());
      const mime = pickAudioMime();
      const rec = mime
        ? new MediaRecorder(audioOnly, { mimeType: mime })
        : new MediaRecorder(audioOnly);

      rec.ondataavailable = (e) => {
        if (e.data.size > 0) {
          audioChunks.push(e.data);
        }
      };

      rec.onstop = async () => {
        const audioBlob = new Blob(audioChunks, {
          type: rec.mimeType || "audio/webm",
        });
        revokeAudioUrl();
        audioPlaybackUrl.value = URL.createObjectURL(audioBlob);

        uploadState.value = "uploading";
        const result = await uploadPracticeSession(
          audioBlob,
          capturedFrames.value,
        );
        uploadState.value = "done";
        uploadMessage.value = result.message;
        uploadOk.value = result.ok;

        revokeThumbs();
        thumbUrls.value = capturedFrames.value.map((f) =>
          URL.createObjectURL(f.blob),
        );

        teardownStream();
        isSessionActive.value = false;
        audioRecorder = null;
      };

      audioRecorder = rec;
      rec.start(1000);
      isSessionActive.value = true;
      sessionStartPerf = performance.now();
      startSessionTimer();
      prevGray = null;
      rafId = requestAnimationFrame(tickMotion);
    } catch (e) {
      teardownStream();
      isSessionActive.value = false;
      audioRecorder = null;
      errorMessage.value =
        e instanceof Error
          ? e.message
          : "Could not access the camera or microphone.";
    } finally {
      isSettingUp.value = false;
    }
  }

  function stopSession() {
    stopMotionLoop();
    const rec = audioRecorder;
    if (rec && rec.state !== "inactive") {
      rec.stop();
    } else {
      teardownStream();
      isSessionActive.value = false;
    }
  }

  onUnmounted(() => {
    clearSessionTimer();
    stopMotionLoop();
    if (audioRecorder && audioRecorder.state !== "inactive") {
      audioRecorder.onstop = null;
      audioRecorder.stop();
    }
    audioRecorder = null;
    teardownStream();
    isSessionActive.value = false;
    revokeAudioUrl();
    revokeThumbs();
  });

  return {
    videoRef,
    activeStream,
    isSettingUp,
    isSessionActive,
    errorMessage,
    capturedFrames,
    lastMotionMean,
    uploadMessage,
    uploadOk,
    uploadState,
    audioPlaybackUrl,
    thumbUrls,
    sessionElapsedMs,
    sessionTimeLabel,
    startSession,
    stopSession,
  };
}
