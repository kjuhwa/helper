const $ = (id) => document.getElementById(id);
const el = (tag, props = {}, ...kids) => {
  const n = Object.assign(document.createElement(tag), props);
  kids.forEach((k) => n.append(k));
  return n;
};

// ---- health ----
fetch("/api/health").then((r) => r.json()).then((h) => {
  const parts = [`로컬 Claude CLI · 모델: ${h.model}`];
  const box = $("health");
  box.textContent = parts.join(" · ");
  if (!h.claude_cli) box.append(el("span", { className: "bad", textContent: " · Claude Code CLI(claude) 없음 — 설치 후 로그인 필요" }));
  if (!h.ffmpeg) box.append(el("span", { className: "bad", textContent: " · ffmpeg 없음" }));
}).catch(() => {});

// ---- url input ----
const urlOk = () => /^https?:\/\/\S+$/i.test($("url").value.trim());
const isMixed = (u) => { try { const q = new URL(u).searchParams; return q.has("v") && q.has("list"); } catch { return false; } };
$("url").addEventListener("input", () => {
  $("go").disabled = !urlOk();
  $("whole-wrap").classList.toggle("hidden", !isMixed($("url").value.trim()));
});
$("url").addEventListener("keydown", (e) => { if (e.key === "Enter" && urlOk()) $("go").click(); });
$("hint").addEventListener("keydown", (e) => { if (e.key === "Enter" && urlOk()) $("go").click(); });

// ---- run ----
$("go").addEventListener("click", async () => {
  if (!urlOk()) return;
  if (!confirmLeave()) return;
  $("go").disabled = true;
  current = null;
  setDirty(false);
  $("result").classList.add("hidden");
  $("batch").classList.add("hidden");
  batchId = null;
  $("progress").classList.remove("hidden");
  $("perr").classList.add("hidden");
  renderSteps({ steps: [], status: "upload", label: "URL 확인 중… (재생목록이면 영상 목록을 읽습니다)" });
  try {
    const r = await fetch("/api/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: $("url").value.trim(), hint: $("hint").value, force: $("force").checked,
        whole_playlist: isMixed($("url").value.trim()) && $("whole").checked,
      }),
    });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
    const data = await r.json();
    if (data.kind === "batch") {
      $("progress").classList.add("hidden");
      $("go").disabled = false;
      startBatch(data);
    } else {
      poll(data.id);
    }
  } catch (e) {
    showError(`요청 실패: ${e.message}`);
  }
});

function renderSteps(job) {
  const ol = $("steps");
  ol.replaceChildren();
  if (job.status === "upload") { ol.append(el("li", { className: "active", textContent: job.label })); return; }
  const keys = job.steps.map((s) => s.key);
  const cur = job.status === "done" ? keys.length : keys.indexOf(job.status);
  job.steps.forEach((s, i) => {
    const cls = i < cur || job.status === "done" ? "done" : i === cur ? "active" : "";
    ol.append(el("li", { className: cls, textContent: s.label }));
  });
  if (job.cached) ol.append(el("li", { className: "done", textContent: "보관함에 있던 결과를 불러왔습니다 (새로 분석하려면 '캐시 무시' 체크)" }));
}

function showError(msg) {
  $("perr").textContent = msg;
  $("perr").classList.remove("hidden");
  $("go").disabled = false;
}

async function poll(id) {
  try {
    const job = await (await fetch(`/api/jobs/${id}`)).json();
    renderSteps(job);
    if (job.status === "error") return showError(job.error);
    if (job.status === "done") {
      $("go").disabled = false;
      refreshLibCount();
      return openAnalysis(job.analysis_id, "new");
    }
  } catch (e) { /* 일시적 오류는 재시도 */ }
  setTimeout(() => poll(id), 1200);
}

// ---- result ----
const CONF_LABEL = { high: "높음", medium: "중간", guess: "추정", low: "낮음", none: "실패" };

function renderTitles(titles, selected) {
  const sel = Math.max(0, titles.indexOf(selected));
  $("titles").replaceChildren(...titles.map((t, i) => {
    const radio = el("input", { type: "radio", name: "title-pick", checked: i === sel, title: "이 제목 사용" });
    const input = el("input", { type: "text", value: t, className: "title-input" });
    const count = el("span", { className: "count" });
    const upd = () => (count.textContent = `${input.value.length}/100`);
    input.addEventListener("input", () => { upd(); markDirty(); });
    radio.addEventListener("change", markDirty);
    upd();
    return el("div", { className: "title-row" }, radio, input, count, copyBtn(() => input.value));
  }));
}

