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

"""Interoperable context packing and prefix-delta transfer protocol.

A :class:`ContextPack` is a self-describing, checksummed byte bundle. A
:class:`ContextPackDelta` reuses a prefix of an existing pack and carries only
the appended suffix bytes. Both are serialized as compact, sorted-key JSON
with Base64 item payloads so a receiver can rebuild the target pack purely from
wire bytes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass

PACK_SCHEMA = "powercontext.context-pack.v1"
DELTA_SCHEMA = "powercontext.context-pack-delta.v1"

_DEFAULT_CHUNK_BYTES = 512


class ContextPackError(ValueError):
    """Raised when a pack or delta fails protocol or chunk validation."""


def _canonical_json(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(value: str) -> bytes:
    if not isinstance(value, str):
        raise ContextPackError("pack items must be Base64 strings")  # noqa: TRY003
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError) as error:
        raise ContextPackError("pack items contain invalid Base64") from error


def _digest_for(schema: str, wire_items: list[str]) -> str:
    unsigned = {"schema": schema, "items": wire_items}
    return "sha256:" + hashlib.sha256(_canonical_json(unsigned)).hexdigest()


@dataclass(frozen=True, slots=True)
class ContextPack:
    """A checksummed, chunked bundle of context bytes."""

    items: tuple[bytes, ...]
    digest: str

    # ------------------------------------------------------------------ build

    @classmethod
    def build(cls, items: tuple[bytes, ...]) -> ContextPack:
        if not isinstance(items, tuple) or any(not isinstance(item, bytes) for item in items):
            raise ContextPackError("pack items must be a tuple of bytes")  # noqa: TRY003
        wire_items = [_b64encode(item) for item in items]
        return cls(items=tuple(items), digest=_digest_for(PACK_SCHEMA, wire_items))

    @classmethod
    def from_content(cls, content: str | None, *, chunk_bytes: int = _DEFAULT_CHUNK_BYTES) -> ContextPack:
        """Chunk ``content`` into deterministic, valid-UTF-8 bounded pieces."""

        if not isinstance(chunk_bytes, int) or isinstance(chunk_bytes, bool) or chunk_bytes < 1:
            raise ContextPackError("chunk_bytes must be a positive integer")  # noqa: TRY003
        if content is None:
            return cls.build(())
        if not isinstance(content, str):
            raise ContextPackError("content must be text or None")  # noqa: TRY003
        data = content.encode("utf-8")
        chunks: list[bytes] = []
        index = 0
        total = len(data)
        while index < total:
            end = min(index + chunk_bytes, total)
            cut = end
            while cut > index:
                try:
                    data[index:cut].decode("utf-8")
                    break
                except UnicodeDecodeError:
                    cut -= 1
            if cut == index:
                raise ContextPackError(
                    "cannot form a valid UTF-8 chunk within chunk_bytes"  # noqa: TRY003
                )
            chunks.append(data[index:cut])
            index = cut
        return cls.build(tuple(chunks))

    # ------------------------------------------------------------- serialize

    def to_bytes(self) -> bytes:
        wire_items = [_b64encode(item) for item in self.items]
        count = 0
        while True:
            payload = {
                "schema": PACK_SCHEMA,
                "items": wire_items,
                "digest": self.digest,
                "byte_count": count,
            }
            raw = _canonical_json(payload)
            if len(raw) == count:
                return raw
            count = len(raw)

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> ContextPack:
        try:
            value = json.loads(raw)
        except (ValueError, TypeError) as error:
            raise ContextPackError("pack is not valid JSON") from error
        if not isinstance(value, dict) or set(value.keys()) != {
            "schema",
            "items",
            "digest",
            "byte_count",
        }:
            raise ContextPackError("pack must contain exactly schema, items, digest, byte_count")  # noqa: TRY003
        if value["schema"] != PACK_SCHEMA:
            raise ContextPackError("unrecognized pack schema")  # noqa: TRY003
        wire_items = value["items"]
        if not isinstance(wire_items, list) or any(not isinstance(item, str) for item in wire_items):
            raise ContextPackError("pack items must be a list of Base64 strings")  # noqa: TRY003
        digest = value["digest"]
        if not isinstance(digest, str) or digest != _digest_for(PACK_SCHEMA, wire_items):
            raise ContextPackError("pack digest mismatch")  # noqa: TRY003
        byte_count = value["byte_count"]
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count != len(raw):
            raise ContextPackError("pack byte_count mismatch")  # noqa: TRY003
        items = tuple(_b64decode(item) for item in wire_items)
        return cls(items=items, digest=digest)


@dataclass(frozen=True, slots=True)
class ContextPackDelta:
    """A prefix-reuse delta that rebuilds a target pack from a base pack."""

    base_digest: str
    target_digest: str
    prefix_items: int
    appended: tuple[bytes, ...]

    # ------------------------------------------------------------------ build

    @classmethod
    def between(cls, base: ContextPack, target: ContextPack) -> ContextPackDelta:
        if not isinstance(base, ContextPack) or not isinstance(target, ContextPack):
            raise ContextPackError("delta requires two ContextPack values")  # noqa: TRY003
        prefix = 0
        for base_item, target_item in zip(base.items, target.items):
            if base_item != target_item:
                break
            prefix += 1
        return cls(
            base_digest=base.digest,
            target_digest=target.digest,
            prefix_items=prefix,
            appended=tuple(target.items[prefix:]),
        )

    # ------------------------------------------------------------- serialize

    def to_bytes(self) -> bytes:
        payload = {
            "schema": DELTA_SCHEMA,
            "base_digest": self.base_digest,
            "target_digest": self.target_digest,
            "prefix_items": self.prefix_items,
            "appended": [_b64encode(item) for item in self.appended],
        }
        return _canonical_json(payload)

    @property
    def byte_count(self) -> int:
        return len(self.to_bytes())

    @classmethod
    def from_bytes(cls, raw: bytes) -> ContextPackDelta:
        try:
            value = json.loads(raw)
        except (ValueError, TypeError) as error:
            raise ContextPackError("delta is not valid JSON") from error
        if not isinstance(value, dict) or set(value.keys()) != {
            "schema",
            "base_digest",
            "target_digest",
            "prefix_items",
            "appended",
        }:
            raise ContextPackError(
                "delta must contain exactly schema, base_digest, target_digest, prefix_items, appended"  # noqa: TRY003
            )
        if value["schema"] != DELTA_SCHEMA:
            raise ContextPackError("unrecognized delta schema")  # noqa: TRY003
        prefix = value["prefix_items"]
        if isinstance(prefix, bool) or not isinstance(prefix, int) or prefix < 0:
            raise ContextPackError("prefix_items must be a non-negative integer")  # noqa: TRY003
        appended_wire = value["appended"]
        if not isinstance(appended_wire, list) or any(not isinstance(item, str) for item in appended_wire):
            raise ContextPackError("delta appended must be a list of Base64 strings")  # noqa: TRY003
        appended = tuple(_b64decode(item) for item in appended_wire)
        for field in ("base_digest", "target_digest"):
            if not isinstance(value[field], str):
                raise ContextPackError(f"{field} must be a string")  # noqa: TRY003
        return cls(
            base_digest=value["base_digest"],
            target_digest=value["target_digest"],
            prefix_items=prefix,
            appended=appended,
        )


def apply_context_pack_delta(base: ContextPack, delta: ContextPackDelta) -> ContextPack:
    """Rebuild the target pack from ``base`` and a validated ``delta``."""

    if not isinstance(base, ContextPack) or not isinstance(delta, ContextPackDelta):
        raise ContextPackError("apply requires a ContextPack base and a ContextPackDelta")  # noqa: TRY003
    if delta.base_digest != base.digest:
        raise ContextPackError("delta base_digest does not match the supplied base pack")  # noqa: TRY003
    prefix = delta.prefix_items
    if isinstance(prefix, bool) or not isinstance(prefix, int) or prefix < 0 or prefix > len(base.items):
        raise ContextPackError("prefix_items is out of bounds for the base pack")  # noqa: TRY003
    rebuilt_items = base.items[:prefix] + delta.appended
    target = ContextPack.build(rebuilt_items)
    if target.digest != delta.target_digest:
        raise ContextPackError("rebuilt target digest does not match delta target_digest")  # noqa: TRY003
    return target


__all__ = [
    "DELTA_SCHEMA",
    "PACK_SCHEMA",
    "ContextPack",
    "ContextPackDelta",
    "ContextPackError",
    "apply_context_pack_delta",
]
