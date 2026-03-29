import { beforeEach, describe, expect, it } from "vitest";

import {
  getLastSessionId,
  getRecentSessions,
  loadWhiteboardSnapshot,
  persistWhiteboardSnapshot,
} from "../src/utils/sessionOutputStorage";

describe("sessionOutputStorage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("scopes snapshots, recents, and last-session ids by Clerk user", () => {
    persistWhiteboardSnapshot({
      userId: "user_a",
      sessionId: "session-a-1",
      savedAt: "2026-03-29T10:00:00.000Z",
      verbalResponses: [
        {
          timestampMs: 1000,
          verbalResponse: "Add a cache layer.",
          visualDelta: "Cache box added.",
        },
      ],
      imageFramesSentCount: 3,
      discardedFramesCount: 1,
      processedFramesCount: 2,
      uploadOk: true,
      uploadMessage: "Session ended (processing).",
    });
    persistWhiteboardSnapshot({
      userId: "user_b",
      sessionId: "session-b-1",
      savedAt: "2026-03-29T11:00:00.000Z",
      verbalResponses: [],
      imageFramesSentCount: 1,
      discardedFramesCount: 0,
      processedFramesCount: 1,
      uploadOk: false,
      uploadMessage: "Upload failed.",
    });

    expect(loadWhiteboardSnapshot("user_a", "session-a-1")?.userId).toBe("user_a");
    expect(loadWhiteboardSnapshot("user_b", "session-a-1")).toBeNull();
    expect(getLastSessionId("user_a")).toBe("session-a-1");
    expect(getLastSessionId("user_b")).toBe("session-b-1");
    expect(getRecentSessions("user_a")).toEqual([
      { sessionId: "session-a-1", savedAt: "2026-03-29T10:00:00.000Z" },
    ]);
    expect(getRecentSessions("user_b")).toEqual([
      { sessionId: "session-b-1", savedAt: "2026-03-29T11:00:00.000Z" },
    ]);
  });

  it("moves the latest save to the top without duplicating recents", () => {
    persistWhiteboardSnapshot({
      userId: "user_a",
      sessionId: "session-1",
      savedAt: "2026-03-29T10:00:00.000Z",
      verbalResponses: [],
      imageFramesSentCount: 1,
      discardedFramesCount: 0,
      processedFramesCount: 1,
      uploadOk: true,
      uploadMessage: null,
    });
    persistWhiteboardSnapshot({
      userId: "user_a",
      sessionId: "session-2",
      savedAt: "2026-03-29T11:00:00.000Z",
      verbalResponses: [],
      imageFramesSentCount: 2,
      discardedFramesCount: 0,
      processedFramesCount: 2,
      uploadOk: true,
      uploadMessage: null,
    });
    persistWhiteboardSnapshot({
      userId: "user_a",
      sessionId: "session-1",
      savedAt: "2026-03-29T12:00:00.000Z",
      verbalResponses: [],
      imageFramesSentCount: 3,
      discardedFramesCount: 0,
      processedFramesCount: 3,
      uploadOk: true,
      uploadMessage: null,
    });

    expect(getLastSessionId("user_a")).toBe("session-1");
    expect(getRecentSessions("user_a")).toEqual([
      { sessionId: "session-1", savedAt: "2026-03-29T12:00:00.000Z" },
      { sessionId: "session-2", savedAt: "2026-03-29T11:00:00.000Z" },
    ]);
  });
});
