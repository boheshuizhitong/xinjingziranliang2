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

"""Source lifecycle: propagate source withdrawal/restore through a DAG of
Memory and Topic Memory nodes, keeping search and Context in sync."""

from __future__ import annotations

import json
from collections import OrderedDict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from powercontext.artifacts import ArtifactRef, MemoryCitation
from powercontext.builtin.persistence.database import AsyncDatabase
from powercontext.sources import SourceRef

Policy = Literal["all", "any"]
NodeType = Literal["source", "memory", "topic"]


class SourceLifecycleError(ValueError):
    """Raised on lifecycle protocol, registration, or event validation errors."""


class SourceLifecycleEvent(BaseModel):
    """A withdrawal or restore event for one registered Source node."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    node_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    revision: int = Field(gt=0)
    sequence: int = Field(gt=0)
    available: bool

    @field_validator("node_id", "reason")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value


_NODE_FIELDS = (
    "node_id",
    "node_type",
    "ref_json",
    "parents_json",
    "policy",
    "available",
    "revision",
    "sequence",
)


class _Node:
    __slots__ = (
        "node_id",
        "node_type",
        "ref",
        "parents",
        "policy",
        "available",
        "revision",
        "sequence",
    )

    def __init__(
        self,
        node_id: str,
        node_type: NodeType,
        ref: Any,
        parents: tuple[str, ...],
        policy: str,
        available: bool,
        revision: int,
        sequence: int,
    ) -> None:
        self.node_id = node_id
        self.node_type = node_type
        self.ref = ref
        self.parents = parents
        self.policy = policy
        self.available = available
        self.revision = revision
        self.sequence = sequence


_CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS lifecycle_nodes (
    scope_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    node_type TEXT NOT NULL,
    ref_json TEXT NOT NULL,
    parents_json TEXT NOT NULL,
    policy TEXT NOT NULL,
    available INTEGER NOT NULL,
    revision INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    PRIMARY KEY (scope_id, node_id)
)
"""


