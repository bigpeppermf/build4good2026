import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createApp, defineComponent } from "vue";

import { useSessionAnalysis } from "../src/composables/useSessionAnalysis";

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

describe("useSessionAnalysis", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    vi.clearAllMocks();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("stores complete analysis payload when first poll completes", async () => {
    fetchMock.mockResolvedValueOnce(
      response(200, {
        status: "complete",
        stage: "complete",
        analysis: {
          architecture_pattern: "3-tier web architecture",
          component_count: 3,
          identified_components: ["Browser", "API", "DB"],
          connection_density: "moderate",
          entry_point: "Browser",
          disconnected_components: [],
          bottlenecks: ["DB"],
          missing_standard_components: ["Cache layer"],
          summary: "Solid base architecture.",
        },
        feedback: {
          strengths: ["Clear flow"],
          improvements: ["Add cache"],
          critical_gaps: [],
          narrative: "Nice structure.",
        },
        score: {
          total: 80,
          breakdown: {
            completeness: 20,
            scalability: 20,
            reliability: 20,
            clarity: 20,
          },
          grade: "B",
        },
      }),
    );

    const { result: sessionAnalysis, unmount } = withSetup(() =>
      useSessionAnalysis(),
    );

    sessionAnalysis.startPolling("session-1");

    await vi.waitFor(() => {
      expect(sessionAnalysis.status.value).toBe("complete");
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledWith("/api/analysis/session-1", {
      method: "GET",
    });
    expect(sessionAnalysis.analysis.value?.architecture_pattern).toBe(
      "3-tier web architecture",
    );
    expect(sessionAnalysis.feedback.value?.improvements).toEqual(["Add cache"]);
    expect(sessionAnalysis.score.value?.total).toBe(80);
    expect(sessionAnalysis.isPolling.value).toBe(false);

    unmount();
  });

  it("continues polling while processing and completes on subsequent poll", async () => {
    fetchMock
      .mockResolvedValueOnce(
        response(200, {
          status: "processing",
          stage: "analysis",
        }),
      )
      .mockResolvedValueOnce(
        response(200, {
          status: "complete",
          stage: "complete",
          analysis: {
            architecture_pattern: "event-driven service architecture",
            component_count: 4,
            identified_components: ["Client", "API", "Queue", "DB"],
            connection_density: "dense",
            entry_point: "Client",
            disconnected_components: [],
            bottlenecks: [],
            missing_standard_components: [],
            summary: "Asynchronous path introduced.",
          },
          feedback: {
            strengths: ["Queue added"],
            improvements: ["Add monitoring"],
            critical_gaps: [],
            narrative: "Good async design.",
          },
          score: {
            total: 88,
            breakdown: {
              completeness: 22,
              scalability: 23,
              reliability: 21,
              clarity: 22,
            },
            grade: "B",
          },
        }),
      );

    const { result: sessionAnalysis, unmount } = withSetup(() =>
      useSessionAnalysis(),
    );

    sessionAnalysis.startPolling("session-2");

    await vi.waitFor(() => {
      expect(sessionAnalysis.status.value).toBe("processing");
      expect(sessionAnalysis.stage.value).toBe("analysis");
    });

    await vi.advanceTimersByTimeAsync(2_000);

    await vi.waitFor(() => {
      expect(sessionAnalysis.status.value).toBe("complete");
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(sessionAnalysis.score.value?.grade).toBe("B");
    expect(sessionAnalysis.stage.value).toBe("complete");

    unmount();
  });

  it("stores failed status and error when polling endpoint fails", async () => {
    fetchMock.mockResolvedValueOnce(
      response(404, {
        error: "Unknown 'session_id' for analysis.",
      }),
    );

    const { result: sessionAnalysis, unmount } = withSetup(() =>
      useSessionAnalysis(),
    );

    sessionAnalysis.startPolling("missing-session");

    await vi.waitFor(() => {
      expect(sessionAnalysis.status.value).toBe("failed");
    });

    expect(sessionAnalysis.errorMessage.value).toContain("Unknown");
    expect(sessionAnalysis.isPolling.value).toBe(false);
    expect(sessionAnalysis.analysis.value).toBeNull();
    expect(sessionAnalysis.feedback.value).toBeNull();
    expect(sessionAnalysis.score.value).toBeNull();

    unmount();
  });
});
