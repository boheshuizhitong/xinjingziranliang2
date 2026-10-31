/* 学伴 StudyMate 前端逻辑（原生 JS，无构建依赖） */
"use strict";

const $ = (id) => document.getElementById(id);

function courseTag(course) {
  const map = { 物理: "phys", 高数: "math", 英语: "eng", 电路: "circ", 文献: "lit" };
  return `<span class="tag ${map[course] || ""}">${course}</span>`;
}

function signalTag(signal) {
  const t = { semantic: "语义命中", keyword: "关键词命中", both: "双命中" };
  return `<span class="signal">${t[signal] || signal}</span>`;
}

function log(msg) {
  const el = $("debug-log");
  el.textContent = `${new Date().toLocaleTimeString()} > ${msg}\n` + el.textContent.slice(0, 1200);
}

/* ---------- 通用请求 ---------- */
async function api(path, body) {
  const opt = body
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
    : { method: "GET" };
  const resp = await fetch(path, opt);
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.detail || `HTTP ${resp.status}`);
  return data;
}

/* ---------- Tab 切换 ---------- */
document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll("section.tab").forEach((s) => s.classList.remove("active"));
    btn.classList.add("active");
    $(`tab-${btn.dataset.tab}`).classList.add("active");
    if (btn.dataset.tab === "plan") loadPlan();
    if (btn.dataset.tab === "memory") loadMemories();
    if (btn.dataset.tab === "kb") loadNotes();
  });
});

/* ---------- 健康检查 ---------- */
async function checkHealth() {
  try {
    const h = await api("/api/health");
    $("bd-seekdb").textContent = `seekdb: ${h.seekdb.ok ? "嵌入式✓" : "异常"}`;
    $("bd-pc").textContent = `PowerContext: ${h.powercontext.ok ? "已连接✓" : "未连接"}`;
    if (!h.powercontext.ok) {
      log("PowerContext 未连接，请先启动 pc_server（python pc_server/server.py）");
    }
    // 首次访问自动初始化知识库与示例数据
    if (h.seekdb.ok) {
      const init = await api("/api/init");
      log(`知识库初始化：${JSON.stringify(init.kb)}`);
      if (init.seed.status === "ok") log(`示例数据导入 ${init.seed.imported} 条`);
    }
  } catch (e) {
    log("健康检查失败: " + e.message);
  }
}

/* ---------- 问答 ---------- */
async function ask() {
  const q = $("ask-input").value.trim();
  if (!q) return;
  appendMsg("user", q);
  $("ask-input").value = "";
  appendMsg("bot", "正在检索知识库与回忆你的学习记录…");
  try {
    const r = await api("/api/ask", { question: q, course: $("ask-course").value });
    $("chat").lastElementChild.remove();
    const evidence = (r.knowledge.results || [])
      .map((x) => `【${x.course}】${x.title} · ${signalTag(x.signal)}`)
      .join(" ");
    appendMsg("bot", r.answer + "\n" + (evidence ? `\n命中证据：${evidence}` : ""));
    log(`ask: "${q}" → 命中 ${r.knowledge.results.length} 条，记忆上下文 ${r.memory_context.hits.length} 条`);
  } catch (e) {
    $("chat").lastElementChild.remove();
    appendMsg("bot", "出错了：" + e.message);
  }
}
$("ask-btn").addEventListener("click", ask);
$("ask-input").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });

function appendMsg(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  $("chat").appendChild(div);
  $("chat").scrollTop = $("chat").scrollHeight;
}

/* ---------- 知识库 ---------- */
async function loadNotes(course) {
  try {
    const r = await api("/api/notes?course=" + encodeURIComponent(course || ""));
    $("kb-stats").textContent =
      `共 ${r.stats.total} 条：` + Object.entries(r.stats.by_course).map(([c, n]) => `${c} ${n}`).join("、");
    $("kb-list").innerHTML = r.notes.length
      ? r.notes.map((n) => `
        <div class="note-item">
          <div><span class="title">${escapeHtml(n.title)}</span> ${courseTag(n.course)}
            <button class="btn small danger" data-del="${n.id}" style="float:right;">删除</button></div>
          <div class="src">${n.source ? "出处：" + escapeHtml(n.source) : "无出处"} · ${escapeHtml(n.created_at || "")}</div>
          <div class="content">${escapeHtml(n.content)}</div>
        </div>`).join("")
      : '<div class="empty">暂无笔记，可先导入示例数据（刷新页面自动导入）或手动添加</div>';
    document.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", async () => {
        await api(`/api/notes/${b.dataset.del}`);
        loadNotes($("kb-course").value);
      }));
  } catch (e) { $("kb-list").innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`; }
}

async function kbSearch() {
  const q = $("kb-q").value.trim();
  if (!q) return;
  try {
    const r = await api("/api/search", { query: q, course: $("kb-course").value });
    const html = r.results.length
      ? r.results.map((x) => `
        <div class="note-item">
          <div><span class="title">${escapeHtml(x.title)}</span> ${courseTag(x.course)} ${signalTag(x.signal)}
            <span class="muted">得分 ${x.score}</span></div>
          <div class="content">${escapeHtml(x.content)}</div>
          <div class="src">全文表达式："${escapeHtml(r.fulltext_expr)}" · 向量命中 ${r.raw.vector_hits} · 全文命中 ${r.raw.fulltext_hits}</div>
        </div>`).join("")
      : '<div class="empty">没有匹配结果，试试换个说法或补充笔记</div>';
    $("kb-results").innerHTML = html;
    log(`hybrid_search: "${q}" [${r.course || "全部"}] → ${r.results.length} 条（向量 ${r.raw.vector_hits} + 全文 ${r.raw.fulltext_hits}）`);
  } catch (e) { $("kb-results").innerHTML = `<div class="empty">检索失败：${escapeHtml(e.message)}</div>`; }
}
$("kb-search-btn").addEventListener("click", kbSearch);
$("kb-q").addEventListener("keydown", (e) => { if (e.key === "Enter") kbSearch(); });

async function addNote() {
  const title = $("note-title").value.trim();
  const content = $("note-content").value.trim();
  if (!title || !content) { alert("标题和内容不能为空"); return; }
  try {
    const r = await api("/api/notes", { title, content, course: $("note-course").value, source: $("note-source").value });
    log(`add note #${r.note.id} "${title}" → 已嵌入并入库`);
    $("note-title").value = ""; $("note-content").value = ""; $("note-source").value = "";
    loadNotes();
  } catch (e) { alert("添加失败：" + e.message); }
}
$("note-add").addEventListener("click", addNote);

