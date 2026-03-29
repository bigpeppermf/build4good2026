/**
 * Persists whiteboard session output in localStorage so Chat can show
 * coach replies, visual deltas, and stats after leaving the Dashboard.
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
  sessionId: string;
  savedAt: string;
  verbalResponses: SnapshotVerbalItem[];
  imageFramesSentCount: number;
  discardedFramesCount: number;
  processedFramesCount: number;
  uploadOk: boolean | null;
  uploadMessage: string | null;
}

export function persistWhiteboardSnapshot(data: WhiteboardSessionSnapshot): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + data.sessionId, JSON.stringify(data));
    localStorage.setItem(LAST_KEY, data.sessionId);
    const raw = localStorage.getItem(RECENT_KEY);
    let recent: { sessionId: string; savedAt: string }[] = [];
    if (raw) {
      recent = JSON.parse(raw) as { sessionId: string; savedAt: string }[];
    }
    recent = [
      { sessionId: data.sessionId, savedAt: data.savedAt },
      ...recent.filter((x) => x.sessionId !== data.sessionId),
    ].slice(0, 12);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
  } catch {
    /* quota or private mode */
  }
}

export function loadWhiteboardSnapshot(
  sessionId: string,
): WhiteboardSessionSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + sessionId);
    if (!raw) return null;
    return JSON.parse(raw) as WhiteboardSessionSnapshot;
  } catch {
    return null;
  }
}

export function getRecentSessions(): { sessionId: string; savedAt: string }[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as { sessionId: string; savedAt: string }[];
  } catch {
    return [];
  }
}

export function getLastSessionId(): string | null {
  try {
    return localStorage.getItem(LAST_KEY);
  } catch {
    return null;
  }
}
