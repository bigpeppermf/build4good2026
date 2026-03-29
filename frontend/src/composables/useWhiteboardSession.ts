import { computed, nextTick, onUnmounted, ref, shallowRef } from "vue";

import { apiUrl } from "../utils/apiUrl";

/** Still frames from the webcam (not video stream). */
const IMAGE_INTERVAL_MS = 15_000;

const JPEG_QUALITY = 0.82;
const EXPORT_MAX_WIDTH = 1280;

/** Normalized crop rect over the video (0–1), from the adjustable frame UI. */
export interface FrameCropNorm {
  left: number;
  top: number;
  width: number;
  height: number;
}

function defaultFrameCrop(): FrameCropNorm {
  return { left: 0.06, top: 0.08, width: 0.88, height: 0.72 };
}

export interface VerbalResponseItem {
  timestampMs: number;
  verbalResponse: string;
  visualDelta?: string;
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

/**
 * Map normalized crop (0–1 relative to the video *element* box, same as the overlay)
 * into source pixel rect on the video bitmap. Accounts for CSS `object-fit: cover`,
 * which scales and centers the stream so the element is filled — naive left*videoWidth
 * would not match what you see on screen.
 */
function coverCropToVideoPixels(
  video: HTMLVideoElement,
  crop: FrameCropNorm,
): { sx: number; sy: number; sw: number; sh: number } | null {
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (vw <= 0 || vh <= 0) {
    return null;
  }

  const rect = video.getBoundingClientRect();
  const elW = rect.width;
  const elH = rect.height;
  if (elW <= 0 || elH <= 0) {
    return null;
  }

  const scale = Math.max(elW / vw, elH / vh);
  const wVis = elW / scale;
  const hVis = elH / scale;
  const x0 = (vw - wVis) / 2;
  const y0 = (vh - hVis) / 2;

  let sx = x0 + crop.left * wVis;
  let sy = y0 + crop.top * hVis;
  let sw = crop.width * wVis;
  let sh = crop.height * hVis;

  sx = Math.round(sx);
  sy = Math.round(sy);
  sw = Math.round(sw);
  sh = Math.round(sh);

  sx = clamp(sx, 0, vw - 1);
  sy = clamp(sy, 0, vh - 1);
  sw = clamp(sw, 1, vw - sx);
  sh = clamp(sh, 1, vh - sy);

  return { sx, sy, sw, sh };
}

function captureJpegFromVideo(
  video: HTMLVideoElement,
  crop: FrameCropNorm,
): Promise<Blob | null> {
  const src = coverCropToVideoPixels(video, crop);
  if (!src) {
    return Promise.resolve(null);
  }
  const { sx, sy, sw, sh } = src;

  const scale = Math.min(1, EXPORT_MAX_WIDTH / sw);
  const cw = Math.round(sw * scale);
  const ch = Math.round(sh * scale);

  const canvas = document.createElement("canvas");
  canvas.width = cw;
  canvas.height = ch;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    return Promise.resolve(null);
  }
  ctx.drawImage(video, sx, sy, sw, sh, 0, 0, cw, ch);

  return new Promise((resolve) => {
    canvas.toBlob(
      (blob) => resolve(blob),
      "image/jpeg",
      JPEG_QUALITY,
    );
  });
}