class ScopedSourceLifecycleService:
    """Per-scope lifecycle DAG service."""

    def __init__(self, runtime: Any, scope_id: str, database: AsyncDatabase) -> None:
        self._runtime = runtime
        self._scope_id = scope_id
        self._db = database
        self._nodes: dict[str, _Node] = {}
        self._loaded = False
        self._lock = asyncio_lock()

    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._db.transaction() as conn:
            await conn.exec_driver_sql(_CREATE_TABLES_SQL)
            result = await conn.execute(
                text(
                    "SELECT node_id, node_type, ref_json, parents_json, policy, "
                    "available, revision, sequence FROM lifecycle_nodes WHERE scope_id = :scope"
                ),
                {"scope": self._scope_id},
            )
            rows = result.all()
        for row in rows:
            (
                node_id,
                node_type,
                ref_json,
                parents_json,
                policy,
                available,
                revision,
                sequence,
            ) = row
            self._nodes[node_id] = _Node(
                node_id=node_id,
                node_type=node_type,  # type: ignore[arg-type]
                ref=self._decode_ref(node_type, ref_json),
                parents=tuple(json.loads(parents_json)),
                policy=policy,
                available=bool(available),
                revision=revision,
                sequence=sequence,
            )
        self._loaded = True

    @staticmethod
    def _encode_ref(node_type: str, ref: Any) -> str:
        if node_type == "source":
            return json.dumps({"source_id": ref.source_id, "source_type": ref.source_type})
        if node_type == "memory":
            return json.dumps(
                {
                    "memory_ref": {
                        "artifact_id": ref.memory_ref.artifact_id,
                        "revision": ref.memory_ref.revision,
                    },
                    "entry_id": ref.entry_id,
                    "entry_version_id": ref.entry_version_id,
                }
            )
        if node_type == "topic":
            return json.dumps(
                {
                    "family": ref.family,
                    "artifact_id": ref.artifact_id,
                    "revision": ref.revision,
                }
            )
        raise SourceLifecycleError(f"unknown node type: {node_type}")

    @staticmethod
    def _decode_ref(node_type: str, ref_json: str) -> Any:
        data = json.loads(ref_json)
        if node_type == "source":
            return SourceRef(source_id=data["source_id"], source_type=data["source_type"])
        if node_type == "memory":
            from powercontext.artifacts import ArtifactRef as _AR

            return MemoryCitation(
                memory_ref=_AR(
                    family="memory",
                    artifact_id=data["memory_ref"]["artifact_id"],
                    revision=data["memory_ref"]["revision"],
                ),
                entry_id=data["entry_id"],
                entry_version_id=data["entry_version_id"],
            )
        if node_type == "topic":
            return ArtifactRef(**data)
        raise SourceLifecycleError(f"unknown node type: {node_type}")

    async def _persist_node(self, node: _Node) -> None:
        async with self._db.transaction() as conn:
            await conn.execute(
                text(
                    "INSERT OR REPLACE INTO lifecycle_nodes "
                    "(scope_id, node_id, node_type, ref_json, parents_json, policy, "
                    "available, revision, sequence) VALUES "
                    "(:scope, :node_id, :node_type, :ref_json, :parents_json, :policy, "
                    ":available, :revision, :sequence)"
                ),
                {
                    "scope": self._scope_id,
                    "node_id": node.node_id,
                    "node_type": node.node_type,
                    "ref_json": self._encode_ref(node.node_type, node.ref),
                    "parents_json": json.dumps(list(node.parents)),
                    "policy": node.policy,
                    "available": 1 if node.available else 0,
                    "revision": node.revision,
                    "sequence": node.sequence,
                },
            )

    def _check_parents(self, parents: tuple[str, ...]) -> None:
        if not parents:
            raise SourceLifecycleError("derived node must have at least one parent")
        if len(set(parents)) != len(parents):
            raise SourceLifecycleError("duplicate parents are not allowed")
        for parent in parents:
            if parent not in self._nodes:
                raise SourceLifecycleError(f"parent node {parent!r} is not registered")
            if parent == "":
                raise SourceLifecycleError("parent must not be empty")

    def _check_cycle(self, node_id: str, parents: tuple[str, ...]) -> None:
        visited: set[str] = set()
        stack = list(parents)
        while stack:
            current = stack.pop()
            if current == node_id:
                raise SourceLifecycleError("registration would create a cycle")
            if current in visited:
                continue
            visited.add(current)
            parent_node = self._nodes.get(current)
            if parent_node is not None and parent_node.node_type != "source":
                stack.extend(parent_node.parents)

    async def register_source(self, node_id: str, ref: SourceRef, *, revision: int) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError("node_id must be a non-empty string")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise SourceLifecycleError("revision must be a positive integer")
        await self._ensure_loaded()
        existing = self._nodes.get(node_id)
        if existing is not None:
            if existing.node_type != "source":
                raise SourceLifecycleError(f"node {node_id!r} already registered as {existing.node_type}")
            if existing.ref.source_id != ref.source_id or existing.revision != revision:
                raise SourceLifecycleError(f"node {node_id!r} registration conflicts")
            return
        node = _Node(
            node_id=node_id,
            node_type="source",
            ref=ref,
            parents=(),
            policy="all",
            available=True,
            revision=revision,
            sequence=0,
        )
        self._nodes[node_id] = node
        await self._persist_node(node)

    async def register_memory(
        self,
        node_id: str,
        citation: MemoryCitation,
        *,
        parents: tuple[str, ...],
        policy: Policy,
    ) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError("node_id must be a non-empty string")
        if policy not in ("all", "any"):
            raise SourceLifecycleError("policy must be 'all' or 'any'")
        await self._ensure_loaded()
        self._check_parents(parents)
        self._check_cycle(node_id, parents)
        existing = self._nodes.get(node_id)
        if existing is not None:
            if existing.node_type != "memory":
                raise SourceLifecycleError(f"node {node_id!r} already registered as {existing.node_type}")
            existing_parents = tuple(existing.parents)
            if existing_parents != tuple(parents) or existing.policy != policy:
                raise SourceLifecycleError(f"node {node_id!r} registration conflicts")
            return
        available = self._compute_available(parents, policy)
        node = _Node(
            node_id=node_id,
            node_type="memory",
            ref=citation,
            parents=tuple(parents),
            policy=policy,
            available=available,
            revision=0,
            sequence=0,
        )
        self._nodes[node_id] = node
        await self._persist_node(node)
        # Apply initial availability to the underlying memory entry.
        await self._set_memory_entry_state(node, available)

    async def register_topic(
        self,
        node_id: str,
        ref: ArtifactRef,
        *,
        parents: tuple[str, ...],
        policy: Policy,
    ) -> None:
        if not isinstance(node_id, str) or not node_id.strip():
            raise SourceLifecycleError("node_id must be a non-empty string")
        if policy not in ("all", "any"):
            raise SourceLifecycleError("policy must be 'all' or 'any'")
        await self._ensure_loaded()
        self._check_parents(parents)
        self._check_cycle(node_id, parents)
        existing = self._nodes.get(node_id)
        if existing is not None:
            if existing.node_type != "topic":
                raise SourceLifecycleError(f"node {node_id!r} already registered as {existing.node_type}")
            existing_parents = tuple(existing.parents)
            if existing_parents != tuple(parents) or existing.policy != policy:
                raise SourceLifecycleError(f"node {node_id!r} registration conflicts")
            return
        available = self._compute_available(parents, policy)
        node = _Node(
            node_id=node_id,
            node_type="topic",
            ref=ref,
            parents=tuple(parents),
            policy=policy,
            available=available,
            revision=0,
            sequence=0,
        )
        self._nodes[node_id] = node
        await self._persist_node(node)

    def _compute_available(self, parents: tuple[str, ...], policy: str) -> bool:
        statuses = [self._nodes[p].available for p in parents]
        return all(statuses) if policy == "all" else any(statuses)

    def _propagate(self) -> list[tuple[_Node, bool]]:
        """Recompute availability for all derived nodes topologically.

        Returns list of (node, changed_to_available) for nodes whose availability changed.
        """
        changed: list[tuple[_Node, bool]] = []
        # Topological order: sources first, then derived nodes.
        remaining = {nid: node for nid, node in self._nodes.items() if node.node_type != "source"}
        resolved: set[str] = {nid for nid, node in self._nodes.items() if node.node_type == "source"}
        while remaining:
            progressed = False
            for nid, node in list(remaining.items()):
                if all(p in resolved for p in node.parents):
                    new_avail = self._compute_available(node.parents, node.policy)
                    if new_avail != node.available:
                        node.available = new_avail
                        changed.append((node, new_avail))
                    resolved.add(nid)
                    del remaining[nid]
                    progressed = True
            if not progressed:
                # Should not happen if cycle checks passed.
                break
        return changed

    async def apply(self, event: SourceLifecycleEvent) -> list[str]:
        await self._ensure_loaded()
        node = self._nodes.get(event.node_id)
        if node is None or node.node_type != "source":
            raise SourceLifecycleError(f"unknown source node: {event.node_id!r}")
        if event.revision != node.revision:
            raise SourceLifecycleError(f"revision mismatch for {event.node_id!r}")
        # Idempotent replay: same sequence + same available state is OK.
        if event.sequence == node.sequence:
            if event.available == node.available:
                return self._active_nodes()
            raise SourceLifecycleError("same sequence with different state")
        if event.sequence < node.sequence:
            raise SourceLifecycleError("sequence must be monotonically increasing")
        node.available = event.available
        node.sequence = event.sequence
        changed = self._propagate()
        # Persist the source node update.
        await self._persist_node(node)
        for changed_node, _ in changed:
            await self._persist_node(changed_node)
        # Apply memory state changes.
        for changed_node, available in changed:
            if changed_node.node_type == "memory":
                await self._set_memory_entry_state(changed_node, available)
        return self._active_nodes()

    def _active_nodes(self) -> list[str]:
        return sorted(nid for nid, node in self._nodes.items() if node.available)

    async def _set_memory_entry_state(self, node: _Node, available: bool) -> None:
        """Call forget/reactivate on the underlying memory entry."""
        runtime = self._runtime
        async with runtime._context(self._scope_id) as context:
            service = context.artifacts.memory
            current = await service.head(context.artifacts.memory_artifact_id)
            entry = await service.validate_citation(node.ref)
            if available:
                await service.reactivate(current, entries=(entry,), reason="source-restored")
            else:
                await service.forget(current, entries=(entry,), reason="source-withdrawn")

    async def resolve(self, node_id: str, *, purpose: str) -> Any:
        await self._ensure_loaded()
        node = self._nodes.get(node_id)
        if node is None:
            raise SourceLifecycleError(f"unknown node: {node_id!r}")
        if purpose not in ("generation", "audit"):
            raise SourceLifecycleError(f"unknown purpose: {purpose!r}")
        if purpose == "generation" and not node.available:
            raise SourceLifecycleError(f"node {node_id!r} is not available for generation")
        return node.ref

    def inactive_topic_refs(self) -> set[tuple[str, str, int]]:
        """Return (family, artifact_id, revision) for inactive topic nodes."""
        return {
            (node.ref.family, node.ref.artifact_id, node.ref.revision)
            for node in self._nodes.values()
            if node.node_type == "topic" and not node.available
        }


class LifecycleApplication:
    """Select the scoped lifecycle service."""

    def __init__(self, runtime: Any, database: AsyncDatabase) -> None:
        self._runtime = runtime
        self._db = database
        self._cache: dict[str, ScopedSourceLifecycleService] = {}

    def for_scope(self, scope_id: str, /) -> ScopedSourceLifecycleService:
        if scope_id not in self._cache:
            self._cache[scope_id] = ScopedSourceLifecycleService(self._runtime, scope_id, self._db)
        return self._cache[scope_id]


def asyncio_lock() -> Any:
    import asyncio

    return asyncio.Lock()
