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

"""SeekDB native hybrid search: one SQL for both FTS and vector candidates."""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import (
    EmbeddingProfile,
    MemoryCapabilities,
    MemoryProjection,
    MemorySearchChannels,
    MemorySearchRequest,
)
from powercontext.builtin.persistence.memory_index import memory_channel_hits
from powercontext.builtin.persistence.oceanbase.memory_index import (
    OceanBaseMemoryFTSIndex,
    OceanBaseMemoryVectorIndex,
)
from powercontext.builtin.persistence.tags import memory_tag_parameters, memory_tag_sql

_HYBRID_SQL = """
SELECT * FROM (
    SELECT
        h.memory_artifact_id,
        h.head_revision,
        h.entry_id,
        h.entry_version_id,
        v.text,
        CAST(NULL AS DECIMAL(20,10)) AS distance,
        'fts' AS channel
    FROM pc_memory_entry_heads AS h
    JOIN pc_memory_entry_versions AS v
      ON v.scope_id = h.scope_id
     AND v.memory_artifact_id = h.memory_artifact_id
     AND v.entry_version_id = h.entry_version_id
    WHERE h.scope_id = :scope_id
      AND h.memory_artifact_id IN :memory_artifact_ids
      AND MATCH(h.searchable_text) AGAINST(:analyzed_query IN BOOLEAN MODE)
    UNION ALL
    SELECT
        ve.memory_artifact_id,
        ve.head_revision,
        ve.entry_id,
        ve.entry_version_id,
        ver.text,
        l2_distance(ve.embedding, :query_vector) AS distance,
        'vector' AS channel
    FROM pc_memory_vector_entries AS ve
    JOIN pc_memory_entry_versions AS ver
      ON ver.scope_id = ve.scope_id
     AND ver.memory_artifact_id = ve.memory_artifact_id
     AND ver.entry_version_id = ve.entry_version_id
    WHERE ve.scope_id = :scope_id
      AND ve.memory_artifact_id IN :memory_artifact_ids
) AS combined
ORDER BY combined.channel DESC, combined.distance ASC
LIMIT :candidate_limit
"""

_HYBRID_SQL_TAGGED = _HYBRID_SQL.replace(
    "MATCH(h.searchable_text)",
    "MATCH(h.searchable_text)",
).replace(
    "UNION ALL",
    memory_tag_sql("h") + "\n    UNION ALL",
).replace(
    "WHERE ve.scope_id",
    "WHERE ve.scope_id",
).replace(
    ") AS combined",
    memory_tag_sql("ve") + "\n) AS combined",
)


class SeekDBHybridMemoryIndex:
    """Run FTS + vector candidates in a single native seekdb statement.

    Delegates writes and single-channel queries to the OceanBase FTS and vector
    indexes. For mode="hybrid" issues one UNION ALL statement that hits both the
    TEXT RETRIEVAL SCAN and the VECTOR INDEX.
    """

    def __init__(self, fts_index: OceanBaseMemoryFTSIndex, vector_index: OceanBaseMemoryVectorIndex) -> None:
        self._fts = fts_index
        self._vector = vector_index
        fts_caps = fts_index.capabilities
        vec_caps = vector_index.capabilities
        self.capabilities = MemoryCapabilities(
            fts=True,
            vector=True,
            hybrid=True,
            embedding_profile=vec_caps.embedding_profile,
            tag_filter=fts_caps.tag_filter and vec_caps.tag_filter,
        )
        self.tables = tuple(table for table in (*fts_index.tables, *vector_index.tables))
        self._hybrid_sql = text(_HYBRID_SQL).bindparams(
            bindparam("memory_artifact_ids", expanding=True),
        )
        self._hybrid_sql_tagged = text(_HYBRID_SQL_TAGGED).bindparams(
            bindparam("memory_artifact_ids", expanding=True),
            bindparam("tag_keys", expanding=True),
            bindparam("tag_hashes", expanding=True),
        )

    async def initialize(self, connection: AsyncConnection, /) -> None:
        await self._fts.initialize(connection)
        await self._vector.initialize(connection)

    async def replace(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memory_ref: ArtifactRef,
        projections: tuple[MemoryProjection, ...],
        /,
    ) -> None:
        await self._fts.replace(connection, scope_id, memory_ref, projections)
        await self._vector.replace(connection, scope_id, memory_ref, projections)

    async def delete(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memory_ref: ArtifactRef,
        entry_ids: tuple[str, ...],
        /,
    ) -> None:
        await self._fts.delete(connection, scope_id, memory_ref, entry_ids)
        await self._vector.delete(connection, scope_id, memory_ref, entry_ids)

    async def upsert(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memory_ref: ArtifactRef,
        projections: tuple[MemoryProjection, ...],
        /,
    ) -> None:
        await self._fts.upsert(connection, scope_id, memory_ref, projections)
        await self._vector.upsert(connection, scope_id, memory_ref, projections)

    async def search(
        self,
        connection: AsyncConnection,
        scope_id: str,
        request: MemorySearchRequest,
        /,
    ) -> MemorySearchChannels:
        if request.mode == "hybrid":
            return await self._search_hybrid(connection, scope_id, request)
        # Delegate single-channel searches to the underlying indexes.
        fts_channels = await self._fts.search(connection, scope_id, request)
        vec_channels = await self._vector.search(connection, scope_id, request)
        return MemorySearchChannels(fts=fts_channels.fts, vector=vec_channels.vector)

    async def _search_hybrid(
        self,
        connection: AsyncConnection,
        scope_id: str,
        request: MemorySearchRequest,
        /,
    ) -> MemorySearchChannels:
        if request.embedding_profile != self._vector.profile or request.query_vector is None:
            from powercontext.builtin.artifacts.memory import CapabilityNotSupportedError

            raise CapabilityNotSupportedError("embedding-profile")
        if not await self._vector.vector_complete(connection, scope_id, request.memories, self._vector.profile):
            from powercontext.builtin.artifacts.memory import CapabilityNotSupportedError

            raise CapabilityNotSupportedError("vector")
        sql = self._hybrid_sql if request.tag_filter is None else self._hybrid_sql_tagged
        rows = (
            await connection.execute(
                sql,
                {
                    "scope_id": scope_id,
                    "memory_artifact_ids": tuple(m.artifact_id for m in request.memories),
                    "analyzed_query": request.analyzed_query,
                    "query_vector": request.query_vector,
                    "candidate_limit": request.candidate_limit,
                    **memory_tag_parameters(request.tag_filter),
                },
            )
        ).mappings().all()
        fts_rows = [r for r in rows if r["channel"] == "fts"]
        vec_rows = [r for r in rows if r["channel"] == "vector"]
        return MemorySearchChannels(
            fts=memory_channel_hits(fts_rows, request.memories),
            vector=memory_channel_hits(vec_rows, request.memories),
        )

    async def vector_complete(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memories: tuple[ArtifactRef, ...],
        profile: EmbeddingProfile,
        /,
    ) -> bool:
        return await self._vector.vector_complete(connection, scope_id, memories, profile)

    async def hydrate(
        self,
        connection: AsyncConnection,
        scope_id: str,
        projections: tuple[MemoryProjection, ...],
        /,
    ) -> tuple[MemoryProjection, ...]:
        projections = await self._fts.hydrate(connection, scope_id, projections)
        projections = await self._vector.hydrate(connection, scope_id, projections)
        return projections