function renderResult(res) {
  const m = res.meta;
  $("result").classList.remove("hidden");

  const warns = (m.warnings || []).map((w) => el("div", { className: "warn", textContent: "⚠ " + w }));
  if (warns.length > 2) {
    const more = el("details", { className: "warn-more" }, el("summary", { textContent: `경고 ${warns.length - 2}개 더 보기` }), ...warns.slice(2));
    $("warnings").replaceChildren(...warns.slice(0, 2), more);
  } else {
    $("warnings").replaceChildren(...warns);
  }

  const rc = res.recognition || {};
  const badge = $("recog");
  badge.className = `badge ${rc.confidence || "none"}`;
  badge.textContent = rc.match
    ? `오디오 인식 ${rc.votes}/${rc.total} 일치 (${rc.provider})`
    : "오디오 인식 실패";

  const s = m.song || {};
  const rows = [
    ["곡", [s.title_ko, s.title_en].filter(Boolean).join(" / ")],
    ["아티스트", [s.artist_ko, s.artist_en].filter(Boolean).join(" / ")],
    ["멤버", (s.members || []).join(", ")],
    ["앨범", s.album], ["발매일", s.release_date], ["크레딧", s.credits],
  ];
  $("song").replaceChildren(...rows.flatMap(([k, v]) => [el("dt", { textContent: k }), el("dd", { textContent: v || "—" })]));

  renderTitles(m.title_candidates || [], m.selected_title);

  $("desc").value = m.description || "";
  $("tags").value = (m.tags || []).join(", ");
  $("hashtags").value = (m.hashtags || []).join(" ");
  $("category").textContent = m.category || "";
  $("vtype").textContent = m.video_type || "";
  updateCounts();

  const tb = $("evidence").querySelector("tbody");
  tb.replaceChildren(...(m.evidence || []).map((e) => el("tr", {},
    el("td", { textContent: e.field }), el("td", { textContent: e.value }),
    el("td", { className: e.confidence, textContent: CONF_LABEL[e.confidence] || e.confidence }),
    el("td", { textContent: e.basis }))));
  $("sources").replaceChildren(...(res.sources || []).map((s) =>
    el("li", {}, el("a", { href: s.url, target: "_blank", rel: "noopener", textContent: s.title || s.url }))));
  $("vision").textContent = JSON.stringify(res.vision, null, 2);
  $("notes").textContent = res.research_notes || "";
}

function tagsLength(str) {
  const tags = str.split(",").map((t) => t.trim()).filter(Boolean);
  if (!tags.length) return 0;
  return tags.reduce((n, t) => n + t.length + (t.includes(" ") ? 2 : 0), 0) + tags.length - 1;
}
function updateCounts() {
  $("desc-count").textContent = $("desc").value.length;
  const n = tagsLength($("tags").value);
  $("tags-count").textContent = n;
  $("tags-count").style.color = n > 500 ? "var(--err)" : "";
}
$("desc").addEventListener("input", () => { updateCounts(); markDirty(); });
$("tags").addEventListener("input", () => { updateCounts(); markDirty(); });
$("hashtags").addEventListener("input", markDirty);
$("r-memo").addEventListener("input", markDirty);
$("r-status").addEventListener("change", markDirty);

function copyBtn(get) {
  const b = el("button", { className: "copy", textContent: "복사" });
  b.addEventListener("click", () => copy(get(), b));
  return b;
}
async function copy(text, btn) {
  try { await navigator.clipboard.writeText(text); } catch {
    const t = el("textarea", { value: text }); document.body.append(t); t.select();
    document.execCommand("copy"); t.remove();
  }
  btn.classList.add("done"); btn.textContent = "복사됨";
  setTimeout(() => { btn.classList.remove("done"); btn.textContent = "복사"; }, 1500);
}
document.querySelectorAll("button.copy[data-target]").forEach((b) =>
  b.addEventListener("click", () => copy($(b.dataset.target).value, b)));

// ================= 보관함 =================
const STATUS_LABEL = { draft: "초안", uploaded: "업로드 완료", hold: "보류" };
let current = null;   // 지금 화면에 띄운 보관함 항목
let dirty = false;

function fmtDate(sec) {
  const d = new Date(sec * 1000);
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function showView(view) {
  const fromBatch = view === "detail" && current && current.from === "batch";
  $("tab-new").classList.toggle("active", view === "new" || fromBatch);
  $("tab-lib").classList.toggle("active", view === "lib" || (view === "detail" && !fromBatch));
  $("view-new").classList.toggle("hidden", view !== "new");
  $("view-lib").classList.toggle("hidden", view !== "lib");
  $("result").classList.toggle("hidden", !(view === "detail" || (view === "new" && current && current.from === "new")));
  $("r-back").classList.toggle("hidden", view !== "detail");
  $("r-back").textContent = fromBatch ? "← 재생목록" : "← 보관함";
  if (view === "lib") loadLibrary();
}

function confirmLeave() {
  return !dirty || confirm("저장하지 않은 변경 사항이 있습니다. 버리고 이동할까요?");
}

document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  if (!confirmLeave()) return;
  setDirty(false);
  if (current && current.from !== "new") current = null;
  showView(b.dataset.view);
}));
$("r-back").addEventListener("click", () => {
  if (!confirmLeave()) return;
  const from = current && current.from;
  setDirty(false);
  current = null;
  showView(from === "batch" ? "new" : "lib");
});

