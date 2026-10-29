# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
from typing import cast

import pytest

from powercontext.builtin.persistence.sqlite import SQLiteConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.runtime.composition import (
    _open_work_background,
    _work_background_requested,
    _work_discoverers,
    _work_handlers,
)
from powercontext.builtin.runtime.config import RuntimeConfig
from powercontext.builtin.runtime.membership import DuplicateSingleNodeError
from powercontext.builtin.runtime.relational import RelationalContexts
from powercontext.builtin.runtime.work_handlers import (
    EXPERIENCE_WORK_KIND,
    MAINTENANCE_WORK_KIND,
    MEMORY_WORK_KIND,
    PROFILE_WORK_KIND,
)


def _config(tmp_path, **overrides):
    return BuiltinConfig(
        database=SQLiteConfig(url=f"sqlite+aiosqlite:///{tmp_path / 'work.db'}"),
        **overrides,
    )


def test_ledger_background_only_starts_when_a_schedule_is_configured() -> None:
    assert _work_background_requested(BuiltinConfig()) is False
    assert _work_background_requested(BuiltinConfig(runtime=RuntimeConfig(memory_schedule_seconds=30))) is True
    assert _work_background_requested(BuiltinConfig(runtime=RuntimeConfig(experience_schedule_seconds=30))) is True
    assert _work_background_requested(BuiltinConfig(runtime=RuntimeConfig(profile_schedule_enabled=True))) is True


def test_composition_registers_every_discoverer_and_handler(tmp_path) -> None:
    sentinel = object()
    config = _config(
        tmp_path,
        runtime=RuntimeConfig(
            memory_schedule_seconds=30,
            experience_schedule_seconds=30,
            profile_schedule_enabled=True,
        ),
    )

    discoverers = _work_discoverers(config, cast("RelationalContexts", sentinel))
    assert [discoverer.name for discoverer in discoverers] == [
        MEMORY_WORK_KIND,
        EXPERIENCE_WORK_KIND,
        PROFILE_WORK_KIND,
        MAINTENANCE_WORK_KIND,
    ]

    class _Profiles:
        """Stand-in for the shared Profile service the handler only stores."""

    fake_contexts = cast("RelationalContexts", type("Contexts", (), {"profiles": _Profiles()})())
    handlers = _work_handlers(config, fake_contexts)
    assert [handler.kind for handler in handlers] == [
        MEMORY_WORK_KIND,
        EXPERIENCE_WORK_KIND,
        PROFILE_WORK_KIND,
        MAINTENANCE_WORK_KIND,
    ]


def test_unconfigured_runtime_exposes_operations_without_execution(tmp_path) -> None:
    async def scenario() -> None:
        config = _config(tmp_path)
        async with (
            open_builtin_contexts(config) as contexts,
            _open_work_background(BuiltinConfig(), contexts) as background,
        ):
            assert background.operations is not None
            assert background.scheduler is None
            assert background.worker is None
            assert background.membership is None

    asyncio.run(scenario())


def test_configured_single_node_runtime_owns_the_ledger_and_shuts_down(tmp_path) -> None:
    async def scenario() -> None:
        config = _config(tmp_path, runtime=RuntimeConfig(memory_schedule_seconds=30))
        async with (
            open_builtin_contexts(config) as contexts,
            _open_work_background(config, contexts) as background,
        ):
            assert background.membership is not None
            assert background.scheduler is not None
            assert background.worker is not None
            assert set(background.worker.supported) == {
                MEMORY_WORK_KIND,
                EXPERIENCE_WORK_KIND,
                PROFILE_WORK_KIND,
                MAINTENANCE_WORK_KIND,
            }
            # A second runtime may not claim the same single-node ownership.
            with pytest.raises(DuplicateSingleNodeError):
                async with _open_work_background(config, contexts):
                    pass

    asyncio.run(scenario())