export function useWhiteboardSession() {
  const videoRef = ref<HTMLVideoElement | null>(null);

  const activeStream = shallowRef<MediaStream | null>(null);
  const isSettingUp = ref(false);
  const isBeginningSession = ref(false);
  const isSessionActive = ref(false);
  const errorMessage = ref<string | null>(null);

  const uploadMessage = ref<string | null>(null);
  const uploadOk = ref<boolean | null>(null);
  const uploadState = ref<"idle" | "uploading" | "done">("idle");

  /** Normalized region used for JPEG capture (shared with setup UI). */
  const frameCropNorm = ref<FrameCropNorm>(defaultFrameCrop());

  /** Backend graph session (POST /new-session) — set when user taps Start session. */
  const sessionId = ref<string | null>(null);
  const verbalResponses = ref<VerbalResponseItem[]>([]);
  const lastCaptureError = ref<string | null>(null);

  /** Set from each still-image interval once the backend responds (UI border feedback). */
  const lastCaptureProcessStatus = ref<"idle" | "success" | "error">("idle");

  const imageFramesSentCount = ref(0);

  const sessionElapsedMs = ref(0);
  let sessionTimerId: ReturnType<typeof setInterval> | null = null;

  const sessionTimeLabel = computed(() => {
    const totalSec = Math.floor(sessionElapsedMs.value / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  });

  let imageSeq = 0;

  let imageIntervalId: ReturnType<typeof setInterval> | null = null;

  function clearSessionTimer() {
    if (sessionTimerId !== null) {
      clearInterval(sessionTimerId);
      sessionTimerId = null;
    }
  }

  function clearImageInterval() {
    if (imageIntervalId !== null) {
      clearInterval(imageIntervalId);
      imageIntervalId = null;
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

  function stopTimersAndIntervals() {
    clearSessionTimer();
    clearImageInterval();
  }

  function teardownStream() {
    stopTimersAndIntervals();
    activeStream.value?.getTracks().forEach((t) => t.stop());
    activeStream.value = null;
    if (videoRef.value) {
      videoRef.value.srcObject = null;
    }
  }

  function startImageInterval() {
    clearImageInterval();
    imageIntervalId = window.setInterval(() => {
      void captureAndSendImage();
    }, IMAGE_INTERVAL_MS);
  }

  async function captureAndSendImage() {
    const video = videoRef.value;
    if (!video || !isSessionActive.value || !sessionId.value) {
      return;
    }
    const blob = await captureJpegFromVideo(video, frameCropNorm.value);
    if (!blob || blob.size === 0) {
      lastCaptureError.value =
        "Could not read pixels for this frame (camera may still be starting).";
      lastCaptureProcessStatus.value = "error";
      return;
    }
    imageSeq += 1;
    const timestampMs = Math.round(sessionElapsedMs.value);
    lastCaptureError.value = null;

    const form = new FormData();
    form.append("session_id", sessionId.value);
    form.append("timestamp_ms", String(timestampMs));
    form.append("frame", blob, "frame.jpg");

    try {
      const res = await fetch(apiUrl("/agent/process-capture"), {
        method: "POST",
        body: form,
      });
      const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;

      if (!res.ok) {
        const err =
          typeof data.error === "string" ? data.error : `Capture failed (${res.status})`;
        lastCaptureError.value = err;
        lastCaptureProcessStatus.value = "error";
        return;
      }

      imageFramesSentCount.value += 1;

      if (data.discarded === true) {
        lastCaptureProcessStatus.value = "success";
        return;
      }

      const verbal =
        typeof data.verbal_response === "string" ? data.verbal_response : "";
      const vd =
        typeof data.visual_delta === "string" ? data.visual_delta : undefined;

      if (verbal) {
        verbalResponses.value = [
          ...verbalResponses.value,
          {
            timestampMs: timestampMs,
            verbalResponse: verbal,
            visualDelta: vd,
          },
        ];
      }

      lastCaptureProcessStatus.value = "success";
    } catch {
      lastCaptureError.value = "Network error while uploading frame.";
      lastCaptureProcessStatus.value = "error";
    }
  }

  async function finalizeSession() {
    const sid = sessionId.value;
    isSessionActive.value = false;
    isBeginningSession.value = false;
    stopTimersAndIntervals();
    lastCaptureProcessStatus.value = "idle";

    if (!sid) {
      teardownStream();
      return;
    }

    uploadState.value = "uploading";
    try {
      const res = await fetch(apiUrl("/end-session"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sid }),
      });
      const data = (await res.json().catch(() => ({}))) as Record<
        string,
        unknown
      >;
      if (res.ok) {
        uploadOk.value = true;
        uploadMessage.value =
          typeof data.status === "string"
            ? `Session ended and saved (${data.status}).`
            : "Session ended and saved.";
      } else {
        uploadOk.value = false;
        uploadMessage.value =
          typeof data.error === "string"
            ? data.error
            : "Could not save session on the server.";
      }
    } catch {
      uploadOk.value = false;
      uploadMessage.value =
        "Could not reach the server to end the session.";
    }
    sessionId.value = null;
    uploadState.value = "done";
    teardownStream();
  }

  /** Camera preview only — no backend session yet. */
  async function openCameraSetup() {
    errorMessage.value = null;
    uploadMessage.value = null;
    uploadOk.value = null;
    uploadState.value = "idle";
    lastCaptureError.value = null;
    lastCaptureProcessStatus.value = "idle";
    verbalResponses.value = [];
    imageSeq = 0;
    imageFramesSentCount.value = 0;
    sessionId.value = null;
    frameCropNorm.value = defaultFrameCrop();
    stopTimersAndIntervals();
    sessionElapsedMs.value = 0;

    if (!navigator.mediaDevices?.getUserMedia) {
      errorMessage.value =
        "Camera access is not available in this browser or context. Try HTTPS or localhost.";
      return;
    }

    if (activeStream.value || isSettingUp.value) {
      return;
    }

    isSettingUp.value = true;

    let stream: MediaStream | null = null;

    try {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            facingMode: { ideal: "environment" },
            width: { ideal: 1280 },
            height: { ideal: 720 },
          },
        });
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({
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
    } catch (e) {
      sessionId.value = null;
      clearImageInterval();
      teardownStream();
      isSessionActive.value = false;
      errorMessage.value =
        e instanceof Error
          ? e.message
          : "Could not start camera.";
    } finally {
      isSettingUp.value = false;
    }
  }

  /** POST /new-session, timer, and capture interval — call after framing the shot. */
  async function beginSession() {
    if (!activeStream.value || isSessionActive.value || isBeginningSession.value) {
      return;
    }

    errorMessage.value = null;
    lastCaptureError.value = null;
    lastCaptureProcessStatus.value = "idle";
    verbalResponses.value = [];
    imageSeq = 0;
    imageFramesSentCount.value = 0;
    sessionElapsedMs.value = 0;
    stopTimersAndIntervals();

    isBeginningSession.value = true;

    try {
      const nsRes = await fetch(apiUrl("/new-session"), { method: "POST" });
      if (!nsRes.ok) {
        throw new Error(
          "Could not create a backend session (is the API running on port 8000?)",
        );
      }
      const nsJson = (await nsRes.json()) as { session_id?: string };
      if (!nsJson.session_id) {
        throw new Error("Invalid response from new-session.");
      }
      sessionId.value = nsJson.session_id;
      isSessionActive.value = true;
      startSessionTimer();
      startImageInterval();
    } catch (e) {
      sessionId.value = null;
      isSessionActive.value = false;
      errorMessage.value =
        e instanceof Error
          ? e.message
          : "Could not start session.";
    } finally {
      isBeginningSession.value = false;
    }
  }

  function stopSession() {
    void finalizeSession();
  }

  onUnmounted(() => {
    if (sessionId.value || isSessionActive.value) {
      void finalizeSession();
    } else {
      teardownStream();
    }
  });

  return {
    videoRef,
    activeStream,
    isSettingUp,
    isBeginningSession,
    isSessionActive,
    errorMessage,
    uploadMessage,
    uploadOk,
    uploadState,
    frameCropNorm,
    sessionId,
    verbalResponses,
    lastCaptureError,
    lastCaptureProcessStatus,
    imageFramesSentCount,
    sessionElapsedMs,
    sessionTimeLabel,
    openCameraSetup,
    beginSession,
    stopSession,
  };
}
