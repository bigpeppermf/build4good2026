import { computed, nextTick, onUnmounted, ref, shallowRef } from "vue";

/** How often encoded chunks are produced and pushed over the WebSocket. */
const STREAM_SLICE_MS = 500;

const STREAM_PATH = "/api/practice/stream";

function streamWebSocketUrl(): string {
  const env = import.meta.env.VITE_PRACTICE_STREAM_WS as string | undefined;
  if (env && env.trim().length > 0) {
    return env.trim();
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${STREAM_PATH}`;
}

function pickStreamMime(): string | undefined {
  const candidates = [
    "video/webm;codecs=vp9,opus",
    "video/webm;codecs=vp8,opus",
    "video/webm",
  ];
  for (const t of candidates) {
    if (MediaRecorder.isTypeSupported(t)) {
      return t;
    }
  }
  return undefined;
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

  /** Local replay URL (full WebM after stop). */
  const sessionPlaybackUrl = ref<string | null>(null);

  const streamWsConnected = ref(false);
  const chunksSentCount = ref(0);

  const sessionElapsedMs = ref(0);
  let sessionTimerId: ReturnType<typeof setInterval> | null = null;

  const sessionTimeLabel = computed(() => {
    const totalSec = Math.floor(sessionElapsedMs.value / 1000);
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  });

  let mediaRecorder: MediaRecorder | null = null;
  const streamChunks: Blob[] = [];
  let practiceSocket: WebSocket | null = null;
  const pendingChunks: Blob[] = [];

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

  function revokeSessionPlaybackUrl() {
    if (sessionPlaybackUrl.value) {
      URL.revokeObjectURL(sessionPlaybackUrl.value);
      sessionPlaybackUrl.value = null;
    }
  }

  function flushPendingChunks() {
    const ws = practiceSocket;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return;
    }
    while (pendingChunks.length > 0) {
      const chunk = pendingChunks.shift();
      if (chunk && chunk.size > 0) {
        ws.send(chunk);
        chunksSentCount.value += 1;
      }
    }
  }

  function sendChunkToSocket(blob: Blob) {
    if (blob.size === 0) {
      return;
    }
    const ws = practiceSocket;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(blob);
      chunksSentCount.value += 1;
    } else {
      pendingChunks.push(blob);
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
    pendingChunks.length = 0;
  }

  function stopSessionTimerAndMotion() {
    clearSessionTimer();
  }

  function teardownStream() {
    stopSessionTimerAndMotion();
    activeStream.value?.getTracks().forEach((t) => t.stop());
    activeStream.value = null;
    if (videoRef.value) {
      videoRef.value.srcObject = null;
    }
  }

  async function startSession() {
    errorMessage.value = null;
    uploadMessage.value = null;
    uploadOk.value = null;
    uploadState.value = "idle";
    revokeSessionPlaybackUrl();
    streamChunks.length = 0;
    pendingChunks.length = 0;
    chunksSentCount.value = 0;
    closePracticeSocket();
    stopSessionTimerAndMotion();
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

      const mime = pickStreamMime();
      const rec = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);

      rec.ondataavailable = (e) => {
        if (e.data.size === 0) {
          return;
        }
        streamChunks.push(e.data);
        sendChunkToSocket(e.data);
      };

      rec.onstop = () => {
        isSessionActive.value = false;
        streamWsConnected.value = false;
        uploadState.value = "uploading";
        clearSessionTimer();
        try {
          if (practiceSocket?.readyState === WebSocket.OPEN) {
            practiceSocket.send(
              JSON.stringify({
                type: "stop",
                elapsedMs: Math.round(sessionElapsedMs.value),
                chunksSent: chunksSentCount.value,
                mime: rec.mimeType || "video/webm",
              }),
            );
          }
        } catch {
          /* ignore */
        }
        closePracticeSocket();

        const blob = new Blob(streamChunks, {
          type: rec.mimeType || "video/webm",
        });
        streamChunks.length = 0;
        revokeSessionPlaybackUrl();
        if (blob.size > 0) {
          sessionPlaybackUrl.value = URL.createObjectURL(blob);
        }

        uploadState.value = "done";
        uploadOk.value = true;
        uploadMessage.value =
          "Session ended. Media was streamed to the backend while recording; local replay is available below if the browser produced a file.";

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
          try {
            ws.send(
              JSON.stringify({
                type: "start",
                mime: rec.mimeType || mime || "video/webm",
              }),
            );
          } catch {
            /* ignore */
          }
          flushPendingChunks();
          try {
            rec.start(STREAM_SLICE_MS);
          } catch (err) {
            reject(
              err instanceof Error
                ? err
                : new Error("Could not start media recorder."),
            );
            return;
          }
          isSessionActive.value = true;
          startSessionTimer();
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
    clearSessionTimer();
    closePracticeSocket();
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.onstop = null;
      mediaRecorder.stop();
    }
    mediaRecorder = null;
    teardownStream();
    isSessionActive.value = false;
    revokeSessionPlaybackUrl();
    streamChunks.length = 0;
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
    chunksSentCount,
    sessionElapsedMs,
    sessionTimeLabel,
    startSession,
    stopSession,
  };
}
