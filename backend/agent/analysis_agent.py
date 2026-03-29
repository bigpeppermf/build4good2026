"""
Post-session analysis agent.

Generates structured architecture analysis/feedback/score output from the
validated graph and transcript.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from core.graph import SystemDesignGraph

ANALYSIS_SYSTEM_PROMPT = """\
You are an expert system design interviewer evaluating a candidate's whiteboard design.
You will receive:
1) A graph snapshot of the candidate's architecture.
2) The candidate's audio transcript.
3) Session metadata.

Return JSON ONLY (no markdown) using this exact top-level schema:
{
  "analysis": {
    "architecture_pattern": "string",
    "component_count": 0,
    "identified_components": ["string"],
    "connection_density": "sparse|moderate|dense",
    "entry_point": "string|null",
    "disconnected_components": ["string"],
    "bottlenecks": ["string"],
    "missing_standard_components": ["string"],
    "summary": "string"
  },
  "feedback": {
    "strengths": ["string"],
    "improvements": ["string"],
    "critical_gaps": ["string"],
    "narrative": "string"
  },
  "score": {
    "total": 0,
    "breakdown": {
      "completeness": 0,
      "scalability": 0,
      "reliability": 0,
      "clarity": 0
    },
    "grade": "A|B|C|D|F"
  }
}

