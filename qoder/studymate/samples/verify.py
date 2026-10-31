"""学伴 StudyMate 一键验证脚本（评审复现用）

前置：主应用已启动（http://127.0.0.1:8080），PowerContext 已连接（官方或兼容实现均可）。
运行：python samples/verify.py

覆盖：①知识库初始化 ②seekdb 混合检索 ③PowerContext 记忆写入 ④跨会话记忆召回 ⑤复习计划调度
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8080"
PASS, FAIL = "✅", "❌"
checks: list[tuple[str, bool, str]] = []


def post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


# 支持 `--reset`：先清空知识库再验证，保证任意状态下都得到完整结果
if "--reset" in sys.argv:
    print("→ 先执行 /api/reset 清空知识库…")
    post("/api/reset", {})


def check(name: str, ok: bool, detail: str = ""):
    checks.append((name, ok, detail))
    print(f"{PASS if ok else FAIL} {name} {detail}")


print("=" * 66)
print(" 学伴 StudyMate 验证样例")
print("=" * 66)

# ---------- ① 健康与初始化 ----------
h = get("/api/health")
check("服务健康：seekdb 嵌入式就绪", h["seekdb"]["ok"] is True)
check("服务健康：PowerContext 已连接", h["powercontext"]["ok"] is True,
      f"({h['powercontext']['url']})")

init = post("/api/init", {})
check("知识库初始化并导入示例数据", init["seed"]["status"] == "ok",
      f"（导入 {init['seed'].get('imported', 0)} 条，"
      f"共 {init['kb']['total']} 条）")
scope = init.get("powercontext_scope", "")
check("PowerContext Scope 创建成功", bool(scope), f"(scope_id={scope})")

# ---------- ② seekdb 混合检索 ----------
cases = [
    ("杨氏双缝实验怎么算条纹间距", "双缝"),
    ("英语作文怎么避免抄原文", "paraphrase"),
    ("气温对声速有什么影响", "声速"),
    ("泰勒展开是干什么的", "泰勒"),
    ("carbon capture 碳捕集", "CCUS"),
]
for q, expect in cases:
    r = post("/api/search", {"query": q, "course": ""})
    top = r["results"][0] if r["results"] else {}
    ok = bool(top) and expect in (top.get("title", "") + top.get("content", ""))
    check(f"混合检索：“{q}” → 首位命中《{top.get('title', '无')}》",
          ok, f"[{top.get('signal', '-')}]")

r = post("/api/search", {"query": "复习 笔记", "course": "英语"})
ok = all(x["course"] == "英语" for x in r["results"][:3])
check("标量过滤：course=英语 仅返回英语笔记", ok, f"（{len(r['results'])} 条）")

# ---------- ③ PowerContext 记忆写入 ----------
w = post("/api/weak", {"topic": "傅里叶变换的物理意义", "course": "高数", "detail": "分不清时域频域"})
check("记忆写入：薄弱知识点", bool(w.get("response", {}).get("changed")), f"({w['text'][:26]}…)")

p = post("/api/reviewed", {"topic": "光的干涉", "course": "物理", "note": "双缝公式已记住"})
check("记忆写入：复习进度", bool(p.get("response", {}).get("changed")), f"({p['text'][:26]}…)")

pref = post("/api/preference", {"text": "我喜欢先做错题再背单词"})
check("记忆写入：学习偏好", bool(pref.get("response", {}).get("changed")))

# ---------- ④ 跨会话记忆召回（PowerContext 核心） ----------
a = post("/api/ask", {"question": "帮我复习光的干涉，我上次标记过进度"})
hits = a.get("memory_context", {}).get("hits", [])
ok = any("光的干涉" in (x.get("text") or "") or "复习进度" in (x.get("text") or "") for x in hits)
check("跨会话记忆召回：提问时召回历史进度", ok,
      f"（召回 {len(hits)} 条：{[x['text'][:20] for x in hits]}）")
top1 = a.get("knowledge", {}).get("results", [{}])[0]
check("问答联动：知识库证据命中《光的干涉》", "光的干涉" in (top1.get("title") or ""))

# ---------- ⑤ 复习计划调度 ----------
plan = get("/api/plan")
due = [i for i in plan.get("due_today", [])]
ok = any("傅里叶" in i["topic"] for i in due)
check("复习计划：薄弱点进入今日复习", ok,
      f"（今日 {plan['summary']['due_today']} 项 · 共跟踪 {plan['summary']['tracked_topics']} 项）")
weak_item = next((i for i in due if "傅里叶" in i["topic"]), None)
ok = weak_item is not None and len(weak_item.get("materials", [])) > 0
check("复习计划：自动匹配知识库复习资料", ok,
      f"（匹配 {len(weak_item.get('materials', []))} 条资料）" if weak_item else "（未找到薄弱点）")

# ---------- 汇总 ----------
print("-" * 66)
fails = [c for c in checks if not c[1]]
print(f"验证完成：{len(checks) - len(fails)}/{len(checks)} 通过")
if fails:
    print("未通过项：")
    for name, ok, detail in fails:
        print(f"  {FAIL} {name} {detail}")
    sys.exit(1)
print("全部通过 🎉 可提交评审。")
