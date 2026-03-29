import { onUnmounted, ref } from "vue";

import { useMirageAuth } from "./useMirageAuth";
import { apiUrl } from "../utils/apiUrl";

const POLL_INTERVAL_MS = 2_000;

export type AnalysisStatus = "idle" | "processing" | "complete" | "failed";

export interface SessionAnalysisData {
  architecture_pattern: string;
  component_count: number;
  identified_components: string[];
  connection_density: "sparse" | "moderate" | "dense";
  entry_point: string | null;
  disconnected_components: string[];
  bottlenecks: string[];
  missing_standard_components: string[];
  summary: string;
}

export interface SessionFeedbackData {
  strengths: string[];
  improvements: string[];
  critical_gaps: string[];
  narrative: string;
}

export interface SessionScoreData {
  total: number;
  breakdown: {
    completeness: number;
    scalability: number;
    reliability: number;
    clarity: number;
  };
  grade: "A" | "B" | "C" | "D" | "F";
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object") {
    return value as Record<string, unknown>;
  }
  return {};
}

function asText(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed) {
      return trimmed;
    }
  }
  return fallback;
}

function asStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const out: string[] = [];
  for (const item of value) {
    if (typeof item === "string") {
      const trimmed = item.trim();
      if (trimmed) {
        out.push(trimmed);
      }
    }
  }
  return out;
}

function asInt(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return Math.trunc(value);
  }
  if (typeof value === "string") {
    const parsed = Number.parseInt(value, 10);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function asConnectionDensity(value: unknown): "sparse" | "moderate" | "dense" {
  if (value === "sparse" || value === "moderate" || value === "dense") {
    return value;
  }
  return "moderate";
}

function asGrade(value: unknown): "A" | "B" | "C" | "D" | "F" {
  if (value === "A" || value === "B" || value === "C" || value === "D" || value === "F") {
    return value;
  }
  return "C";
}

function parseAnalysis(value: unknown): SessionAnalysisData | null {
  const raw = asRecord(value);
  if (Object.keys(raw).length === 0) {
    return null;
  }
  return {
    architecture_pattern: asText(raw.architecture_pattern, "Unknown architecture"),
    component_count: Math.max(0, asInt(raw.component_count, 0)),
    identified_components: asStringArray(raw.identified_components),
    connection_density: asConnectionDensity(raw.connection_density),
    entry_point: asText(raw.entry_point) || null,
    disconnected_components: asStringArray(raw.disconnected_components),
    bottlenecks: asStringArray(raw.bottlenecks),
    missing_standard_components: asStringArray(raw.missing_standard_components),
    summary: asText(raw.summary, "No summary available."),
  };
}

function parseFeedback(value: unknown): SessionFeedbackData | null {
  const raw = asRecord(value);
  if (Object.keys(raw).length === 0) {
    return null;
  }
  return {
    strengths: asStringArray(raw.strengths),
    improvements: asStringArray(raw.improvements),
    critical_gaps: asStringArray(raw.critical_gaps),
    narrative: asText(raw.narrative, "No coaching narrative available."),
  };
}

function clampScoreBand(value: unknown): number {
  return Math.min(25, Math.max(0, asInt(value, 0)));
}

function parseScore(value: unknown): SessionScoreData | null {
  const raw = asRecord(value);
  if (Object.keys(raw).length === 0) {
    return null;
  }
  const breakdownRaw = asRecord(raw.breakdown);
  const breakdown = {
    completeness: clampScoreBand(breakdownRaw.completeness),
    scalability: clampScoreBand(breakdownRaw.scalability),
    reliability: clampScoreBand(breakdownRaw.reliability),
    clarity: clampScoreBand(breakdownRaw.clarity),
  };
  const fallbackTotal =
    breakdown.completeness +
    breakdown.scalability +
    breakdown.reliability +
    breakdown.clarity;
  return {
    total: Math.min(100, Math.max(0, asInt(raw.total, fallbackTotal))),
    breakdown,
    grade: asGrade(raw.grade),
  };
}

export function useSessionAnalysis() {
  const { apiFetch } = useMirageAuth();
  const sessionId = ref<string | null>(null);
  const status = ref<AnalysisStatus>("idle");
  const stage = ref<string | null>(null);
  const errorMessage = ref<string | null>(null);
  const isPolling = ref(false);

  const analysis = ref<SessionAnalysisData | null>(null);
  const feedback = ref<SessionFeedbackData | null>(null);
  const score = ref<SessionScoreData | null>(null);

  let pollTimer: ReturnType<typeof setTimeout> | null = null;
  let pollToken = 0;

  function clearPollTimer() {
    if (pollTimer !== null) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  function resetOutput() {
    analysis.value = null;
    feedback.value = null;
    score.value = null;
  }

  function stopPolling() {
    pollToken += 1;
    clearPollTimer();
    isPolling.value = false;
  }

  async function pollOnce(activeToken: number) {
    if (!sessionId.value) {
      return;
    }
    try {
      const res = await apiFetch(apiUrl(`/analysis/${sessionId.value}`), {
        method: "GET",
      });
      if (activeToken !== pollToken) {
        return;
      }
      const payload = (await res.json().catch(() => ({}))) as Record<string, unknown>;

      if (!res.ok) {
        status.value = "failed";
        stage.value = "polling";
        errorMessage.value =
          typeof payload.error === "string"
            ? payload.error
            : `Could not load analysis (${res.status}).`;
        isPolling.value = false;
        clearPollTimer();
        return;
      }

      const nextStatus = asText(payload.status, "processing");
      stage.value = asText(payload.stage, stage.value ?? "processing");

      if (nextStatus === "processing") {
        status.value = "processing";
        isPolling.value = true;
        clearPollTimer();
        pollTimer = setTimeout(() => {
          void pollOnce(activeToken);
        }, POLL_INTERVAL_MS);
        return;
      }

      if (nextStatus === "failed") {
        status.value = "failed";
        errorMessage.value = asText(payload.error, "Session analysis failed.");
        isPolling.value = false;
        clearPollTimer();
        return;
      }

      if (nextStatus === "complete") {
        status.value = "complete";
        analysis.value = parseAnalysis(payload.analysis);
        feedback.value = parseFeedback(payload.feedback);
        score.value = parseScore(payload.score);
        errorMessage.value = null;
        isPolling.value = false;
        clearPollTimer();
        return;
      }

      status.value = "processing";
      isPolling.value = true;
      clearPollTimer();
      pollTimer = setTimeout(() => {
        void pollOnce(activeToken);
      }, POLL_INTERVAL_MS);
    } catch {
      if (activeToken !== pollToken) {
        return;
      }
      status.value = "failed";
      stage.value = "polling";
      errorMessage.value = "Network error while polling session analysis.";
      isPolling.value = false;
      clearPollTimer();
    }
  }

  function startPolling(nextSessionId: string) {
    const normalized = nextSessionId.trim();
    stopPolling();
    resetOutput();
    errorMessage.value = null;
    stage.value = "queued";
    if (!normalized) {
      sessionId.value = null;
      status.value = "failed";
      errorMessage.value = "Missing session ID for analysis polling.";
      return;
    }

    sessionId.value = normalized;
    status.value = "processing";
    isPolling.value = true;
    const activeToken = pollToken;
    void pollOnce(activeToken);
  }

  onUnmounted(() => {
    stopPolling();
  });

  return {
    sessionId,
    status,
    stage,
    errorMessage,
    isPolling,
    analysis,
    feedback,
    score,
    startPolling,
    stopPolling,
  };
}
