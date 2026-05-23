#!/usr/bin/env python3
"""Search local Eureka session JSONL files and print Markdown deep-link results."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SESSION_FILE = "session.jsonl"
MAX_LINES_PER_SESSION = 180
MAX_CONTENT_CHARS = 120_000
DEFAULT_WORKSPACES_ROOTS = ["~/.eureka/workspaces", "~/.craft-agent/workspaces"]


@dataclass
class SearchResult:
    score: float
    workspace_id: str
    session_id: str
    title: str
    summary: str
    snippet: str
    metadata: dict[str, Any]


def expand(path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(path))).resolve()


def tokenize(text: str) -> list[str]:
    return re.findall(r"[\w\-\u4e00-\u9fff]+", text.lower())


def compact(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def markdown_escape(text: str) -> str:
    return text.replace("[", "\\[").replace("]", "\\]")


def format_time(ms: Any) -> str:
    if not isinstance(ms, (int, float)) or ms <= 0:
        return "unknown"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def iter_session_files(workspaces_root: Path, workspace_id: str | None) -> Iterable[tuple[str, Path]]:
    workspace_dirs = [workspaces_root / workspace_id] if workspace_id else sorted(workspaces_root.iterdir())
    for workspace_dir in workspace_dirs:
        sessions_dir = workspace_dir / "sessions"
        if not sessions_dir.is_dir():
            continue
        for session_dir in sorted(sessions_dir.iterdir()):
            session_file = session_dir / SESSION_FILE
            if session_file.is_file():
                yield workspace_dir.name, session_file


def read_jsonl_session(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata: dict[str, Any] = {}
    messages: list[dict[str, Any]] = []
    chars = 0

    with path.open("r", encoding="utf-8", errors="replace") as f:
        for index, line in enumerate(f):
            if index > MAX_LINES_PER_SESSION or chars > MAX_CONTENT_CHARS:
                break
            line = line.strip()
            if not line:
                continue
            chars += len(line)
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if index == 0 and isinstance(obj, dict) and obj.get("id") == path.parent.name:
                metadata = obj
            elif isinstance(obj, dict):
                messages.append(obj)

    if not metadata:
        metadata = {"id": path.parent.name}
    return metadata, messages


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def build_search_document(metadata: dict[str, Any], messages: list[dict[str, Any]]) -> str:
    fields = [
        metadata.get("id"),
        metadata.get("name"),
        metadata.get("preview"),
        metadata.get("workingDirectory"),
        metadata.get("sdkCwd"),
        metadata.get("engine"),
        metadata.get("model"),
        metadata.get("type"),
        metadata.get("todoState"),
        metadata.get("taskAttentionStatus"),
        metadata.get("parentSessionId"),
    ]
    user_texts = [message_text(m) for m in messages if m.get("type") == "user" or m.get("role") == "user"]
    assistant_texts = [message_text(m) for m in messages if m.get("type") == "assistant" or m.get("role") == "assistant"]
    tool_texts = [message_text(m) for m in messages if m.get("type") == "tool" or m.get("role") == "tool"]
    return "\n".join(
        str(x)
        for x in [
            *fields,
            *user_texts[:20],
            *assistant_texts[:12],
            *tool_texts[:6],
        ]
        if x
    )


def summarize(metadata: dict[str, Any], messages: list[dict[str, Any]]) -> str:
    preview = metadata.get("preview")
    if isinstance(preview, str) and preview.strip():
        return compact(preview, 260)

    for message in messages:
        if message.get("type") == "user" or message.get("role") == "user":
            text = message_text(message)
            if text.strip():
                return compact(text, 260)

    name = metadata.get("name") or metadata.get("id") or "Untitled session"
    session_type = metadata.get("type") or "session"
    return f"{session_type} named {name}."


def find_snippet(document: str, query_terms: list[str]) -> str:
    normalized = document.lower()
    best_index = -1
    for term in query_terms:
        index = normalized.find(term.lower())
        if index != -1 and (best_index == -1 or index < best_index):
            best_index = index

    if best_index == -1:
        return compact(document, 220)

    start = max(0, best_index - 90)
    end = min(len(document), best_index + 180)
    prefix = "..." if start > 0 else ""
    suffix = "..." if end < len(document) else ""
    return compact(prefix + document[start:end] + suffix, 260)


def score_document(query: str, metadata: dict[str, Any], document: str) -> float:
    query_lower = query.lower().strip()
    document_lower = document.lower()
    terms = tokenize(query)
    if not terms:
        return 0

    score = 0.0
    if query_lower and query_lower in document_lower:
        score += 20

    field_boost = " ".join(
        str(metadata.get(key) or "")
        for key in ["id", "name", "preview", "workingDirectory", "parentSessionId"]
    ).lower()

    for term in terms:
        occurrences = document_lower.count(term)
        if occurrences:
            score += 2.0 + math.log1p(occurrences)
        if term in field_boost:
            score += 4.0
        if term == str(metadata.get("id", "")).lower():
            score += 30.0

    last_used = metadata.get("lastUsedAt") or metadata.get("updatedAt") or metadata.get("createdAt")
    if isinstance(last_used, (int, float)) and last_used > 0:
        age_days = max(0.0, (datetime.now(tz=timezone.utc).timestamp() - last_used / 1000) / 86400)
        score += max(0.0, 2.0 - age_days / 45)

    return score


def search(args: argparse.Namespace) -> list[SearchResult]:
    roots = [expand(root) for root in (args.workspaces_root or DEFAULT_WORKSPACES_ROOTS)]
    results: list[SearchResult] = []
    seen: set[tuple[str, str]] = set()
    terms = tokenize(args.query)

    existing_roots = [root for root in roots if root.is_dir()]
    if not existing_roots:
        root_list = ", ".join(str(root) for root in roots)
        raise SystemExit(f"No Eureka workspaces roots found: {root_list}")

    for root in existing_roots:
        for workspace_id, session_file in iter_session_files(root, args.workspace_id):
            metadata, messages = read_jsonl_session(session_file)
            document = build_search_document(metadata, messages)
            score = score_document(args.query, metadata, document)
            if score <= 0:
                continue

            session_id = str(metadata.get("id") or session_file.parent.name)
            key = (workspace_id, session_id)
            if key in seen:
                continue
            seen.add(key)

            title = str(metadata.get("name") or session_id)
            results.append(
                SearchResult(
                    score=score,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    title=title,
                    summary=summarize(metadata, messages),
                    snippet=find_snippet(document, terms),
                    metadata=metadata,
                )
            )

    results.sort(key=lambda r: (-r.score, -(r.metadata.get("lastUsedAt") or 0)))
    return results[: args.limit]


def format_roots(roots: list[str] | None) -> str:
    effective_roots = roots or DEFAULT_WORKSPACES_ROOTS
    existing = [str(expand(root)) for root in effective_roots if expand(root).is_dir()]
    if not existing:
        return "none found"
    return ", ".join(f"`{root}`" for root in existing)


def print_markdown(query: str, results: list[SearchResult], roots: list[str] | None) -> None:
    print(f"### Eureka session search results for `{query}`")
    print()
    print(f"Searched: {format_roots(roots)}")
    print()

    if not results:
        print("No matching Eureka sessions found.")
        return

    for index, result in enumerate(results, 1):
        metadata = result.metadata
        link = f"eureka://workspaces/{result.workspace_id}/sessions/{result.session_id}"
        session_type = metadata.get("type") or "session"
        engine = metadata.get("engine") or "unknown engine"
        model = metadata.get("model") or "unknown model"
        updated = format_time(metadata.get("lastUsedAt") or metadata.get("updatedAt") or metadata.get("createdAt"))
        title = markdown_escape(f"{result.title} ({result.session_id})")

        print(f"{index}. [{title}]({link})")
        print(f"   `{session_type}` · `{engine}` · `{model}` · updated {updated} · workspace `{result.workspace_id}`")
        print(f"   Summary: {result.summary}")
        print(f"   Match: {result.snippet}")
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Search local Eureka session files and output Markdown deep links.")
    parser.add_argument("query", help="Natural-language description or keywords to search for.")
    parser.add_argument(
        "--workspaces-root",
        action="append",
        help="Root folder containing Eureka workspace directories. Can be passed multiple times. Defaults to ~/.eureka/workspaces plus legacy ~/.craft-agent/workspaces.",
    )
    parser.add_argument("--workspace-id", help="Limit search to one Eureka workspace id.")
    parser.add_argument("--limit", type=int, default=8, help="Maximum number of results.")
    args = parser.parse_args()

    results = search(args)
    print_markdown(args.query, results, args.workspaces_root)


if __name__ == "__main__":
    main()
