"""
Session-aware chat agent for post-session follow-up questions.
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

CHAT_SYSTEM_PROMPT = """\
You are Mirage, a system design interview coach.
Use the provided SESSION CONTEXT as ground truth for this conversation.
Answer clearly and practically in 2-6 sentences unless the user asks for more detail.
If the question cannot be answered from the context, say that directly and suggest what
additional design details are needed.
"""


def _content_to_text(content: Any) -> str:
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


class ChatAgent:
    """
    Generates a single response for a user follow-up question.
    """

    def __init__(self, chat_seed_context: str, llm: Any | None = None) -> None:
        self.chat_seed_context = (chat_seed_context or "").strip()
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

    def respond(self, message: str) -> str:
        prompt = (message or "").strip()
        if not prompt:
            return "Please share a specific question about your architecture."

        fallback = self._fallback_response(prompt)
        if self.llm is None:
            return fallback

        try:
            result = self.llm.invoke(
                [
                    SystemMessage(
                        content=(
                            f"{CHAT_SYSTEM_PROMPT}\n\n"
                            "SESSION CONTEXT:\n"
                            f"{self.chat_seed_context or 'No session context available.'}"
                        )
                    ),
                    HumanMessage(content=prompt),
                ]
            )
            text = _content_to_text(getattr(result, "content", "")).strip()
            return text or fallback
        except Exception:  # noqa: BLE001
            return fallback

    def _fallback_response(self, prompt: str) -> str:
        lower = prompt.lower()
        if "scale" in lower or "scalability" in lower:
            return (
                "From your saved analysis, the main scalability improvements are to "
                "add caching and remove single bottlenecks on the request path."
            )
        if "reliab" in lower or "failure" in lower:
            return (
                "The review suggests improving reliability by adding redundancy on "
                "critical components and defining clearer failover behavior."
            )
        return (
            "Based on your session analysis, focus first on the top listed improvement, "
            "then re-check score dimensions with the largest gaps."
        )
