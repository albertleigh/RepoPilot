"""
Conversation compression utilities.

Provides token estimation, micro-compaction of old tool results, and
full auto-compaction via LLM summarisation.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

TOKEN_THRESHOLD = 100_000


def estimate_tokens(messages: list) -> int:
    """Rough token count (≈ 1 token per 4 chars of JSON)."""
    return len(json.dumps(messages, default=str)) // 4


def microcompact(messages: list) -> None:
    """Clear old tool-result payloads, keeping the three most recent."""
    parts: list = []
    for msg in messages:
        # Anthropic format: tool results inside user message content list
        if msg.get("role") == "user" and isinstance(msg.get("content"), list):
            for part in msg["content"]:
                if isinstance(part, dict) and part.get("type") == "tool_result":
                    parts.append(part)
        # OpenAI format: role="tool" messages
        elif msg.get("role") == "tool":
            parts.append(msg)
    if len(parts) <= 3:
        return
    for part in parts[:-3]:
        if isinstance(part.get("content"), str) and len(part["content"]) > 100:
            part["content"] = "[cleared]"


def auto_compact(messages: list, llm_client, workdir: Path, prefix: str = "") -> list:
    """Summarise *messages* via the LLM and return a fresh pair.

    Saves the full transcript to ``<workdir>/.transcripts/`` before
    compacting.

    *prefix* is prepended to the filename, e.g. ``"PM_"`` or
    ``"EM_myrepo_"``.
    """
    transcript_dir = workdir / ".transcripts"
    transcript_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    path = transcript_dir / f"{prefix}{stamp}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for msg in messages:
            f.write(json.dumps(msg, default=str) + "\n")

    conv_text = json.dumps(messages, default=str)[:80_000]
    summary = llm_client.send_message(
        f"Summarize the following conversation for continuity:\n{conv_text}"
    )
    return [
        {"role": "user",
         "content": f"[Compressed. Transcript: {path}]\n{summary}"},
        {"role": "assistant",
         "content": "Understood. Continuing with summary context."},
    ]
