/**
 * Persists whiteboard session output in localStorage so Chat can show
 * coach replies, visual deltas, and stats after leaving the Dashboard.
 *
 * Storage is scoped by Clerk user ID so snapshots from different users on the
 * same browser do not leak into each other.
 */

const STORAGE_PREFIX = "mirage:session:";
const RECENT_KEY = "mirage:recentSessions";
const LAST_KEY = "mirage:lastSessionId";

export interface SnapshotVerbalItem {
  timestampMs: number;
  verbalResponse: string;
  visualDelta?: string;
}

export interface WhiteboardSessionSnapshot {
  userId: string;
  sessionId: string;
  savedAt: string;
  verbalResponses: SnapshotVerbalItem[];
  imageFramesSentCount: number;
  discardedFramesCount: number;
  processedFramesCount: number;
  uploadOk: boolean | null;
  uploadMessage: string | null;
}

function sessionStorageKey(userId: string, sessionId: string): string {
  return `${STORAGE_PREFIX}${userId}:${sessionId}`;
}

function recentSessionsKey(userId: string): string {
  return `${RECENT_KEY}:${userId}`;
}

function lastSessionKey(userId: string): string {
  return `${LAST_KEY}:${userId}`;
}

export function persistWhiteboardSnapshot(data: WhiteboardSessionSnapshot): void {
  try {
    localStorage.setItem(
      sessionStorageKey(data.userId, data.sessionId),
      JSON.stringify(data),
    );
    localStorage.setItem(lastSessionKey(data.userId), data.sessionId);

    const raw = localStorage.getItem(recentSessionsKey(data.userId));
    let recent: { sessionId: string; savedAt: string }[] = [];
    if (raw) {
      recent = JSON.parse(raw) as { sessionId: string; savedAt: string }[];
    }
    recent = [
      { sessionId: data.sessionId, savedAt: data.savedAt },
      ...recent.filter((item) => item.sessionId !== data.sessionId),
    ].slice(0, 12);
    localStorage.setItem(recentSessionsKey(data.userId), JSON.stringify(recent));
  } catch {
    /* quota or private mode */
  }
}

export function loadWhiteboardSnapshot(
  userId: string,
  sessionId: string,
): WhiteboardSessionSnapshot | null {
  try {
    const raw = localStorage.getItem(sessionStorageKey(userId, sessionId));
    if (!raw) {
      return null;
    }
    return JSON.parse(raw) as WhiteboardSessionSnapshot;
  } catch {
    return null;
  }
}

export function getRecentSessions(
  userId: string,
): { sessionId: string; savedAt: string }[] {
  try {
    const raw = localStorage.getItem(recentSessionsKey(userId));
    if (!raw) {
      return [];
    }
    return JSON.parse(raw) as { sessionId: string; savedAt: string }[];
  } catch {
    return [];
  }
}

export function getLastSessionId(userId: string): string | null {
  try {
    return localStorage.getItem(lastSessionKey(userId));
  } catch {
    return null;
  }
}
