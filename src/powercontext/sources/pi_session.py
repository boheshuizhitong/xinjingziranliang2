# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pi v3 session source: capture the visible event path of one chosen branch.

Pi sessions are JSONL graphs organized through ``parentId``. The chosen leaf
and its ancestors form one history path; each visible event on that path becomes
an independently-addressable CAPTURED Source. The connector re-parses the whole
file on every run and submits only events not already imported, persisting a
checkpoint through :class:`ConnectorLifecycle` so branch switches, appends,
restarts and corruptions resume from the recorded progress.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
    TextEvidence,
)
from powercontext.sources.models import Source, SourceMaterialization

PI_EVENT_SOURCE_NAME = "pi-event"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
_SOURCE_ID_PREFIX = "pi:"

_CONTROL_EVENT_TYPES: frozenset[str] = frozenset()


def pi_event_source_id(session_id: str, event_id: str) -> str:
    """Build the stable, delimiter-safe Source identity for one Pi event."""

    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be a non-empty string")  # noqa: TRY003
    if not isinstance(event_id, str) or not event_id:
        raise ValueError("event_id must be a non-empty string")  # noqa: TRY003
    identity = f"{_SOURCE_ID_PREFIX}{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        raise ValueError("pi event source_id exceeds the 256 character limit")  # noqa: TRY003
    return identity


class PiSessionInput(BaseModel):
    """A complete offline Pi v3 JSONL session to parse for one branch."""

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """One visible event on a chosen Pi branch path."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]


class PiEventSource(Source):
    """A captured Pi event whose identity is ``(session_id, event_id)``."""

    source_id: str
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, Any]


class PiEventAdapter:
    """Resolve and read :class:`PiEventInput` as a captured :class:`PiEventSource`."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        source_id = pi_event_source_id(value.session_id, value.event_id)
        return PiEventSource(
            name=source_id,
            definition_version="1",
            materialization=SourceMaterialization.CAPTURED,
            source_id=source_id,
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=value.record,
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=source.record,
        )


class PiEventTextEvidenceProjection:
    """Project a captured Pi event into the canonical text-evidence shape."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        metadata: dict[str, JsonValue] = {
            "session_id": source.session_id,
            "event_id": source.event_id,
            "parent_id": source.parent_id,
            "event_type": source.event_type,
            "role": source.role,
        }
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.source_id,
            content=source.content,
            metadata=metadata,
        )


PI_EVENT_SOURCE_ADAPTER = PiEventAdapter()
PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition(
    PI_EVENT_SOURCE_ADAPTER,
    projections=(PiEventTextEvidenceProjection(),),
)


def _compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _text_blocks(content: Any) -> list[str]:
    """Collect visible text pieces from a message/content block list, in order."""

    blocks: list[str] = []
    if isinstance(content, str):
        if content:
            blocks.append(content)
        return blocks
    if not isinstance(content, list):
        return blocks
    for block in content:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                blocks.append(text)
        elif kind == "toolCall":
            name = block.get("name", "")
            call_id = block.get("id", "")
            arguments = block.get("arguments", {})
            blocks.append(f"[tool_call {name} {call_id}] {_compact_json(arguments)}")
        # thinking and image blocks carry no visible text evidence.
    return blocks


def _event_body(record: dict[str, Any]) -> tuple[str, str] | None:
    """Return ``(role, body)`` for a visible record, or ``None`` for control nodes."""

    event_type = record.get("type")

    if event_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return None
        role = message.get("role")
        if not isinstance(role, str) or not role:
            return None
        content = message.get("content")

        if role == "toolResult":
            text = "\n".join(_text_blocks(content))
            body = f"[tool_result {message.get('toolName', '')} {message.get('toolCallId', '')}] {text}"
            return role, body
        if role == "bashExecution":
            command = message.get("command", "")
            output = message.get("output", "")
            body = f"$ {command}\n{output}"
            return role, body

        blocks = _text_blocks(content)
        if not blocks:
            return None
        return role, "\n".join(blocks)

    if event_type in {"compaction", "branch_summary"}:
        summary = record.get("summary")
        if not isinstance(summary, str) or not summary:
            return None
        return event_type, summary

    if event_type == "custom_message":
        blocks = _text_blocks(record.get("content"))
        if not blocks:
            return None
        return "custom", "\n".join(blocks)

    # model_change, thinking_level_change and other control nodes have no text.
    return None


def _load_records(content: bytes) -> tuple[str, dict[str, dict[str, Any]], list[str]]:
    """Decode and fully validate the JSONL graph; return (session_id, nodes, order)."""

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("pi session must be strict UTF-8") from error

    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise ValueError("pi session is empty")  # noqa: TRY003

    try:
        first = json.loads(lines[0])
    except json.JSONDecodeError as error:
        raise ValueError(f"invalid session header: {error}") from error
    if not isinstance(first, dict) or first.get("type") != "session" or first.get("version") != 3:
        raise ValueError("first record must be a v3 session header")  # noqa: TRY003
    session_id = first.get("id")
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session header id must be a non-empty string")  # noqa: TRY003

    nodes: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for line in lines[1:]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid pi record: {error}") from error
        if not isinstance(record, dict):
            raise ValueError("pi record must be a JSON object")  # noqa: TRY003
        event_id = record.get("id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("pi record id must be a non-empty string")  # noqa: TRY003
        if event_id in nodes:
            raise ValueError(f"duplicate pi record id {event_id!r}")  # noqa: TRY003
        parent_id = record.get("parentId")
        if parent_id is not None and parent_id not in nodes:
            raise ValueError(f"pi record {event_id!r} references missing parent {parent_id!r}")  # noqa: TRY003
        nodes[event_id] = record
        order.append(event_id)

    return session_id, nodes, order


def _branch_path(
    session_id: str,
    nodes: dict[str, dict[str, Any]],
    order: list[str],
    leaf_id: str | None,
) -> list[dict[str, Any]]:
    """Return the root-to-leaf chain of records for the chosen leaf."""

    if leaf_id is None:
        if not order:
            raise ValueError("pi session has no event records")  # noqa: TRY003
        leaf_id = order[-1]
    if leaf_id not in nodes:
        raise ValueError(f"pi leaf {leaf_id!r} is not a record in the session")  # noqa: TRY003

    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    current: str | None = leaf_id
    while current is not None:
        if current in seen:
            raise ValueError("pi session contains a parent cycle")  # noqa: TRY003
        seen.add(current)
        record = nodes[current]
        chain.append(record)
        current = record.get("parentId")
    chain.reverse()
    return chain


def parse_pi_session(session: PiSessionInput) -> tuple[PiEventInput, ...]:
    """Parse a Pi v3 session and return the chosen branch's visible events."""

    session_id, nodes, order = _load_records(session.content)
    chain = _branch_path(session_id, nodes, order, session.leaf_id)

    events: list[PiEventInput] = []
    for record in chain:
        rendered = _event_body(record)
        if rendered is None:
            continue
        role, body = rendered
        event_id = record["id"]
        events.append(
            PiEventInput(
                session_id=session_id,
                event_id=event_id,
                parent_id=record.get("parentId"),
                event_type=record.get("type", ""),
                role=role,
                content=f"{role}: {body}",
                record=record,
            )
        )
    return tuple(events)


