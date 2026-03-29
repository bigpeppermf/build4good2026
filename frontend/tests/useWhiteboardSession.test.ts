import { beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, defineComponent } from "vue";

import { useWhiteboardSession } from "../src/composables/useWhiteboardSession";

type MockTrack = MediaStreamTrack & { stop: ReturnType<typeof vi.fn> };

class MockMediaStream {
  private tracks: MediaStreamTrack[];

  constructor(tracks: MediaStreamTrack[] = []) {
    this.tracks = tracks;
  }

  getTracks(): MediaStreamTrack[] {
    return this.tracks;
  }

  getAudioTracks(): MediaStreamTrack[] {
    return this.tracks.filter((track) => track.kind === "audio");
  }
}

class MockMediaRecorder {
  static isTypeSupported = vi.fn((mime: string) => {
    return mime.includes("webm") || mime.includes("ogg");
  });

  state: RecordingState = "inactive";
  mimeType: string;
  ondataavailable: ((event: BlobEvent) => unknown) | null = null;
  onstop: ((event: Event) => unknown) | null = null;

  constructor(
    readonly stream: MediaStream,
    options?: MediaRecorderOptions,
  ) {
    this.mimeType = options?.mimeType ?? "audio/webm";
  }

  start() {
    this.state = "recording";
  }

  stop() {
    if (this.state === "inactive") {
      return;
    }
    this.state = "inactive";
    this.ondataavailable?.({
      data: new Blob(["audio-chunk"], { type: this.mimeType }),
    } as BlobEvent);
    this.onstop?.(new Event("stop"));
  }
}

function makeTrack(kind: "audio" | "video"): MockTrack {
  return {
    kind,
    stop: vi.fn(),
  } as unknown as MockTrack;
}

function makeStreamWithAudio(): MediaStream {
  const tracks = [makeTrack("video"), makeTrack("audio")];
  return new MockMediaStream(tracks) as unknown as MediaStream;
}

function makeVideoElement(): HTMLVideoElement {
  const el = document.createElement("video");
  Object.defineProperty(el, "play", {
    configurable: true,
    value: vi.fn().mockResolvedValue(undefined),
  });
  return el;
}

function response(status: number, body: Record<string, unknown>): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: vi.fn().mockResolvedValue(body),
  } as unknown as Response;
}

function withSetup<T>(composable: () => T): { result: T; unmount: () => void } {
  let result!: T;
  const app = createApp(
    defineComponent({
      setup() {
        result = composable();
        return () => null;
      },
    }),
  );
  const root = document.createElement("div");
  app.mount(root);
  return {
    result,
    unmount: () => app.unmount(),
  };
}

describe("useWhiteboardSession audio lifecycle", () => {
  const getUserMedia = vi.fn();
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubGlobal("MediaStream", MockMediaStream);
    vi.stubGlobal("MediaRecorder", MockMediaRecorder);
    Object.defineProperty(window.navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
  });

  it("requests both video and audio when opening camera setup", async () => {
    const stream = makeStreamWithAudio();
    getUserMedia.mockResolvedValueOnce(stream);

    const { result: session, unmount } = withSetup(() => useWhiteboardSession());
    session.videoRef.value = makeVideoElement();

    await session.openCameraSetup();

    expect(getUserMedia).toHaveBeenCalledTimes(1);
    expect(getUserMedia).toHaveBeenCalledWith(
      expect.objectContaining({
        video: expect.any(Object),
        audio: expect.any(Object),
      }),
    );
    expect(session.activeStream.value).toBe(stream);
    unmount();
  });

  it("starts recording on beginSession and finalizes an audio blob on stopSession", async () => {
    const stream = makeStreamWithAudio();
    getUserMedia.mockResolvedValueOnce(stream);

    fetchMock
      .mockResolvedValueOnce(response(200, { session_id: "session-1" }))
      .mockResolvedValueOnce(response(200, { status: "saved" }));

    const { result: session, unmount } = withSetup(() => useWhiteboardSession());
    session.videoRef.value = makeVideoElement();

    await session.openCameraSetup();
    await session.beginSession();

    expect(session.mediaRecorder.value).not.toBeNull();
    expect(session.mediaRecorder.value?.state).toBe("recording");
    expect(session.sessionId.value).toBe("session-1");

    session.stopSession();

    await vi.waitFor(() => {
      expect(session.uploadState.value).toBe("done");
    });

    expect(session.audioChunks.value).toHaveLength(1);
    expect(session.audioBlob.value).not.toBeNull();
    expect(session.audioBlob?.value?.size ?? 0).toBeGreaterThan(0);
    expect(session.audioBlob?.value?.type).toContain("audio/");
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/new-session", {
      method: "POST",
    });
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      "/api/end-session",
      expect.objectContaining({
        method: "POST",
      }),
    );
    const endSessionCall = fetchMock.mock.calls[1];
    const endSessionInit = endSessionCall?.[1] as RequestInit | undefined;
    expect(endSessionInit?.body).toBeInstanceOf(FormData);
    const endSessionBody = endSessionInit?.body as FormData;
    expect(endSessionBody.get("session_id")).toBe("session-1");
    const uploadedAudio = endSessionBody.get("audio");
    expect(uploadedAudio).toBeInstanceOf(Blob);
    expect((uploadedAudio as Blob).size).toBeGreaterThan(0);
    unmount();
  });
});
