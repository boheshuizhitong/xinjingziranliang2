"""工程资料导入：把业务工程的规格/代码/测试写入 seekdb 工程资料库

用法：
  python -m context_module.import_materials [--clear] [--specs-dir ...] [--code-roots ...] [--tests-roots ...]

说明：
  - 规格：business_app/specs/*.md     （mtype=spec）
  - 代码：business_app/*.py           （mtype=code，仅源码主干）
  - 测试：business_app/tests/*.py     （mtype=test）
以 (mtype, source) 为键 upsert：再次导入同名 source 会覆盖旧内容，
从而支持「更新规格并重新导入后，模块使用新内容」。
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import config as cfg
from .seekdb_store import MaterialStore

CODE_ROOTS = ("catalog.py", "server.py")
TEST_GLOB = "tests/*.py"
SPEC_GLOB = "specs/*.md"


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def build_materials() -> list[dict]:
    """收集业务工程的规格/代码/测试为待入库条目。"""
    app = cfg.BUSINESS_APP_DIR
    items: list[dict] = []

    # 规格
    for p in sorted(app.glob(SPEC_GLOB)):
        rel = p.relative_to(cfg.BASE_DIR).as_posix()
        items.append({
            "mtype": "spec", "title": f"[规格] {p.name}",
            "content": _read_text(p), "source": rel,
            "tags": "spec 规格", "version": p.stem.split("_v")[-1] if "_v" in p.stem else "",
        })

    # 代码
    for name in CODE_ROOTS:
        p = app / name
        if p.exists():
            rel = p.relative_to(cfg.BASE_DIR).as_posix()
            items.append({
                "mtype": "code", "title": f"[代码] {name}",
                "content": _read_text(p), "source": rel,
                "tags": "code 代码 实现", "version": "",
            })

    # 测试
    for p in sorted(app.glob(TEST_GLOB)):
        rel = p.relative_to(cfg.BASE_DIR).as_posix()
        items.append({
            "mtype": "test", "title": f"[测试] {p.name}",
            "content": _read_text(p), "source": rel,
            "tags": "test 测试 用例", "version": "",
        })
    return items


def import_materials(clear: bool = False, store: MaterialStore | None = None) -> dict:
    store = store or MaterialStore()
    store.init()
    if clear:
        cleared = store.clear_all()
    else:
        cleared = 0
    items = build_materials()
    added = []
    for it in items:
        r = store.upsert_material(**it)
        added.append(r)
    return {"cleared": cleared, "added": len(added), "items": items, "stats": store.stats()}


def main() -> None:
    ap = argparse.ArgumentParser(description="导入业务工程资料到 seekdb")
    ap.add_argument("--clear", action="store_true", help="先清空工程资料库再导入")
    args = ap.parse_args()
    result = import_materials(clear=args.clear)
    print(f"cleared={result['cleared']} added={result['added']}")
    for it in result["items"]:
        print(f"  [{it['mtype']:4}] {it['source']}")
    print("stats:", result["stats"])


if __name__ == "__main__":
    main()
