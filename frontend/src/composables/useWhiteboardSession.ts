import { computed, nextTick, onUnmounted, ref, shallowRef } from "vue";

import { apiUrl } from "../utils/apiUrl";

/** Still frames from the webcam (not video stream). */
const IMAGE_INTERVAL_MS = 15_000;

const JPEG_QUALITY = 0.82;
const EXPORT_MAX_WIDTH = 1280;
const DEFAULT_AUDIO_MIME_TYPE = "audio/webm";
const AUDIO_MIME_CANDIDATES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/ogg;codecs=opus",
  "audio/ogg",
] as const;

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

function preferredAudioMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") {
    return null;
  }

  if (typeof MediaRecorder.isTypeSupported !== "function") {
    return AUDIO_MIME_CANDIDATES[0];
  }

  for (const candidate of AUDIO_MIME_CANDIDATES) {
    if (MediaRecorder.isTypeSupported(candidate)) {
      return candidate;
    }
  }

  return null;
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
  const mediaRecorder = ref<MediaRecorder | null>(null);
  const audioChunks = ref<Blob[]>([]);
  const audioBlob = ref<Blob | null>(null);
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
  const lastCompletedSessionId = ref<string | null>(null);
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
    if (mediaRecorder.value && mediaRecorder.value.state !== "inactive") {
      try {
        mediaRecorder.value.stop();
      } catch {
        // no-op: if the recorder is already stopping, this can throw.
      }
    }
    mediaRecorder.value = null;
    activeStream.value?.getTracks().forEach((t) => t.stop());
    activeStream.value = null;
    if (videoRef.value) {
      videoRef.value.srcObject = null;
    }
  }

  function currentAudioMimeType(recorder: MediaRecorder | null): string {
    const mime = recorder?.mimeType?.trim();
    if (mime) {
      return mime;
    }
    return preferredAudioMimeType() ?? DEFAULT_AUDIO_MIME_TYPE;
  }

  function buildAudioBlob(recorder: MediaRecorder | null): Blob {
    return new Blob(audioChunks.value, { type: currentAudioMimeType(recorder) });
  }

  async function startAudioRecorder(stream: MediaStream) {
    if (typeof MediaRecorder === "undefined") {
      throw new Error("MediaRecorder is not supported in this browser.");
    }

    const audioTracks = stream.getAudioTracks();
    if (audioTracks.length === 0) {
      throw new Error(
        "Microphone access is required. Please allow microphone permissions and try again.",
      );
    }

    const recordingStream =
      typeof MediaStream === "undefined"
        ? stream
        : new MediaStream(audioTracks);
    const mimeType = preferredAudioMimeType();

    const recorder = mimeType
      ? new MediaRecorder(recordingStream, { mimeType })
      : new MediaRecorder(recordingStream);

    audioChunks.value = [];
    audioBlob.value = null;

    recorder.ondataavailable = (event: BlobEvent) => {
      if (event.data.size > 0) {
        audioChunks.value = [...audioChunks.value, event.data];
      }
    };

    recorder.start();
    mediaRecorder.value = recorder;
  }

  async function finalizeAudio(): Promise<Blob> {
    const recorder = mediaRecorder.value;

    if (!recorder) {
      if (!audioBlob.value) {
        audioBlob.value = new Blob([], { type: DEFAULT_AUDIO_MIME_TYPE });
      }
      return audioBlob.value;
    }

    if (recorder.state === "inactive") {
      if (!audioBlob.value) {
        audioBlob.value = buildAudioBlob(recorder);
      }
      return audioBlob.value;
    }

    return new Promise((resolve) => {
      const previousOnStop = recorder.onstop;
      recorder.onstop = (event: Event) => {
        if (typeof previousOnStop === "function") {
          previousOnStop.call(recorder, event);
        }
        const blob = buildAudioBlob(recorder);
        audioBlob.value = blob;
        resolve(blob);
      };
      recorder.stop();
    });
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
    lastCompletedSessionId.value = null;
    try {
      const finalizedAudio = await finalizeAudio();
      const form = new FormData();
      form.append("session_id", sid);
      form.append(
        "audio",
        finalizedAudio,
        finalizedAudio.type.includes("ogg") ? "session-audio.ogg" : "session-audio.webm",
      );

      const res = await fetch(apiUrl("/end-session"), {
        method: "POST",
        body: form,
      });
      const data = (await res.json().catch(() => ({}))) as Record<
        string,
        unknown
      >;
      if (res.ok) {
        const completedSid =
          typeof data.session_id === "string" && data.session_id.trim()
            ? data.session_id
            : sid;
        lastCompletedSessionId.value = completedSid;
        uploadOk.value = true;
        uploadMessage.value =
          typeof data.status === "string"
            ? `Session ended (${data.status}).`
            : "Session ended.";
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
    lastCompletedSessionId.value = null;
    mediaRecorder.value = null;
    audioChunks.value = [];
    audioBlob.value = null;
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
          audio: {
            echoCancellation: { ideal: true },
            noiseSuppression: { ideal: true },
            autoGainControl: { ideal: true },
          },
        });
      } catch {
        stream = await navigator.mediaDevices.getUserMedia({
          video: true,
          audio: true,
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
    lastCompletedSessionId.value = null;
    audioChunks.value = [];
    audioBlob.value = null;
    mediaRecorder.value = null;
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
      await startAudioRecorder(activeStream.value);
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
    mediaRecorder,
    audioChunks,
    audioBlob,
    isSettingUp,
    isBeginningSession,
    isSessionActive,
    errorMessage,
    uploadMessage,
    uploadOk,
    uploadState,
    frameCropNorm,
    sessionId,
    lastCompletedSessionId,
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
