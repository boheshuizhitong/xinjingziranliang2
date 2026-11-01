"""上下文模块 CLI 入口

用法：
  python -m context_module "为商品查询增加价格区间筛选" [--task-id 001]
  python -m context_module "任务描述" --json        # 输出结构化 JSON
  python -m context_module "任务描述" --save         # 把本次任务状态写入 PowerContext
  python -m context_module --import                  # 仅导入工程资料到 seekdb
  python -m context_module --import --clear          # 清空后重新导入

输入：任务描述（+可选 task_id / 过滤类型）。
输出：定位本次任务适用的规格、需修改的代码、验证测试，以及任务状态。
"""
from __future__ import annotations

import argparse
import json

from . import config as cfg
from . import import_materials
from .engine import ContextEngine, format_context


def main() -> None:
    ap = argparse.ArgumentParser(description="SDD 上下文管理系统 CLI")
    ap.add_argument("query", nargs="?", default="", help="开发任务描述")
    ap.add_argument("--task-id", default="", help="任务 id（可选）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出")
    ap.add_argument("--save", action="store_true", help="把任务状态写入 PowerContext")
    ap.add_argument("--top-k", type=int, default=cfg.CONTEXT_OUTPUT_TOP_K)
    ap.add_argument("--import", dest="do_import", action="store_true", help="仅导入资料")
    ap.add_argument("--clear", action="store_true", help="导入前清空资料库")
    args = ap.parse_args()

    if args.do_import:
        result = import_materials.import_materials(clear=args.clear)
        print(f"导入完成：cleared={result['cleared']} added={result['added']}")
        print("stats:", result["stats"])
        return

    if not args.query:
        ap.error("请提供任务描述（query）")

    engine = ContextEngine()
    context = engine.build_context(args.query, task_id=args.task_id, top_k=args.top_k)

    if args.save:
        engine.save_state(
            done=["已导入规格 v2 并完成价格区间筛选实现"],
            todo=["运行全部目标与回归测试并确认通过", "生成代码差异并记录 MiniMax 使用过程"],
            verification=["business_app/tests/test_catalog.py 目标+回归"],
        )

    if args.json:
        print(json.dumps(context, ensure_ascii=False, indent=2))
    else:
        print(format_context(context))


if __name__ == "__main__":
    main()