/* ---------- 复习计划 ---------- */
async function loadPlan() {
  try {
    const r = await api("/api/plan");
    $("plan-summary").textContent = `（跟踪 ${r.summary.tracked_topics} 个知识点 · 今日应复习 ${r.summary.due_today} · 巩固 ${r.summary.consolidating}）`;
    const render = (items, cls) => items.map((it) => `
      <div class="plan-item ${cls}">
        <div class="topic">${it.topic} ${courseTag(it.course)}
          ${it.is_weak ? '<span class="tag" style="background:var(--warn-soft);color:#b54708;">薄弱点</span>' : ""}
          ${it.days_since >= 99 ? '<span class="due-badge">未复习过</span>' : `<span class="due-badge">上次复习 ${it.days_since} 天前</span>`}
        </div>
        ${it.progress_note ? `<div class="muted">上次备注：${escapeHtml(it.progress_note)}</div>` : ""}
        <div class="muted">复习资料（来自 seekdb）：${it.materials.length ? "" : "知识库暂无匹配"}</div>
        ${it.materials.map((m) => `<div class="content">· 【${m.course}】${escapeHtml(m.title)} ${signalTag(m.signal)}</div>`).join("")}
        <div style="margin-top:6px;"><button class="btn small" data-done="${escapeHtml(it.topic)}|${it.course}">✓ 今日已复习</button></div>
      </div>`).join("");
    $("plan-list").innerHTML = r.summary.tracked_topics === 0
      ? '<div class="empty">还没有记忆任何知识点。去「记忆/复习计划」页记录一个薄弱点，或问学伴一个问题，它会开始了解你。</div>'
      : render(r.due_today, "due") + '<h3 style="margin:12px 0 6px;font-size:14px;">🧊 巩固中</h3>' + render(r.consolidating, "consolidate");
    document.querySelectorAll("[data-done]").forEach((b) =>
      b.addEventListener("click", async () => {
        const [topic, course] = b.dataset.done.split("|");
        const note = prompt(`为「${topic}」留一句复习备注（可选）：`, "") || "";
        const r = await api("/api/reviewed", { topic, course, note });
        log(`mark reviewed: "${topic}" → PowerContext 写入复习进度`);
        alert("已记录 ✓ 学伴会据此安排下次复习时间");
        loadPlan();
      }));
  } catch (e) { $("plan-list").innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`; }
}
$("plan-refresh").addEventListener("click", loadPlan);

async function addWeak() {
  const topic = $("weak-topic").value.trim();
  if (!topic) { alert("请输入知识点"); return; }
  try {
    const r = await api("/api/weak", { topic, course: $("weak-course").value, detail: $("weak-detail").value.trim() });
    log(`weak point recorded: "${topic}" → ${r.text}`);
    alert("已记下薄弱点 ✓ 复习计划会优先安排它");
    $("weak-topic").value = ""; $("weak-detail").value = "";
    loadPlan();
  } catch (e) { alert("记录失败：" + e.message); }
}
$("weak-btn").addEventListener("click", addWeak);

/* ---------- 记忆 ---------- */
const KIND_LABEL = { weak_point: ["薄弱点", "weak"], progress: ["进度", "progress"], preference: ["偏好", "preference"], fact: ["事实", "weak"] };

function renderMemories() {
  api("/api/memories").then((r) => {
    const all = [...r.weak_points.map((m) => ({ ...m, kind: "weak_point" })),
                 ...r.progress.map((m) => ({ ...m, kind: "progress" })),
                 ...r.preferences.map((m) => ({ ...m, kind: "preference" }))];
    $("mem-list").innerHTML = all.length
      ? all.slice(0, 30).map((m) => {
          const [label, cls] = KIND_LABEL[m.kind] || [m.kind, "weak"];
          const txt = m.text.replace(/^(薄弱知识点|复习进度|学习偏好)：/, "");
          return `<div class="mem-item"><span class="kind-badge ${cls}">${label}</span>${escapeHtml(txt)}<span class="muted"> · 分 ${m.score}</span></div>`;
        }).join("")
      : '<div class="empty">还没有记忆。去问答/复习计划页留下一些交互，PowerContext 会记住。</div>';
  }).catch((e) => { $("mem-list").innerHTML = `<div class="empty">加载失败：${escapeHtml(e.message)}</div>`; });

  api("/api/plan").then(() => {}).catch(() => {});
  api("/api/memories").then(() => {});
}

async function addPref() {
  const text = $("pref-text").value.trim();
  if (!text) { alert("请输入偏好内容"); return; }
  try {
    const r = await api("/api/preference", { text });
    log(`preference saved: "${text}"`);
    $("pref-text").value = "";
    loadMemories();
  } catch (e) { alert("保存失败：" + e.message); }
}
$("pref-btn").addEventListener("click", addPref);

function loadMemories() { renderMemories(); }

/* ---------- 工具 ---------- */
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- 启动 ---------- */
checkHealth().then(() => loadNotes());
