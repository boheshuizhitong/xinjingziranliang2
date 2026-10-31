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

"""Cross-call embedding request coalescing with a bounded LRU vector cache."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from typing import Any

from powercontext.builtin.inference.models import EmbeddingResult, EmbeddingVector, InferenceUsage


class _Batch:
    """One in-flight underlying embed call shared by every waiter."""

    def __init__(self, texts: tuple[str, ...]) -> None:
        self.texts = texts
        self._done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.vectors: dict[str, EmbeddingVector] | None = None
        self.usage: InferenceUsage | None = None
        self.error: BaseException | None = None
        # Per-text futures resolved when this batch settles.
        self.text_futures: dict[str, asyncio.Future[EmbeddingVector]] = {}

    async def run(self, model: Any) -> None:
        try:
            result = await model.embed(self.texts)
            if len(result.vectors) != len(self.texts):
                raise ValueError("embedding vector count does not match text count")
            self.vectors = dict(zip(self.texts, result.vectors, strict=True))
            self.usage = result.usage
        except BaseException as exc:
            self.error = exc
        finally:
            if not self._done.done():
                self._done.set_result(None)

    async def wait(self) -> None:
        await self._done
        if self.error is not None:
            raise self.error


class CoalescingEmbeddingModel:
    """Share concurrent embedding work and cache successful vectors.

    Parameters
    ----------
    model:
        The underlying embedding model to wrap. Its ``profile`` is exposed.
    max_batch_size:
        Maximum number of distinct texts per underlying request.
    coalesce_ms:
        Coalescing window in milliseconds; concurrent calls arriving within
        this window share one batch. ``0`` flushes immediately.
    cache_size:
        Capacity of the LRU cache of successful vectors. ``0`` disables the
        cross-call cache but still shares in-flight work.
    """

    def __init__(
        self,
        model: Any,
        *,
        max_batch_size: int = 64,
        coalesce_ms: float = 5.0,
        cache_size: int = 1024,
    ) -> None:
        if not isinstance(max_batch_size, int) or isinstance(max_batch_size, bool) or max_batch_size < 1:
            raise ValueError("max_batch_size must be a positive integer")
        if not isinstance(cache_size, int) or isinstance(cache_size, bool) or cache_size < 0:
            raise ValueError("cache_size must be a non-negative integer")
        self._model = model
        self.profile = model.profile
        self._max_batch = max_batch_size
        self._delay = coalesce_ms / 1000.0
        self._cache_size = cache_size
        self._cache: OrderedDict[str, EmbeddingVector] = OrderedDict()
        self._lock = asyncio.Lock()
        self._inflight: dict[str, _Batch] = {}
        self._pending_texts: dict[str, asyncio.Future[EmbeddingVector]] = {}
        self._flush_task: asyncio.Task[None] | None = None
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def embed(self, texts: tuple[str, ...] | list[str], /) -> EmbeddingResult:
        if not texts:
            return EmbeddingResult(vectors=(), usage=InferenceUsage(requests=0))

        result: list[EmbeddingVector | None] = [None] * len(texts)
        needed: list[tuple[int, str]] = []
        for index, text in enumerate(texts):
            if self._cache_size > 0 and text in self._cache:
                result[index] = self._cache[text]
                self._cache.move_to_end(text)
            else:
                needed.append((index, text))

        if not needed:
            return EmbeddingResult(
                vectors=tuple(result),  # type: ignore[arg-type]
                usage=InferenceUsage(requests=0, input_tokens=0, output_tokens=0),
            )

        unique_needed = list(dict.fromkeys(text for _, text in needed))

        async with self._lock:
            inflight_batches: dict[_Batch, list[str]] = {}
            fresh_texts: list[str] = []
            for text in unique_needed:
                existing = self._inflight.get(text)
                if existing is not None:
                    inflight_batches.setdefault(existing, []).append(text)
                else:
                    fresh_texts.append(text)

            collector_futures: dict[str, asyncio.Future[EmbeddingVector]] = {}
            loop = asyncio.get_running_loop()
            for text in fresh_texts:
                if text not in self._pending_texts:
                    self._pending_texts[text] = loop.create_future()
                collector_futures[text] = self._pending_texts[text]

            if fresh_texts and self._flush_task is None:
                self._flush_task = asyncio.create_task(self._flush_after_delay())

        # Wait on in-flight batches. Shield so cancelling this caller does
        # not cancel the shared underlying batch.
        for batch in inflight_batches:
            await asyncio.shield(batch.wait())

        # Wait on pending (collector) futures.
        for future in collector_futures.values():
            await asyncio.shield(future)

        # Determine which batches this call waited on (for usage).
        waited_batches: set[_Batch] = set(inflight_batches.keys())
        for fut in collector_futures.values():
            batch = getattr(fut, "_batch", None)
            if batch is not None:
                waited_batches.add(batch)

        # Assemble results.
        for index, text in needed:
            existing = self._inflight.get(text)
            if existing is not None and existing.vectors is not None and text in existing.vectors:
                result[index] = existing.vectors[text]
            elif self._cache_size > 0 and text in self._cache:
                result[index] = self._cache[text]
            else:
                fut = collector_futures.get(text)
                if fut is not None:
                    result[index] = fut.result()

        total_requests = 0
        total_input = 0
        total_output = 0
        for batch in waited_batches:
            if batch.usage is not None:
                total_requests += batch.usage.requests
                total_input += batch.usage.input_tokens or 0
                total_output += batch.usage.output_tokens or 0

        usage = InferenceUsage(
            requests=total_requests,
            input_tokens=total_input if total_requests else 0,
            output_tokens=total_output,
        )
        return EmbeddingResult(vectors=tuple(result), usage=usage)  # type: ignore[arg-type]

    async def _flush_after_delay(self) -> None:
        try:
            await asyncio.sleep(self._delay)
            async with self._lock:
                if not self._pending_texts:
                    self._flush_task = None
                    return
                pending = dict(self._pending_texts)
                self._pending_texts.clear()
                self._flush_task = None

            texts = list(pending.keys())
            for start in range(0, len(texts), self._max_batch):
                chunk = tuple(texts[start : start + self._max_batch])
                batch = _Batch(chunk)
                batch.text_futures = {t: pending[t] for t in chunk}
                for text, fut in batch.text_futures.items():
                    setattr(fut, "_batch", batch)
                async with self._lock:
                    for text in chunk:
                        self._inflight[text] = batch
                task = asyncio.create_task(self._run_batch(batch))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._flush_task = None

    async def _run_batch(self, batch: _Batch) -> None:
        await batch.run(self._model)
        async with self._lock:
            for text in batch.texts:
                self._inflight.pop(text, None)
        if batch.error is not None:
            for text, fut in batch.text_futures.items():
                if not fut.done():
                    fut.set_exception(batch.error)
            return
        assert batch.vectors is not None
        for text, fut in batch.text_futures.items():
            if not fut.done():
                fut.set_result(batch.vectors[text])
            if self._cache_size > 0:
                self._cache[text] = batch.vectors[text]
                self._cache.move_to_end(text)
                while len(self._cache) > self._cache_size:
                    self._cache.popitem(last=False)
