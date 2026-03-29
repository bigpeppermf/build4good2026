/**
 * One row in the dashboard “Previous sessions” list.
 * Populate from your API / store when persistence and processing exist.
 */
export type PastSessionSummary = {
  id: string;
  /** Optional label for the row (e.g. human title or problem name). */
  title?: string;
  /** ISO-8601 or any display string your backend returns. */
  recordedAt?: string;
  /**
   * Server-side analysis payload (scores, motion summary, model output, etc.).
   */
  analysis?: unknown;
  /**
   * Coach-style feedback, rubric results, or similar.
   */
  feedback?: unknown;
};