Scoring rubric:
- Completeness (0-25): client + entry/network + app + data layers, plus bonus components.
- Scalability (0-25): load balancing, horizontal app tier, cache, async queue.
- Reliability (0-25): redundancy, no fragile single critical path, failure awareness.
- Clarity (0-25): clear labels, no disconnected components, explicit entry point, edge clarity.
"""

_DENSITIES = {"sparse", "moderate", "dense"}
_GRADES = {"A", "B", "C", "D", "F"}


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lo, min(hi, parsed))


def _normalize_text(value: Any, default: str = "") -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return default


def _normalize_text_list(value: Any, *, max_items: int = 8) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        text = _normalize_text(item)
        if text and text not in output:
            output.append(text)
        if len(output) >= max_items:
            break
    return output


def _grade_from_total(total: int) -> str:
    if total >= 90:
        return "A"
    if total >= 75:
        return "B"
    if total >= 60:
        return "C"
    if total >= 45:
        return "D"
    return "F"


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(content or "")


def _extract_json_candidate(text: str) -> dict[str, Any] | None:
    if not text.strip():
        return None

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            payload = json.loads(fenced.group(1))
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

    return None


class AnalysisAgent:
    """
    Produces post-session analysis output.

    When no real Gemini key is configured, falls back to deterministic rubric
    scoring so local tests remain offline and stable.
    """

    def __init__(self, llm: Any | None = None) -> None:
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if llm is not None:
            self.llm = llm
        elif api_key and api_key != "test-key-stub":
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.5-flash-lite",
                temperature=0,
                google_api_key=api_key,
            )
        else:
            self.llm = None

    async def analyze(
        self,
        graph: SystemDesignGraph,
        transcript: str,
        session_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fallback = self._heuristic_analysis(graph, transcript, session_metadata)
        if self.llm is None:
            return fallback

        metadata = session_metadata or {}
        prompt = (
            "GRAPH SNAPSHOT:\n"
            f"{graph.bfs_serialize()}\n\n"
            "TRANSCRIPT:\n"
            f"{(transcript or '').strip()}\n\n"
            "SESSION METADATA:\n"
            f"{json.dumps(metadata, indent=2, sort_keys=True)}\n\n"
            "Return JSON only."
        )
        try:
            response = await asyncio.wait_for(
                self.llm.ainvoke(
                    [
                        SystemMessage(content=ANALYSIS_SYSTEM_PROMPT),
                        HumanMessage(content=prompt),
                    ]
                ),
                timeout=60.0,
            )
            raw = _message_content_to_text(getattr(response, "content", ""))
            parsed = _extract_json_candidate(raw)
            if parsed is None:
                return fallback
            return self._coerce_output(parsed, fallback=fallback)
        except Exception:  # noqa: BLE001
            return fallback

    def _coerce_output(self, payload: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        analysis_raw = payload.get("analysis", {}) if isinstance(payload.get("analysis"), dict) else {}
        feedback_raw = payload.get("feedback", {}) if isinstance(payload.get("feedback"), dict) else {}
        score_raw = payload.get("score", {}) if isinstance(payload.get("score"), dict) else {}

        fallback_analysis = fallback["analysis"]
        fallback_feedback = fallback["feedback"]
        fallback_score = fallback["score"]

        identified = _normalize_text_list(
            analysis_raw.get("identified_components"),
            max_items=50,
        ) or fallback_analysis["identified_components"]
        disconnected = _normalize_text_list(
            analysis_raw.get("disconnected_components")
        ) or fallback_analysis["disconnected_components"]
        bottlenecks = _normalize_text_list(analysis_raw.get("bottlenecks")) or fallback_analysis["bottlenecks"]
        missing = _normalize_text_list(analysis_raw.get("missing_standard_components")) or fallback_analysis[
            "missing_standard_components"
        ]
        density = _normalize_text(analysis_raw.get("connection_density"), fallback_analysis["connection_density"])
        if density not in _DENSITIES:
            density = fallback_analysis["connection_density"]

        entry_point_value = analysis_raw.get("entry_point")
        entry_point = None
        if isinstance(entry_point_value, str):
            entry_point = entry_point_value.strip() or None

        analysis = {
            "architecture_pattern": _normalize_text(
                analysis_raw.get("architecture_pattern"),
                fallback_analysis["architecture_pattern"],
            ),
            "component_count": _clamp_int(
                analysis_raw.get("component_count"),
                0,
                10_000,
                len(identified),
            ),
            "identified_components": identified,
            "connection_density": density,
            "entry_point": entry_point if entry_point is not None else fallback_analysis["entry_point"],
            "disconnected_components": disconnected,
            "bottlenecks": bottlenecks,
            "missing_standard_components": missing,
            "summary": _normalize_text(analysis_raw.get("summary"), fallback_analysis["summary"]),
        }

        feedback = {
            "strengths": _normalize_text_list(feedback_raw.get("strengths"), max_items=5)
            or fallback_feedback["strengths"],
            "improvements": _normalize_text_list(feedback_raw.get("improvements"), max_items=8)
            or fallback_feedback["improvements"],
            "critical_gaps": _normalize_text_list(feedback_raw.get("critical_gaps"), max_items=5)
            or fallback_feedback["critical_gaps"],
            "narrative": _normalize_text(feedback_raw.get("narrative"), fallback_feedback["narrative"]),
        }

        score_breakdown_raw = (
            score_raw.get("breakdown")
            if isinstance(score_raw.get("breakdown"), dict)
            else {}
        )
        breakdown = {
            "completeness": _clamp_int(
                score_breakdown_raw.get("completeness"),
                0,
                25,
                fallback_score["breakdown"]["completeness"],
            ),
            "scalability": _clamp_int(
                score_breakdown_raw.get("scalability"),
                0,
                25,
                fallback_score["breakdown"]["scalability"],
            ),
            "reliability": _clamp_int(
                score_breakdown_raw.get("reliability"),
                0,
                25,
                fallback_score["breakdown"]["reliability"],
            ),
            "clarity": _clamp_int(
                score_breakdown_raw.get("clarity"),
                0,
                25,
                fallback_score["breakdown"]["clarity"],
            ),
        }
        breakdown_total = sum(breakdown.values())
        total = _clamp_int(score_raw.get("total"), 0, 100, breakdown_total)
        grade = _normalize_text(score_raw.get("grade"), _grade_from_total(total)).upper()
        if grade not in _GRADES:
            grade = _grade_from_total(total)

        return {
            "analysis": analysis,
            "feedback": feedback,
            "score": {
                "total": total,
                "breakdown": breakdown,
                "grade": grade,
            },
        }

    def _heuristic_analysis(
        self,
        graph: SystemDesignGraph,
        transcript: str,
        session_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = graph.get_state()
        nodes = state["nodes"]
        edges = state["edges"]
        node_count = len(nodes)
        edge_count = len(edges)
        nodes_by_id = {node["id"]: node for node in nodes}

        entry_id = state.get("entry_point")
        entry_node = nodes_by_id.get(entry_id) if entry_id else None
        entry_point = entry_node["label"] if entry_node else None

        types = [str(node.get("type", "")).lower() for node in nodes]
        labels = [str(node.get("label", "")).strip() for node in nodes]
        identified_components = [label for label in labels if label]
        labels_lower = [label.lower() for label in labels]
        transcript_lower = (transcript or "").lower()

        in_degree = {node["id"]: 0 for node in nodes}
        out_degree = {node["id"]: 0 for node in nodes}
        for edge in edges:
            from_id = edge.get("from")
            to_id = edge.get("to")
            if from_id in out_degree:
                out_degree[from_id] += 1
            if to_id in in_degree:
                in_degree[to_id] += 1

        disconnected_components = [
            nodes_by_id[node_id]["label"]
            for node_id in nodes_by_id
            if (in_degree.get(node_id, 0) + out_degree.get(node_id, 0)) == 0
        ]

        density_ratio = edge_count / max(1, node_count)
        if density_ratio < 0.75:
            connection_density = "sparse"
        elif density_ratio <= 1.5:
            connection_density = "moderate"
        else:
            connection_density = "dense"

        has_client = any(t == "client" for t in types) or any("browser" in l or "client" in l for l in labels_lower)
        has_app = any(t == "service" for t in types)
        has_data = any(t in {"database", "storage"} for t in types) or any(
            marker in " ".join(labels_lower) for marker in ("database", "postgres", "mysql", "storage")
        )
        has_lb = any(t == "load_balancer" for t in types) or any(
            marker in " ".join(labels_lower) for marker in ("load balancer", "gateway", "ingress", "cdn")
        )
        has_cache = any(t == "cache" for t in types) or any(
            marker in " ".join(labels_lower) for marker in ("cache", "redis", "memcached")
        )
        has_queue = any(t == "queue" for t in types) or any(
            marker in " ".join(labels_lower) for marker in ("queue", "kafka", "rabbitmq", "sqs")
        )
        has_monitoring = any("monitor" in label or "observability" in label for label in labels_lower)

        if has_client and has_app and has_data:
            architecture_pattern = "3-tier web architecture"
        elif has_queue and has_app:
            architecture_pattern = "event-driven service architecture"
        elif node_count <= 1:
            architecture_pattern = "single-component architecture"
        else:
            architecture_pattern = "custom distributed architecture"

        missing_standard_components: list[str] = []
        if not any("cdn" in label for label in labels_lower):
            missing_standard_components.append("CDN")
        if not has_cache:
            missing_standard_components.append("Cache layer")
        if not has_queue:
            missing_standard_components.append("Message queue")

        bottlenecks: list[str] = []
        if edge_count > 0:
            threshold = max(2, (edge_count + 1) // 2)
            for node_id, node in nodes_by_id.items():
                degree = in_degree.get(node_id, 0) + out_degree.get(node_id, 0)
                if degree >= threshold:
                    bottlenecks.append(node["label"])
        if sum(1 for t in types if t == "database") == 1:
            db_node = next((n for n in nodes if n.get("type") == "database"), None)
            if db_node is not None:
                db_label = db_node.get("label", "")
                if isinstance(db_label, str) and db_label and db_label not in bottlenecks:
                    bottlenecks.append(db_label)
        bottlenecks = bottlenecks[:3]

        summary_parts = [
            f"The design includes {node_count} component(s) with {connection_density} connectivity.",
        ]
        if entry_point:
            summary_parts.append(f"Entry point appears to be {entry_point}.")
        if missing_standard_components:
            summary_parts.append(
                "Potentially missing standard components: "
                + ", ".join(missing_standard_components[:3])
                + "."
            )
        summary = " ".join(summary_parts)

        strengths: list[str] = []
        if entry_point:
            strengths.append(f"Entry point is clearly identified as {entry_point}.")
        if has_lb:
            strengths.append("Traffic distribution layer is present.")
        if has_data:
            strengths.append("A persistent data layer is represented.")
        if edge_count > 0:
            strengths.append("Component relationships are explicitly connected by edges.")
        strengths = strengths[:3] or ["Core components are identified and connected."]

        improvements: list[str] = []
        if "CDN" in missing_standard_components:
            improvements.append("Add a CDN in front of user-facing traffic for static asset acceleration.")
        if "Cache layer" in missing_standard_components:
            improvements.append("Add a cache layer (for example Redis) to reduce repeated database reads.")
        if "Message queue" in missing_standard_components:
            improvements.append("Introduce an async queue for background jobs and traffic smoothing.")
        if disconnected_components:
            improvements.append("Reconnect isolated components so each node has a clear role in request flow.")
        if entry_point is None:
            improvements.append("Set an explicit entry point component for traversal and explanation clarity.")
        if not improvements:
            improvements.append("Document redundancy and failover behavior for critical paths.")
        improvements = improvements[:5]

        critical_gaps: list[str] = []
        if not has_data:
            critical_gaps.append("No persistent data layer was identified.")
        if entry_point is None:
            critical_gaps.append("Entry point is not explicitly set.")
        if node_count > 1 and edge_count == 0:
            critical_gaps.append("Multiple components exist but no flow edges are defined.")
        critical_gaps = critical_gaps[:3]

        completeness = 0
        completeness += 6 if has_client else 0
        completeness += 6 if (has_lb or any("cdn" in label for label in labels_lower)) else 0
        completeness += 6 if has_app else 0
        completeness += 6 if has_data else 0
        completeness += int(has_cache) + int(has_queue) + int(has_monitoring)
        completeness = _clamp_int(completeness, 0, 25, 0)

        service_count = sum(1 for t in types if t == "service")
        scalability = 0
        scalability += 8 if has_lb else 0
        scalability += 7 if service_count >= 2 else 0
        scalability += 5 if has_cache else 0
        scalability += 5 if has_queue else 0
        scalability = _clamp_int(scalability, 0, 25, 0)

        reliability = 0
        type_counts: dict[str, int] = {}
        for node_type in types:
            type_counts[node_type] = type_counts.get(node_type, 0) + 1
        has_redundancy = any(
            count >= 2 and node_type in {"service", "database", "cache", "queue", "load_balancer"}
            for node_type, count in type_counts.items()
        )
        reliability += 10 if has_redundancy else 0
        reliability += 8 if (edge_count > 0 and not disconnected_components) else 0
        has_failure_notes = any(
            token in transcript_lower
            for token in ("failover", "replica", "redundant", "backup", "multi-az", "high availability")
        )
        reliability += 7 if has_failure_notes else 0
        reliability = _clamp_int(reliability, 0, 25, 0)

        clarity = 0
        clarity += 5 if all(_normalize_text(label) for label in labels) else 0
        clarity += 10 if not disconnected_components else 0
        clarity += 5 if entry_point else 0
        clarity += 5 if (edge_count > 0 and all(_normalize_text(edge.get("label", "")) for edge in edges)) else 0
        clarity = _clamp_int(clarity, 0, 25, 0)

        total = _clamp_int(completeness + scalability + reliability + clarity, 0, 100, 0)
        grade = _grade_from_total(total)

        metadata = session_metadata or {}
        duration_ms = _clamp_int(metadata.get("duration_ms"), 0, 10_000_000, 0)
        if duration_ms > 0:
            narrative = (
                f"This design shows a solid foundation after a {duration_ms // 1000}-second session. "
                f"Prioritize {improvements[0].lower()} and then strengthen reliability on critical paths."
            )
        else:
            narrative = (
                "This design has a workable baseline. Prioritize the highest-impact improvement first, "
                "then iterate on reliability and operational safeguards."
            )

        return {
            "analysis": {
                "architecture_pattern": architecture_pattern,
                "component_count": node_count,
                "identified_components": identified_components,
                "connection_density": connection_density,
                "entry_point": entry_point,
                "disconnected_components": disconnected_components,
                "bottlenecks": bottlenecks,
                "missing_standard_components": missing_standard_components,
                "summary": summary,
            },
            "feedback": {
                "strengths": strengths,
                "improvements": improvements,
                "critical_gaps": critical_gaps,
                "narrative": narrative,
            },
            "score": {
                "total": total,
                "breakdown": {
                    "completeness": completeness,
                    "scalability": scalability,
                    "reliability": reliability,
                    "clarity": clarity,
                },
                "grade": grade,
            },
        }
