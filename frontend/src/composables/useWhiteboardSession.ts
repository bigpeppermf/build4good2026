import { computed, nextTick, onUnmounted, ref, shallowRef } from "vue";

import { apiUrl } from "../utils/apiUrl";

/** Full audio stream: MediaRecorder timeslice (encode chunks to backend). */
const AUDIO_SLICE_MS = 500;

/** Still frames from the webcam (not video stream). */
const IMAGE_INTERVAL_MS = 15_000;

const JPEG_QUALITY = 0.82;
const EXPORT_MAX_WIDTH = 1280;

export interface VerbalResponseItem {
  timestampMs: number;
  verbalResponse: string;
  visualDelta?: string;
}

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

function speakVerbal(text: string, enabled: boolean) {
  if (!enabled || !text.trim()) {
    return;
  }
  if (typeof window === "undefined" || !window.speechSynthesis) {
    return;
  }
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = "en-US";
  window.speechSynthesis.speak(u);
}

export function useWhiteboardSession() {
  const videoRef = ref<HTMLVideoElement | null>(null);

  const activeStream = shallowRef<MediaStream | null>(null);
  const isSettingUp = ref(false);
  const isSessionActive = ref(false);
  const errorMessage = ref<string | null>(null);

  const uploadMessage = ref<string | null>(null);
  const uploadOk = ref<boolean | null>(null);
  const uploadState = ref<"idle" | "uploading" | "done">("idle");

  const sessionPlaybackUrl = ref<string | null>(null);

  /** Backend graph session (POST /new-session). */
  const sessionId = ref<string | null>(null);
  const verbalResponses = ref<VerbalResponseItem[]>([]);
  const ttsEnabled = ref(true);
  const lastCaptureError = ref<string | null>(null);

  const audioChunksRecordedCount = ref(0);
  const imageFramesSentCount = ref(0);

  const sessionElapsedMs = ref(0);
  let sessionTimerId: ReturnType<typeof setInterval> | null = null;

  const sessionTimeLabel = computed(() => {
    const totalSec = Math.floor(sessionElapsedMs.value / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  });

  let mediaRecorder: MediaRecorder | null = null;
  const audioChunksLocal: Blob[] = [];

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

  function revokeSessionPlaybackUrl() {
    if (sessionPlaybackUrl.value) {
      URL.revokeObjectURL(sessionPlaybackUrl.value);
      sessionPlaybackUrl.value = null;
    }
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
    const blob = await captureJpegFromVideo(video);
    if (!blob || blob.size === 0) {
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
        return;
      }

      imageFramesSentCount.value += 1;

      if (data.discarded === true) {
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
        speakVerbal(verbal, ttsEnabled.value);
      }
    } catch {
      lastCaptureError.value = "Network error while uploading frame.";
    }
  }

  async function startSession() {
    errorMessage.value = null;
    uploadMessage.value = null;
    uploadOk.value = null;
    uploadState.value = "idle";
    lastCaptureError.value = null;
    verbalResponses.value = [];
    revokeSessionPlaybackUrl();
    audioChunksLocal.length = 0;
    imageSeq = 0;
    audioChunksRecordedCount.value = 0;
    imageFramesSentCount.value = 0;
    sessionId.value = null;
    stopTimersAndIntervals();
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
      const nsRes = await fetch(apiUrl("/new-session"), { method: "POST" });
      if (!nsRes.ok) {
        throw new Error("Could not create a backend session (is the API running on port 8000?)");
      }
      const nsJson = (await nsRes.json()) as { session_id?: string };
      if (!nsJson.session_id) {
        throw new Error("Invalid response from new-session.");
      }
      sessionId.value = nsJson.session_id;

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
        if (e.data.size === 0) {
          return;
        }
        audioChunksLocal.push(e.data);
        audioChunksRecordedCount.value += 1;
      };

      rec.onstop = () => {
        void (async () => {
          const sid = sessionId.value;
          isSessionActive.value = false;
          uploadState.value = "uploading";
          stopTimersAndIntervals();

          const blob = new Blob(audioChunksLocal, {
            type: rec.mimeType || "audio/webm",
          });
          audioChunksLocal.length = 0;
          revokeSessionPlaybackUrl();
          if (blob.size > 0) {
            sessionPlaybackUrl.value = URL.createObjectURL(blob);
          }

          if (sid) {
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
          } else {
            uploadOk.value = true;
            uploadMessage.value = "Session ended.";
          }

          uploadState.value = "done";
          teardownStream();
          mediaRecorder = null;
        })();
      };

      mediaRecorder = rec;

      try {
        rec.start(AUDIO_SLICE_MS);
      } catch (err) {
        throw err instanceof Error
          ? err
          : new Error("Could not start audio recorder.");
      }
      isSessionActive.value = true;
      startSessionTimer();
      startImageInterval();
    } catch (e) {
      sessionId.value = null;
      clearImageInterval();
      if (mediaRecorder) {
        try {
          if (mediaRecorder.state !== "inactive") {
            mediaRecorder.stop();
          }
        } catch {
          /* ignore */
        }
      }
      mediaRecorder = null;
      teardownStream();
      isSessionActive.value = false;
      errorMessage.value =
        e instanceof Error
          ? e.message
          : "Could not start camera or recorder.";
    } finally {
      isSettingUp.value = false;
    }
  }

  function stopSession() {
    clearSessionTimer();
    clearImageInterval();
    const rec = mediaRecorder;
    if (rec && rec.state !== "inactive") {
      try {
        rec.requestData?.();
      } catch {
        /* ignore */
      }
      rec.stop();
    } else {
      teardownStream();
      isSessionActive.value = false;
    }
  }

  onUnmounted(() => {
    stopTimersAndIntervals();
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.onstop = null;
      mediaRecorder.stop();
    }
    mediaRecorder = null;
    teardownStream();
    isSessionActive.value = false;
    revokeSessionPlaybackUrl();
    audioChunksLocal.length = 0;
    sessionId.value = null;
  });

  return {
    videoRef,
    activeStream,
    isSettingUp,
    isSessionActive,
    errorMessage,
    uploadMessage,
    uploadOk,
    uploadState,
    sessionPlaybackUrl,
    sessionId,
    verbalResponses,
    ttsEnabled,
    lastCaptureError,
    audioChunksRecordedCount,
    imageFramesSentCount,
    sessionElapsedMs,
    sessionTimeLabel,
    startSession,
    stopSession,
  };
}