async function refreshLibCount() {
  try {
    const items = await (await fetch("/api/analyses")).json();
    $("lib-count").textContent = items.length ? items.length : "";
  } catch { /* ignore */ }
}

let qTimer;
$("lib-q").addEventListener("input", () => { clearTimeout(qTimer); qTimer = setTimeout(loadLibrary, 250); });
$("lib-status").addEventListener("change", loadLibrary);

let libSeq = 0;
async function loadLibrary() {
  const seq = ++libSeq;
  const qs = new URLSearchParams({ q: $("lib-q").value.trim(), status: $("lib-status").value });
  const items = await (await fetch(`/api/analyses?${qs}`)).json();
  if (seq !== libSeq) return;   // 더 최근 요청의 결과를 덮어쓰지 않도록
  $("lib-empty").classList.toggle("hidden", items.length > 0);
  $("lib-list").replaceChildren(...items.map((a) => {
    const thumb = a.thumbnail ? el("img", { className: "thumb", src: a.thumbnail, alt: "", loading: "lazy" })
                              : el("div", { className: "thumb" });
    let sub = [fmtDate(a.created_at), a.hint && `힌트: ${a.hint}`, a.memo && `메모: ${a.memo}`].filter(Boolean).join(" · ");
    if (a.playlist) sub = `재생목록: ${a.playlist} · ${sub}`;
    const main = el("div", { className: "lib-main" },
      el("div", { className: "lib-title", textContent: a.title || a.url }),
      el("div", { className: "lib-song", textContent: a.song ? `♪ ${a.song}` : "노래 미확인" }),
      el("div", { className: "muted small", textContent: sub }));
    const card = el("div", { className: "card lib-item" }, thumb, main,
      el("span", { className: `status ${a.status}`, textContent: STATUS_LABEL[a.status] || a.status }));
    card.addEventListener("click", () => openAnalysis(a.id, "lib"));
    return card;
  }));
}

async function openAnalysis(id, from) {
  const r = await fetch(`/api/analyses/${id}`);
  if (!r.ok) { alertBox("보관함 항목을 불러오지 못했습니다."); return; }
  current = await r.json();
  current.from = from;
  renderResult(current.result);
  renderManage();
  setDirty(false);
  showView(from === "new" ? "new" : "detail");
  if (from !== "new") window.scrollTo(0, 0);
}

function renderManage() {
  const a = current;
  $("r-thumb").classList.toggle("hidden", !a.thumbnail);
  if (a.thumbnail) $("r-thumb").src = a.thumbnail;
  $("r-link").textContent = a.title || a.url;
  $("r-link").href = a.url || "#";
  const edited = a.updated_at - a.created_at > 1 ? ` · 수정 ${fmtDate(a.updated_at)}` : "";
  $("r-date").textContent = `분석 ${fmtDate(a.created_at)}${edited}`;
  $("r-hint").textContent = a.hint ? ` · 힌트: ${a.hint}` : "";
  $("r-status").value = a.status;
  $("r-memo").value = a.memo || "";
  $("r-restore").classList.toggle("hidden", !a.result.original_meta);
}

function markDirty() { if (current) setDirty(true); }
function setDirty(v) {
  dirty = v;
  $("r-saved").textContent = v ? "저장하지 않은 변경 사항" : current ? "저장됨" : "";
  $("r-saved").classList.toggle("dirty", v);
}

function collectMeta() {
  const rows = [...document.querySelectorAll("#titles .title-row")];
  const titles = rows.map((row) => row.querySelector(".title-input").value.trim()).filter(Boolean);
  const picked = rows.find((row) => row.querySelector("input[type=radio]").checked);
  return {
    title_candidates: titles,
    selected_title: picked ? picked.querySelector(".title-input").value.trim() : titles[0] || "",
    description: $("desc").value,
    tags: $("tags").value.split(",").map((t) => t.trim()).filter(Boolean),
    hashtags: $("hashtags").value.split(/\s+/).filter(Boolean),
  };
}