def _record_fingerprint(record: dict[str, Any]) -> str:
    return hashlib.sha256(_compact_json(record).encode("utf-8")).hexdigest()


class PiSessionConnector:
    """Incrementally capture the visible events of one Pi session branch."""

    name = PI_SESSION_CONNECTOR_NAME
    version = "1"
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: str | Path, leaf_id: str | None = None) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        content = self._path.read_bytes()
        session_id, nodes, order = _load_records(content)
        chain = _branch_path(session_id, nodes, order, self._leaf_id)

        imported: dict[str, dict[str, str]] = {}
        previous = session.checkpoint
        if isinstance(previous, dict):
            stored = previous.get("events")
            if isinstance(stored, dict):
                for sid, by_event in stored.items():
                    if isinstance(sid, str) and isinstance(by_event, dict):
                        imported[sid] = {
                            eid: digest
                            for eid, digest in by_event.items()
                            if isinstance(eid, str) and isinstance(digest, str)
                        }

        # First pass: validate every already-imported record on this branch still
        # matches what was captured. A rewrite is a hard failure before any new
        # submission, so a bad run cannot advance the checkpoint.
        visible: list[PiEventInput] = []
        for record in chain:
            rendered = _event_body(record)
            if rendered is None:
                continue
            role, body = rendered
            event_id = record["id"]
            digest = _record_fingerprint(record)
            existing = imported.get(session_id, {}).get(event_id)
            if existing is not None and existing != digest:
                raise ValueError(f"already-imported event {event_id!r} was modified")  # noqa: TRY003
            visible.append(
                PiEventInput(
                    session_id=session_id,
                    event_id=event_id,
                    parent_id=record.get("parentId"),
                    event_type=record.get("type", ""),
                    role=role,
                    content=f"{role}: {body}",
                    record=record,
                )
            )

        by_event = dict(imported.get(session_id, {}))
        for event in visible:
            if event.event_id in by_event:
                continue
            await session.submit(event.event_id, PI_EVENT_SOURCE_NAME, event)
            by_event[event.event_id] = _record_fingerprint(event.record)

        checkpoint: dict[str, dict[str, dict[str, str]]] = {**imported, session_id: by_event}
        return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint={"events": checkpoint})


__all__ = [
    "PI_EVENT_SOURCE_ADAPTER",
    "PI_EVENT_SOURCE_DEFINITION",
    "PI_EVENT_SOURCE_NAME",
    "PI_SESSION_CONNECTOR_NAME",
    "PiEventInput",
    "PiEventSource",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
    "pi_event_source_id",
]
