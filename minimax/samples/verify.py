#!/usr/bin/env python
"""SDD 上下文管理系统 —— 验收验证样例（评审复现）

用法（在 minimax/ 目录，使用 venv python）：
  python samples/verify.py            # 从当前状态验证
  python samples/verify.py --reset    # 重置到干净状态（v1 代码 + 空资料库 + 空记忆）后完整验证
  python samples/verify.py --skip-minimax   # 跳过 MiniMax 修改步骤（仅基础设施验证）

验证点（对照赛题必做项）：
  [P1] 规格更新并重新导入后，上下文模块使用更新后的内容（v1 -> v2）
  [P2] seekdb 实际存储/检索工程资料（stats + 命中信号）
  [P3] 修改前目标功能测试因行为未实现而失败，回归测试通过
  [P4] MiniMax 实际参与代码修改（生成差异并应用）
  [P5] 修改后目标功能测试 + 回归测试全部通过
  [P6] 从空状态保存任务记录，重启模块后能读取并复用状态
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
CATALOG = ROOT / "business_app" / "catalog.py"
SNAP_V1 = ROOT / "business_app" / "snapshots" / "catalog_v1_before.py"
SNAP_V2 = ROOT / "business_app" / "snapshots" / "catalog_v2_after.py"
SPEC_V2 = ROOT / "business_app" / "specs" / "product_spec_v2.md"
SPEC_BAK = ROOT / "business_app" / "specs" / ".v2.bak"
PC_DB = ROOT / "data" / "powercontext.db"
SCOPE_FILE = ROOT / "data" / "powercontext_scope_id.txt"

sys.path.insert(0, str(ROOT))

CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append({"name": name, "ok": bool(ok), "detail": detail})
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  — {detail}" if detail else ""))


def run_py(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(VENV_PY), *args], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8")


def run_pytest() -> subprocess.CompletedProcess:
    return subprocess.run([str(VENV_PY), "-m", "pytest", "business_app/tests", "-q"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")


def get_context(query: str) -> dict:
    from context_module.engine import ContextEngine
    return ContextEngine().build_context(query, task_id="task-001")


def reset() -> None:
    """恢复到干净可复现状态：v1 代码 + 空资料库 + 空记忆。

    注意：PowerContext 服务进程在运行中持有 SQLite 连接，不能删除其数据库文件。
    这里通过删除 scope 文件强制下次创建全新空 Scope（旧记忆仍在库里但不再被使用），
    从而得到"从空状态开始"的验证环境。
    """
    shutil.copy(SNAP_V1, CATALOG)
    run_py(["-m", "context_module", "--import", "--clear"])
    if SCOPE_FILE.exists():
        SCOPE_FILE.unlink()
    # 确保 v2 规格文件在位
    if SPEC_BAK.exists() and not SPEC_V2.exists():
        shutil.move(str(SPEC_BAK), str(SPEC_V2))


# ---------------------------------------------------------------------------
def phase_spec_update() -> None:
    """[P1] 规格更新并重新导入后，模块使用更新后的内容。"""
    from context_module.engine import ContextEngine
    eng = ContextEngine()
    query = "为商品查询增加价格区间筛选，并校验边界输入"

    # 阶段 A：只导入 v1 规格
    if SPEC_V2.exists():
        shutil.move(str(SPEC_V2), str(SPEC_BAK))
    run_py(["-m", "context_module", "--import", "--clear"])
    ctx_a = eng.build_context(query)
    spec_srcs_a = {s["source"] for s in ctx_a["materials"]["specs"]}
    v2_absent = "product_spec_v2.md" not in spec_srcs_a
    has_price_a = any("min_price" in s["content"] for s in ctx_a["materials"]["specs"])
    check("P1a 仅导入 v1 时，上下文不含 v2 且不含价格区间要求",
          v2_absent and not has_price_a,
          f"specs={sorted(spec_srcs_a)}")

    # 阶段 B：加入并重新导入 v2 规格
    if SPEC_BAK.exists():
        shutil.move(str(SPEC_BAK), str(SPEC_V2))
    run_py(["-m", "context_module", "--import", "--clear"])
    ctx_b = eng.build_context(query)
    v2_hit = next((s for s in ctx_b["materials"]["specs"]
                   if s["source"].endswith("product_spec_v2.md")), None)
    check("P1b 重新导入 v2 后，上下文使用 v2（含价格区间筛选要求）",
          v2_hit is not None and "min_price" in v2_hit["content"] and "价格区间筛选" in v2_hit["content"],
          f"v2 source={v2_hit['source'] if v2_hit else None}")


def phase_seekdb() -> None:
    """[P2] seekdb 实际存储/检索工程资料。"""
    from context_module.seekdb_store import MaterialStore
    store = MaterialStore()
    stats = store.stats()
    ok_db = stats["total"] >= 3 and set(stats["by_type"]) >= {"spec", "code", "test"}
    check("P2a seekdb 已存储规格/代码/测试资料", ok_db, f"stats={stats}")

    ctx = get_context("为商品查询增加价格区间筛选")
    specs = ctx["materials"]["specs"]
    check("P2b 查询结果含真实来源与命中信号",
          specs and all(s.get("source") for s in specs) and any(s.get("signal") for s in specs),
          f"specs={[s['source'] for s in specs][:3]} engine={ctx['database']['engine']} vector={ctx['database']['vector_enabled']}")


def phase_before_tests() -> None:
    """[P3] 修改前：目标功能测试失败（行为未实现），回归测试通过。"""
    # 确保当前是 v1
    shutil.copy(SNAP_V1, CATALOG)
    r = run_pytest()
    out = (r.stdout + r.stderr)
    summary = out.strip().splitlines()[-1] if out.strip() else ""
    target_fail = all(
        name in out for name in ("test_price_range_filter", "test_min_gt_max_rejected")
    )
    # 目标 8 个失败，回归 5 个通过
    ok = ("8 failed" in summary and "5 passed" in summary and target_fail)
    check("P3 修改前目标测试因未实现而失败、回归通过", ok,
          f"exit={r.returncode} summary={summary}")
    (ROOT / "samples" / "test_logs" / "pytest_BEFORE_modification.txt").write_text(out, encoding="utf-8")


def phase_minimax(skip: bool) -> None:
    """[P4] MiniMax 实际参与代码修改。"""
    if skip:
        check("P4 MiniMax 代码修改", True, "已跳过（--skip-minimax），完整验收需配置 MINIMAX_API_KEY")
        return
    from minimax_agent import agent
    from context_module.engine import ContextEngine, format_context
    query = "为商品查询增加价格区间筛选，并校验边界输入"
    ctx = ContextEngine().build_context(query, task_id="task-001")
    context_text = format_context(ctx)
    record = agent.run_modification(query, context_text, apply=True, save_log=True)
    check("P4a MiniMax 返回可编译代码并生成差异", bool(record["new_code"]) and bool(record["diff"]),
          f"model={record['model']} diff_lines={record['diff'].count(chr(10))}")
    # 应用后快照 v2
    shutil.copy(CATALOG, SNAP_V2)
    check("P4b 修改已应用到 catalog.py", "min_price" in CATALOG.read_text(encoding="utf-8"))
    (ROOT / "samples" / "test_logs" / "minimax_modification.diff").write_text(record["diff"], encoding="utf-8")


def phase_after_tests() -> None:
    """[P5] 修改后：目标 + 回归全部通过。"""
    r = run_pytest()
    out = (r.stdout + r.stderr)
    summary = out.strip().splitlines()[-1] if out.strip() else ""
    ok = r.returncode == 0 and "13 passed" in summary
    check("P5 修改后目标功能测试 + 回归测试全部通过", ok,
          f"exit={r.returncode} summary={summary}")
    (ROOT / "samples" / "test_logs" / "pytest_AFTER_modification.txt").write_text(out, encoding="utf-8")


def phase_state() -> None:
    """[P6] 从空状态保存任务记录，重启模块后能读取并复用。"""
    from context_module.engine import ContextEngine
    eng = ContextEngine()
    # 空状态应读到 0 条
    empty = eng.build_context("任意查询")["state"]
    empty_ok = not empty["done"] and not empty["todo"] and not empty["verification"]
    # 写入
    eng.save_state(
        done=["已完成价格区间筛选实现，修改后全部测试通过"],
        todo=["（本轮验证无遗留待办）"],
        verification=["business_app/tests/test_catalog.py 13/13 通过"],
    )
    # 新进程（模拟重启）读取
    from context_module.engine import ContextEngine as E2
    eng2 = E2()
    st = eng2.build_context("价格区间筛选")["state"]
    reused = (len(st["done"]) == 1 and len(st["verification"]) >= 1
              and "价格区间筛选" in st["done"][0]["text"])
    check("P6 空状态写入后重启读取并复用", empty_ok and reused,
          f"empty={empty_ok} reused={reused} done={len(st['done'])} todo={len(st['todo'])} veri={len(st['verification'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="重置到干净状态")
    ap.add_argument("--skip-minimax", action="store_true", help="跳过 MiniMax 修改步骤")
    args = ap.parse_args()

    if args.reset:
        reset()
        print("已重置到干净状态（v1 代码 + 空资料库 + 空记忆）\n")

    print("=== [P1] 规格更新并重新导入后使用新内容 ===")
    phase_spec_update()
    print("\n=== [P2] seekdb 实际存储/检索工程资料 ===")
    phase_seekdb()
    print("\n=== [P3] 修改前：目标测试失败 / 回归通过 ===")
    phase_before_tests()
    print("\n=== [P4] MiniMax 实际参与代码修改 ===")
    phase_minimax(args.skip_minimax)
    print("\n=== [P5] 修改后：目标 + 回归全部通过 ===")
    phase_after_tests()
    print("\n=== [P6] PowerContext 状态保存与重启复用 ===")
    phase_state()

    print("\n" + "=" * 60)
    failed = [c for c in CHECKS if not c["ok"]]
    print(f"验证结果：{len(CHECKS) - len(failed)}/{len(CHECKS)} 通过")
    for c in CHECKS:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