$("r-save").addEventListener("click", async () => {
  if (!current) return;
  const r = await fetch(`/api/analyses/${current.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ meta: collectMeta(), status: $("r-status").value, memo: $("r-memo").value }),
  });
  if (!r.ok) {
    const detail = (await r.json().catch(() => ({}))).detail || r.statusText;
    alertBox(`저장 실패: ${detail}`);
    return;
  }
  const from = current.from;
  current = await r.json();
  current.from = from;
  renderResult(current.result);   // 제한에 맞게 보정된 값으로 다시 표시
  renderManage();
  setDirty(false);
  refreshLibCount();
});

$("r-restore").addEventListener("click", () => {
  const o = current && current.result.original_meta;
  if (!o) return;
  renderTitles(o.title_candidates || [], (o.title_candidates || [])[0]);
  $("desc").value = o.description || "";
  $("tags").value = (o.tags || []).join(", ");
  $("hashtags").value = (o.hashtags || []).join(" ");
  updateCounts();
  setDirty(true);   // 저장을 눌러야 반영됨
});

$("r-delete").addEventListener("click", async () => {
  if (!current || !confirm(`"${current.title}" 분석 결과를 보관함에서 삭제할까요?`)) return;
  await fetch(`/api/analyses/${current.id}`, { method: "DELETE" });
  current = null;
  setDirty(false);
  refreshLibCount();
  showView("lib");
});

$("r-reanalyze").addEventListener("click", () => {
  if (!current || !confirmLeave()) return;
  $("url").value = current.url;
  $("hint").value = current.hint || "";
  $("force").checked = true;
  setDirty(false);
  current = null;
  showView("new");
  $("go").disabled = false;
  $("go").click();
});

function alertBox(msg) {
  $("warnings").prepend(el("div", { className: "warn", textContent: `⚠ ${msg}` }));
}

window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
refreshLibCount();

// ================= 재생목록 일괄 분석 =================
let batchId = null;
let batchTimer = null;
let lastDone = -1;

function startBatch(b) {
  batchId = b.id;
  lastDone = -1;
  renderBatch(b);
  pollBatch();
}

async function pollBatch() {
  clearTimeout(batchTimer);
  if (!batchId) return;
  try {
    const b = await (await fetch(`/api/batches/${batchId}`)).json();
    if (b.id !== batchId) return;
    renderBatch(b);
    if (b.finished) { refreshLibCount(); return; }
  } catch { /* 재시도 */ }
  batchTimer = setTimeout(pollBatch, 2000);
}

const IDLE = ["queued", "done", "error", "canceled"];

function renderBatch(b) {
  $("batch").classList.remove("hidden");
  const more = b.total_in_playlist > b.total ? ` (전체 ${b.total_in_playlist}개 중 앞 ${b.total}개)` : "";
  $("b-title").textContent = `재생목록: ${b.title} · ${b.total}개${more}`;
  const fin = b.done + b.error + b.canceled;
  $("b-bar").style.width = `${Math.round((fin / Math.max(b.total, 1)) * 100)}%`;
  const running = b.items.find((i) => !IDLE.includes(i.status));
  $("b-summary").textContent = [
    `완료 ${b.done}`, b.error && `오류 ${b.error}`, b.canceled && `취소 ${b.canceled}`,
    `남음 ${b.total - fin}`, b.hint && `힌트: ${b.hint}`,
    b.finished ? "모두 끝났습니다" : running ? `진행 중: ${running.title || running.url}` : "",
  ].filter(Boolean).join(" · ");
  $("b-cancel").classList.toggle("hidden", b.finished || !b.items.some((i) => i.status === "queued"));
  if (b.done !== lastDone) { lastDone = b.done; refreshLibCount(); }
  $("b-items").replaceChildren(...b.items.map((it, n) => {
    const busy = !IDLE.includes(it.status);
    const label = it.status === "done" && it.cached ? "완료 (보관함)" : it.status_label;
    const stText = it.status === "error" ? `오류: ${it.error.slice(0, 40)}` : label;
    const row = el("li", { className: busy ? "active" : it.status, title: it.error || it.url },
      el("span", { className: "idx", textContent: n + 1 }),
      el("span", { className: "t", textContent: it.title || it.url }),
      el("span", { className: "st", textContent: stText }));
    if (it.analysis_id) {
      const open = el("button", { className: "ghost", textContent: "열기" });
      open.addEventListener("click", () => openAnalysis(it.analysis_id, "batch"));
      row.append(open);
    }
    return row;
  }));
}

$("b-cancel").addEventListener("click", async () => {
  if (!batchId || !confirm("아직 시작하지 않은 영상의 분석을 취소할까요? (진행 중인 영상은 끝까지 진행됩니다)")) return;
  const r = await (await fetch(`/api/batches/${batchId}/cancel`, { method: "POST" })).json();
  renderBatch(r.batch);
});

// 페이지를 새로 열어도 진행 중인 재생목록 작업을 이어서 보여 줌
fetch("/api/batches").then((r) => r.json()).then((list) => {
  const active = list.find((b) => !b.finished);
  if (active && !batchId) startBatch(active);
}).catch(() => {});
