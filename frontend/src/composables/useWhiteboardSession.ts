import { computed, nextTick, onUnmounted, ref, shallowRef } from "vue";

/** Full audio stream: MediaRecorder timeslice (encode chunks to backend). */
const AUDIO_SLICE_MS = 500;

/** Still frames from the webcam (not video stream). */
const IMAGE_INTERVAL_MS = 15_000;

const JPEG_QUALITY = 0.82;
const EXPORT_MAX_WIDTH = 1280;

const STREAM_PATH = "/api/practice/stream";

function streamWebSocketUrl(): string {
  const env = import.meta.env.VITE_PRACTICE_STREAM_WS as string | undefined;
  if (env && env.trim().length > 0) {
    return env.trim();
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${STREAM_PATH}`;
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

  const streamWsConnected = ref(false);
  const audioChunksSentCount = ref(0);
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
  let practiceSocket: WebSocket | null = null;

  const pendingAudio: { seq: number; blob: Blob }[] = [];

  let audioSeq = 0;
  let imageSeq = 0;
  let sessionWallStart = 0;

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

  function flushPendingAudio() {
    const ws = practiceSocket;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    while (pendingAudio.length > 0) {
      const { seq, blob } = pendingAudio.shift()!;
      if (blob.size === 0) {
        continue;
      }
      ws.send(
        JSON.stringify({
          type: "audio_chunk",
          seq,
          bytes: blob.size,
        }),
      );
      ws.send(blob);
      audioChunksSentCount.value += 1;
    }
  }

  function sendAudioChunk(seq: number, blob: Blob) {
    if (blob.size === 0) {
      return;
    }
    const ws = practiceSocket;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(
        JSON.stringify({
          type: "audio_chunk",
          seq,
          bytes: blob.size,
        }),
      );
      ws.send(blob);
      audioChunksSentCount.value += 1;
    } else {
      pendingAudio.push({ seq, blob });
    }
  }

  function closePracticeSocket() {
    if (practiceSocket) {
      practiceSocket.onopen = null;
      practiceSocket.onerror = null;
      practiceSocket.onclose = null;
      practiceSocket.onmessage = null;
      if (
        practiceSocket.readyState === WebSocket.OPEN ||
        practiceSocket.readyState === WebSocket.CONNECTING
      ) {
        practiceSocket.close();
      }
      practiceSocket = null;
    }
    streamWsConnected.value = false;
    pendingAudio.length = 0;
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
    const ws = practiceSocket;
    if (!video || !isSessionActive.value || ws?.readyState !== WebSocket.OPEN) {
      return;
    }
    const blob = await captureJpegFromVideo(video);
    if (!blob || blob.size === 0) {
      return;
    }
    imageSeq += 1;
    const elapsedMs = Date.now() - sessionWallStart;
    try {
      ws.send(
        JSON.stringify({
          type: "image_frame",
          seq: imageSeq,
          elapsedMs,
          bytes: blob.size,
        }),
      );
      ws.send(blob);
      imageFramesSentCount.value += 1;
    } catch {
      /* ignore */
    }
  }

  async function startSession() {
    errorMessage.value = null;
    uploadMessage.value = null;
    uploadOk.value = null;
    uploadState.value = "idle";
    revokeSessionPlaybackUrl();
    audioChunksLocal.length = 0;
    pendingAudio.length = 0;
    audioSeq = 0;
    imageSeq = 0;
    audioChunksSentCount.value = 0;
    imageFramesSentCount.value = 0;
    closePracticeSocket();
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
        audioSeq += 1;
        audioChunksLocal.push(e.data);
        sendAudioChunk(audioSeq, e.data);
      };

      rec.onstop = () => {
        isSessionActive.value = false;
        streamWsConnected.value = false;
        uploadState.value = "uploading";
        stopTimersAndIntervals();
        try {
          if (practiceSocket?.readyState === WebSocket.OPEN) {
            practiceSocket.send(
              JSON.stringify({
                type: "stop",
                elapsedMs: Math.round(sessionElapsedMs.value),
                audioChunksSent: audioChunksSentCount.value,
                imageFramesSent: imageFramesSentCount.value,
                audioMime: rec.mimeType || "audio/webm",
                imageMime: "image/jpeg",
              }),
            );
          }
        } catch {
          /* ignore */
        }
        closePracticeSocket();

        const blob = new Blob(audioChunksLocal, {
          type: rec.mimeType || "audio/webm",
        });
        audioChunksLocal.length = 0;
        revokeSessionPlaybackUrl();
        if (blob.size > 0) {
          sessionPlaybackUrl.value = URL.createObjectURL(blob);
        }

        uploadState.value = "done";
        uploadOk.value = true;
        uploadMessage.value =
          "Session ended. Full audio was streamed over the WebSocket; JPEG stills were sent every 15s. Local audio replay is below if recorded.";

        teardownStream();
        mediaRecorder = null;
      };

      mediaRecorder = rec;

      const url = streamWebSocketUrl();
      const ws = new WebSocket(url);
      practiceSocket = ws;

      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => {
          reject(new Error("Timed out connecting to the practice stream."));
        }, 12000);

        ws.onopen = () => {
          window.clearTimeout(timeout);
          streamWsConnected.value = true;
          sessionWallStart = Date.now();
          try {
            ws.send(
              JSON.stringify({
                type: "start",
                audioMime: rec.mimeType || mime || "audio/webm",
                imageMime: "image/jpeg",
                imageIntervalMs: IMAGE_INTERVAL_MS,
              }),
            );
          } catch {
            /* ignore */
          }
          flushPendingAudio();
          try {
            rec.start(AUDIO_SLICE_MS);
          } catch (err) {
            reject(
              err instanceof Error
                ? err
                : new Error("Could not start audio recorder."),
            );
            return;
          }
          isSessionActive.value = true;
          startSessionTimer();
          startImageInterval();
          resolve();
        };

        ws.onerror = () => {
          window.clearTimeout(timeout);
          streamWsConnected.value = false;
          reject(new Error("WebSocket stream error (is the backend WS route up?)"));
        };

        ws.onclose = (ev) => {
          window.clearTimeout(timeout);
          streamWsConnected.value = false;
          if (ev.code !== 1000 && ev.code !== 1005 && isSessionActive.value) {
            errorMessage.value = `Stream closed (${ev.code}). Stopping recording.`;
            try {
              if (mediaRecorder && mediaRecorder.state !== "inactive") {
                mediaRecorder.stop();
              }
            } catch {
              /* ignore */
            }
          }
        };
      });
    } catch (e) {
      closePracticeSocket();
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
      streamWsConnected.value = false;
      errorMessage.value =
        e instanceof Error
          ? e.message
          : "Could not start camera, recorder, or stream.";
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
      closePracticeSocket();
      teardownStream();
      isSessionActive.value = false;
    }
  }

  onUnmounted(() => {
    stopTimersAndIntervals();
    closePracticeSocket();
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.onstop = null;
      mediaRecorder.stop();
    }
    mediaRecorder = null;
    teardownStream();
    isSessionActive.value = false;
    revokeSessionPlaybackUrl();
    audioChunksLocal.length = 0;
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
    streamWsConnected,
    audioChunksSentCount,
    imageFramesSentCount,
    sessionElapsedMs,
    sessionTimeLabel,
    startSession,
    stopSession,
  };
}
