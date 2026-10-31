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

"""HTTP-backed listwise Memory reranking over a fixed offline scoring protocol."""

from __future__ import annotations

import math

import httpx

from powercontext.builtin.artifacts.memory.models import MemoryHit
from powercontext.builtin.artifacts.memory.reranking import MemoryRerankDecision
from powercontext.builtin.inference import InferenceUsage


class HTTPMemoryReranker:
    """Score Memory candidates against a query through an offline HTTP service.

    Candidates are split into batches of at most ``batch_size`` and scored by
    global 1-based rank. Results across batches participate in one global
    selection ordered by score descending, breaking ties on the original rank
    ascending. Actual HTTP request count is reported through
    :class:`InferenceUsage`.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        client: httpx.AsyncClient,
        batch_size: int = 32,
        policy_id: str = "http-cross-encoder-v1",
    ) -> None:
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
            raise ValueError("batch_size must be a positive integer")  # noqa: TRY003
        self._endpoint = endpoint
        self._client = client
        self._batch_size = batch_size
        self.policy_id = policy_id

    async def rerank(
        self,
        query: str,
        candidates: tuple[MemoryHit, ...],
        limit: int,
        /,
    ) -> MemoryRerankDecision:
        """Score all candidates in batches and select the top ``limit`` globally."""

        candidate_count = len(candidates)
        if candidate_count < 1:
            raise ValueError("rerank requires at least one candidate")  # noqa: TRY003
        if limit < 1 or limit > candidate_count:
            raise ValueError("rerank limit must be between one and the candidate count")  # noqa: TRY003

        scores: dict[int, float] = {}
        requests = 0
        for start in range(0, candidate_count, self._batch_size):
            ranks = tuple(range(start + 1, min(start + self._batch_size, candidate_count) + 1))
            payload = {
                "query": query,
                "candidates": [
                    {"rank": rank, "text": candidates[rank - 1].text} for rank in ranks
                ],
            }
            response = await self._client.post(self._endpoint, json=payload)
            response.raise_for_status()
            batch_scores = _decode_scores(response, expected_ranks=set(ranks))
            scores.update(batch_scores)
            requests += 1

        ordered = sorted(range(1, candidate_count + 1), key=lambda rank: (-scores[rank], rank))
        selected_ranks = tuple(ordered[:limit])
        return MemoryRerankDecision(
            selected_ranks=selected_ranks,
            usage=InferenceUsage(requests=requests),
            discarded_rank_count=candidate_count - len(selected_ranks),
        )


def _decode_scores(response: httpx.Response, *, expected_ranks: set[int]) -> dict[int, float]:
    """Validate the strict ``{"scores": [...]}`` schema for one batch."""

    try:
        body = response.json()
    except ValueError as error:
        raise ValueError("rerank service returned invalid JSON") from error

    if not isinstance(body, dict) or set(body.keys()) != {"scores"}:
        raise ValueError("rerank response must be an object with exactly a 'scores' key")  # noqa: TRY003
    raw_scores = body["scores"]
    if not isinstance(raw_scores, list):
        raise ValueError("rerank 'scores' must be a list")  # noqa: TRY003

    scores: dict[int, float] = {}
    for entry in raw_scores:
        if not isinstance(entry, dict) or set(entry.keys()) != {"rank", "score"}:
            raise ValueError("each rerank score must contain exactly 'rank' and 'score'")  # noqa: TRY003
        rank = entry["rank"]
        if isinstance(rank, bool) or not isinstance(rank, int):
            raise ValueError("rerank score rank must be an integer")  # noqa: TRY003
        score = entry["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError("rerank score must be a finite number")  # noqa: TRY003
        if rank in scores:
            raise ValueError(f"rerank score rank {rank} was returned more than once")  # noqa: TRY003
        scores[rank] = float(score)

    if set(scores.keys()) != expected_ranks:
        raise ValueError("rerank scores must cover exactly the requested batch ranks")  # noqa: TRY003
    return scores


__all__ = ["HTTPMemoryReranker"]
