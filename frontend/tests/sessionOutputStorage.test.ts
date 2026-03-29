import { beforeEach, describe, expect, it } from "vitest";

import {
  deleteWhiteboardSnapshot,
  getLastSessionId,
  getRecentSessions,
  loadWhiteboardSnapshot,
  persistWhiteboardSnapshot,
} from "../src/utils/sessionOutputStorage";

function makeSnapshot(userId: string, sessionId: string, savedAt: string) {
  return {
    userId,
    sessionId,
    savedAt,
    verbalResponses: [],
    imageFramesSentCount: 0,
    discardedFramesCount: 0,
    processedFramesCount: 0,
    uploadOk: true as boolean | null,
    uploadMessage: "ok" as string | null,
  };
}

describe("sessionOutputStorage delete flow", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("removes deleted session and updates recent + last pointers", () => {
    const userId = "user-1";
    persistWhiteboardSnapshot(makeSnapshot(userId, "sess-a", "2026-03-28T10:00:00.000Z"));
    persistWhiteboardSnapshot(makeSnapshot(userId, "sess-b", "2026-03-28T11:00:00.000Z"));

    deleteWhiteboardSnapshot(userId, "sess-b");

    expect(loadWhiteboardSnapshot(userId, "sess-b")).toBeNull();
    expect(getRecentSessions(userId).map((s) => s.sessionId)).toEqual(["sess-a"]);
    expect(getLastSessionId(userId)).toBe("sess-a");
  });

  it("clears recent + last when the final session is deleted", () => {
    const userId = "user-2";
    persistWhiteboardSnapshot(makeSnapshot(userId, "sess-only", "2026-03-28T12:00:00.000Z"));

    deleteWhiteboardSnapshot(userId, "sess-only");

    expect(loadWhiteboardSnapshot(userId, "sess-only")).toBeNull();
    expect(getRecentSessions(userId)).toEqual([]);
    expect(getLastSessionId(userId)).toBeNull();
  });
});
