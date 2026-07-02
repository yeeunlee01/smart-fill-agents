/* smart-fill-agents — 바닐라 프론트엔드
 * 백엔드와는 같은 출처(/api/v1/*)로 HTTP 통신한다. (정적 파일도 be가 서빙)
 */
"use strict";

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/* ===== intent 배지 메타 ===== */
const INTENT_ORDER = ["Chat", "DocQA", "TemplateFill", "Ask"];
const INTENT_LABEL = {
  Chat: "일반채팅",
  DocQA: "문서질의응답",
  TemplateFill: "템플릿채우기",
  Ask: "누락안내",
};
const INTENT_EMOJI = { Chat: "🟢", DocQA: "🔵", TemplateFill: "🟣", Ask: "🟠" };

/* ===== 공통: HTML escape + 미니 마크다운 ===== */
function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );
}

// 아주 가벼운 마크다운 → HTML (굵게/코드/제목/구분선/불릿/문단)
function miniMarkdown(src) {
  const lines = escapeHtml(src).split("\n");
  let html = "";
  let inList = false;
  const inline = (t) =>
    t
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  const closeList = () => {
    if (inList) { html += "</ul>"; inList = false; }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (line === "") { closeList(); continue; }
    if (/^---+$/.test(line)) { closeList(); html += "<hr>"; continue; }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { closeList(); html += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`; continue; }
    if (/^[-*]\s+/.test(line)) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(line.replace(/^[-*]\s+/, ""))}</li>`;
      continue;
    }
    closeList();
    html += `<p>${inline(line)}</p>`;
  }
  closeList();
  return html;
}

// 백엔드가 답변 뒤에 붙이는 근거(`\n\n---\n📎 **근거**\n...`)를 접이식 토글로 분리한다.
// 답변 본문은 그대로, 근거는 '펼치면 보이는' 회색 토글로.
const SOURCES_MARK = /\n*-{3,}\n*📎\s*\*\*\s*근거\s*\*\*\s*\n?/;
function renderReply(text) {
  const t = text || "";
  const m = t.match(SOURCES_MARK);
  if (!m) return miniMarkdown(t);
  const answer = t.slice(0, m.index);
  const sources = t.slice(m.index + m[0].length);
  let html = miniMarkdown(answer);
  if (sources.trim()) {
    html +=
      `<details class="sources"><summary>근거</summary>` +
      `<div class="sources-body">${miniMarkdown(sources)}</div></details>`;
  }
  return html;
}

// 최종 답변 렌더. 구조화된 sources가 있으면 '클릭 가능한' 근거 토글로(원문 하이라이트),
// 없으면(일반채팅/템플릿채우기 등) 기존 마크다운 토글로 폴백.
function renderFinal(bubble, text, sources) {
  if (!sources || !sources.length) {
    bubble.innerHTML = renderReply(text);
    return;
  }
  const m = text.match(SOURCES_MARK);
  const answer = m ? text.slice(0, m.index) : text; // 본문에 붙은 마크다운 근거는 떼고
  bubble.innerHTML = miniMarkdown(answer);
  bubble.appendChild(buildSourcesToggle(sources)); // 구조화 근거로 새로 그림
}

// 원본 바이트를 들고 있어 하이라이트가 가능한 출처인지 (PDF · docx)
function canHighlight(s) {
  const rec = s && chatDocs[s.doc];
  return !!(rec && (rec.kind === "pdf" || rec.kind === "docx"));
}

function buildSourcesToggle(sources) {
  const det = document.createElement("details");
  det.className = "sources";
  det.innerHTML = `<summary>근거</summary><div class="sources-body"></div>`;
  const body = $(".sources-body", det);
  const thumbs = []; // 토글 펼 때 렌더할 대상 {s, thumbEl, locEl}
  sources.forEach((s) => {
    const item = document.createElement("div");
    item.className = "source-item";
    const viewable = canHighlight(s);
    item.innerHTML =
      (viewable ? `<div class="src-thumb"><div class="src-thumb-ph">미리보기…</div></div>` : "") +
      `<div class="src-meta">` +
        `<div class="src-doc">${escapeHtml(s.doc || "")}</div>` +
        (s.location ? `<div class="src-loc">${escapeHtml(s.location)}</div>` : "") +
        (s.score != null ? `<div class="src-score">연관도 ${Number(s.score).toFixed(2)}</div>` : "") +
      `</div>`;
    if (viewable) {
      item.classList.add("clickable");
      item.addEventListener("click", () => openPdfEvidence(s));
      thumbs.push({ s, thumbEl: $(".src-thumb", item), locEl: $(".src-loc", item) });
    }
    body.appendChild(item);
  });

  // 토글을 처음 펼 때 각 근거의 썸네일(페이지+형광펜)을 렌더 + docx는 '본문'→'페이지 N' 라벨 갱신
  if (thumbs.length) {
    let rendered = false;
    det.addEventListener("toggle", () => {
      if (!det.open || rendered) return;
      rendered = true;
      thumbs.forEach(({ s, thumbEl, locEl }) => renderSourceThumb(s, thumbEl, locEl));
    });
  }
  return det;
}

// 근거 항목의 썸네일(그 페이지 축소 렌더 + 형광펜)을 그린다. docx면 페이지 라벨도 갱신.
async function renderSourceThumb(s, thumbEl, locEl) {
  const rec = chatDocs[s && s.doc];
  if (!rec || !thumbEl) return;
  try {
    const pdf = await loadEvidencePdf(rec, s.doc);
    let page;
    if (rec.kind === "docx") {
      page = await resolveDocxPage(s);
      if (locEl) locEl.textContent = page ? `페이지 ${page}` : "본문";
    } else {
      page = _pageNum(s.location);
    }
    await _renderPageWithHighlights(thumbEl, pdf, page || 1, s.texts || [], { noScroll: true });
  } catch (_) {
    thumbEl.innerHTML = `<div class="src-thumb-ph">미리보기 없음</div>`;
    if (locEl && rec.kind === "docx") locEl.textContent = "본문";
  }
}

// docx 근거의 페이지를 해결 (PDF 변환+페이지 탐색, 결과 캐시). 없으면 null.
async function resolveDocxPage(s) {
  const rec = chatDocs[s && s.doc];
  if (!rec || rec.kind !== "docx") return null;
  if (s._page !== undefined) return s._page;
  const pdf = await loadEvidencePdf(rec, s.doc);
  s._page = (await _findPageWithText(pdf, s.texts || [])) || null;
  return s._page;
}

// docx 근거의 페이지를 해결 (PDF 변환+페이지 탐색, 결과 캐시). 없으면 null.
async function resolveDocxPage(s) {
  const rec = chatDocs[s && s.doc];
  if (!rec || rec.kind !== "docx") return null;
  if (s._page !== undefined) return s._page;
  const pdf = await loadEvidencePdf(rec, s.doc);
  s._page = (await _findPageWithText(pdf, s.texts || [])) || null;
  return s._page;
}

/* ===== 근거 원문 PDF 모달 + 하이라이트 ===== */
function _pdfModalEls() {
  return { modal: $("#pdf-modal"), body: $("#pdf-modal-body"), title: $("#pdf-modal-title") };
}
function closePdfModal() {
  const { modal, body } = _pdfModalEls();
  if (!modal) return;
  modal.hidden = true;
  body.innerHTML = "";
}
function _pageNum(location) {
  const m = (location || "").match(/(\d+)/);
  return m ? parseInt(m[1], 10) : 1;
}

async function openPdfEvidence(s) {
  const rec = chatDocs[s.doc];
  const { modal, body, title } = _pdfModalEls();
  if (!rec || !modal) return;
  title.textContent = `${s.doc} · ${s.location || ""}`;
  body.innerHTML = `<div class="pdf-modal-msg">불러오는 중…${rec.kind === "docx" ? " (문서 변환 중)" : ""}</div>`;
  modal.hidden = false;
  try {
    const pdf = await loadEvidencePdf(rec, s.doc);       // docx면 PDF로 변환(캐시)
    // docx는 페이지번호가 없으니(본문) 근거 문장이 있는 페이지를 찾는다 (토글에서 이미 찾았으면 재사용)
    const known = rec.kind === "docx" ? await resolveDocxPage(s) : _pageNum(s.location);
    if (rec.kind === "docx" && known) title.textContent = `${s.doc} · 페이지 ${known}`;
    await renderEvidence(body, pdf, known, s.texts || []);
  } catch (e) {
    body.innerHTML = `<div class="pdf-modal-msg">미리보기를 불러오지 못했어요: ${escapeHtml(String(e))}</div>`;
  }
}

// 출처 원본 → pdf.js 문서. pdf는 바로, docx는 LibreOffice(/templates/pdf)로 변환. 문서당 1회 캐시.
async function loadEvidencePdf(rec, docName) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "/vendor/pdf.worker.min.js";
  if (rec._pdf) return rec._pdf;
  let bytes;
  if (rec.kind === "docx") {
    const blob = base64ToBlob(rec.b64, DOCX_MIME);
    const fd = new FormData(); fd.append("file", blob, docName || "doc.docx");
    const res = await fetch("/api/v1/templates/pdf", { method: "POST", body: fd });
    if (!res.ok) throw new Error(`PDF 변환 실패 (${res.status})`);
    bytes = new Uint8Array(await res.arrayBuffer());
  } else {
    bytes = base64ToBytes(rec.b64);
  }
  rec._pdf = await pdfjsLib.getDocument({ data: bytes }).promise;
  return rec._pdf;
}

// 근거를 렌더할 페이지 결정 후, 문서 '전체'를 세로로 렌더하고 근거 페이지로 스크롤.
async function renderEvidence(container, pdf, page, texts) {
  let focus = page ? Math.min(Math.max(page, 1), pdf.numPages) : null;
  if (focus === null) focus = (await _findPageWithText(pdf, texts)) || 1;
  await _renderAllPages(container, pdf, focus, texts);
}

// 문서 전체 페이지를 세로로 쌓아 렌더(스크롤 가능). 근거 문장이 있는 페이지엔 형광펜, focus 페이지로 스크롤.
async function _renderAllPages(container, pdf, focus, texts) {
  container.innerHTML = "";
  const col = document.createElement("div");
  col.className = "pdf-hl-doc";
  container.appendChild(col);

  const avail = (container.clientWidth || 820) - 24;
  const dpr = Math.min(window.devicePixelRatio || 1, 2);

  for (let p = 1; p <= pdf.numPages; p++) {
    const page = await pdf.getPage(p);
    const base = page.getViewport({ scale: 1 });
    const scale = Math.min(avail / base.width, 1.6);
    const vp = page.getViewport({ scale });

    const wrap = document.createElement("div");
    wrap.className = "pdf-hl-page";
    wrap.style.width = vp.width + "px";
    wrap.style.height = vp.height + "px";

    const canvas = document.createElement("canvas");
    canvas.width = Math.floor(vp.width * dpr);
    canvas.height = Math.floor(vp.height * dpr);
    canvas.style.width = vp.width + "px";
    canvas.style.height = vp.height + "px";
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    wrap.appendChild(canvas);

    const overlay = document.createElement("div");
    overlay.className = "pdf-hl-overlay";
    wrap.appendChild(overlay);
    col.appendChild(wrap);

    await page.render({ canvasContext: ctx, viewport: vp }).promise;

    // 이 페이지에서 근거 문장이 매칭되면 형광펜
    const rects = _highlightRects(await page.getTextContent(), vp, texts);
    rects.forEach((r) => {
      const mark = document.createElement("div");
      mark.className = "pdf-hl-mark";
      mark.style.left = r.x + "px"; mark.style.top = r.y + "px";
      mark.style.width = r.w + "px"; mark.style.height = r.h + "px";
      overlay.appendChild(mark);
    });

    if (p === focus) wrap.scrollIntoView({ block: "start" }); // 근거 페이지로 바로 스크롤
  }
}

// 근거 문장(texts)이 실제로 있는 페이지 번호 탐색 (렌더 없이 텍스트만 확인)
async function _findPageWithText(pdf, texts) {
  const needles = (texts || []).map(_sigChars).filter((n) => n.length >= 2);
  if (!needles.length) return null;
  for (let p = 1; p <= pdf.numPages; p++) {
    const tc = await (await pdf.getPage(p)).getTextContent();
    let compact = "";
    for (const it of tc.items) for (const ch of it.str) if (_SIG.test(ch)) compact += ch.toLowerCase();
    if (needles.some((n) => compact.includes(n) || (n.length > 24 && compact.includes(n.slice(0, 24))))) return p;
  }
  return null;
}

function base64ToBytes(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

// pdf.js 텍스트 아이템 하나의 화면 좌표 사각형 (하이라이트 박스용)
function _itemRect(item, viewport) {
  const t = pdfjsLib.Util.transform(viewport.transform, item.transform);
  const h = Math.hypot(t[2], t[3]) || 12;       // 대략 글자 높이
  const w = (item.width || 0) * viewport.scale; // 텍스트공간 폭 → 화면 폭
  return { x: t[4], y: t[5] - h, w, h: h * 1.15 };
}

// 매칭용으로 남길 문자: 한글·영숫자만 (공백·기호·구두점 전부 무시)
//  → pypdf(근거 문장)와 pdf.js(text layer)의 공백/기호 차이를 흡수한다.
const _SIG = /[0-9A-Za-z가-힣]/;
function _sigChars(s) {
  let out = "";
  for (const ch of s || "") if (_SIG.test(ch)) out += ch.toLowerCase();
  return out;
}

// 텍스트 레이어에서 texts(근거 문장)에 해당하는 아이템들의 하이라이트 사각형 계산
function _highlightRects(textContent, viewport, texts) {
  const items = textContent.items.filter((it) => it.str && it.str.trim());
  // 공백·기호를 뺀 '압축' 페이지 문자열 + 각 압축문자 → item 인덱스 매핑
  let compact = "";
  const owner = [];
  items.forEach((it, ii) => {
    for (const ch of it.str) {
      if (_SIG.test(ch)) { compact += ch.toLowerCase(); owner.push(ii); }
    }
  });
  const rects = [];
  const seen = new Set();
  (texts || []).forEach((raw) => {
    const needle = _sigChars(raw);
    if (needle.length < 2) return;
    let idx = compact.indexOf(needle);
    if (idx < 0 && needle.length > 24) idx = compact.indexOf(needle.slice(0, 24)); // 앞부분만이라도
    if (idx < 0) return;
    const end = idx + Math.min(needle.length, compact.length - idx);
    for (let i = idx; i < end; i++) {
      const ii = owner[i];
      if (!seen.has(ii)) { seen.add(ii); rects.push(_itemRect(items[ii], viewport)); }
    }
  });
  return rects;
}

async function _renderPageWithHighlights(container, pdf, pageNum, texts, opts = {}) {
  const pnum = Math.min(Math.max(pageNum || 1, 1), pdf.numPages);
  const page = await pdf.getPage(pnum);

  const avail = (container.clientWidth || 820) - 8;
  const base = page.getViewport({ scale: 1 });
  const scale = Math.min(avail / base.width, 1.6);
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const vp = page.getViewport({ scale });

  const wrap = document.createElement("div");
  wrap.className = "pdf-hl-page";
  wrap.style.width = vp.width + "px";
  wrap.style.height = vp.height + "px";

  const canvas = document.createElement("canvas");
  canvas.width = Math.floor(vp.width * dpr);
  canvas.height = Math.floor(vp.height * dpr);
  canvas.style.width = vp.width + "px";
  canvas.style.height = vp.height + "px";
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  wrap.appendChild(canvas);

  const overlay = document.createElement("div");
  overlay.className = "pdf-hl-overlay";
  wrap.appendChild(overlay);

  container.innerHTML = "";
  container.appendChild(wrap);

  await page.render({ canvasContext: ctx, viewport: vp }).promise;

  const tc = await page.getTextContent();
  const rects = _highlightRects(tc, vp, texts);
  rects.forEach((r) => {
    const mark = document.createElement("div");
    mark.className = "pdf-hl-mark";
    mark.style.left = r.x + "px";
    mark.style.top = r.y + "px";
    mark.style.width = r.w + "px";
    mark.style.height = r.h + "px";
    overlay.appendChild(mark);
  });
  if (!opts.noScroll) {
    const first = overlay.querySelector(".pdf-hl-mark");
    if (first) first.scrollIntoView({ block: "center" });
  }
}

/* ======================================================================
 *  탭 전환
 * ==================================================================== */
$$(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".nav-item").forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    const view = btn.dataset.view;
    $("#view-chat").classList.toggle("is-active", view === "chat");
    $("#view-templates").classList.toggle("is-active", view === "templates");
    if (view === "chat") refreshTemplateSelect();
    if (view === "templates") {
      // '새 템플릿 등록'은 바로 편집기로, '템플릿 목록'은 라이브러리로
      if (btn.dataset.action === "new") openEditor(null);
      else renderLibrary();
    }
  });
});

/* ======================================================================
 *  템플릿 저장소 (localStorage)
 * ==================================================================== */
const TPL_KEY = "sfa_templates";

function loadTemplates() {
  try {
    const raw = localStorage.getItem(TPL_KEY);
    if (raw) return JSON.parse(raw);
  } catch (_) {}
  const seed = [
    {
      name: "사업계획서 (샘플)",
      raw_text: "사업 개요\n시장 분석\n수익 모델\n팀 구성",
      slots: [
        { name: "사업 개요", definition: "사업의 목적과 배경을 2~3문장으로 요약" },
        { name: "시장 분석", definition: "타깃 시장 규모와 경쟁 현황" },
        { name: "수익 모델", definition: "주요 매출원과 과금 방식" },
        { name: "팀 구성", definition: "핵심 멤버와 역할" },
      ],
    },
  ];
  saveTemplates(seed);
  return seed;
}
function saveTemplates(list) { localStorage.setItem(TPL_KEY, JSON.stringify(list)); }
function getTemplate(name) { return loadTemplates().find((t) => t.name === name) || null; }
function deleteTemplate(name) { saveTemplates(loadTemplates().filter((t) => t.name !== name)); }
function upsertTemplate(tpl) {
  const list = loadTemplates();
  const i = list.findIndex((t) => t.name === tpl.name);
  if (i >= 0) list[i] = tpl; else list.push(tpl);
  saveTemplates(list);
}

/* ===== 채팅 사이드바: 템플릿 선택 ===== */
function refreshTemplateSelect() {
  const sel = $("#template-select");
  const list = loadTemplates();
  const prev = sel.value;
  sel.innerHTML = "";
  // 닫힌 상태 텍스트로만 쓰는 머리글 — 드롭다운을 열면 목록에서 빠진다
  const ph = document.createElement("option");
  ph.value = ""; ph.textContent = "📄 채울 템플릿";
  ph.disabled = true; ph.hidden = true;
  sel.appendChild(ph);
  // 템플릿 해제용 '선택 안 함' (회색)
  const none = document.createElement("option");
  none.value = "__none__"; none.textContent = "선택 안 함";
  none.style.color = "var(--muted)";
  sel.appendChild(none);
  list.forEach((t) => {
    const o = document.createElement("option");
    o.value = t.name; o.textContent = "📄 " + t.name;
    sel.appendChild(o);
  });
  // 이전 선택이 있으면 유지, 없으면 머리글(빈값)
  sel.value = [...sel.options].some((o) => o.value === prev && o.value !== "") ? prev : "";
  $("#no-template-hint").hidden = list.length > 0;
}

/* ======================================================================
 *  템플릿 관리 화면
 * ==================================================================== */
function renderLibrary() {
  $("#tpl-editor").hidden = true;
  $("#tpl-library").hidden = false;
  const grid = $("#tpl-grid");
  grid.innerHTML = "";

  // 맨 앞 '새 템플릿' 카드 → 클릭 시 새 템플릿 등록 편집기로 연결
  const add = document.createElement("div");
  add.className = "tpl-card add";
  add.innerHTML = "<h3>➕ 새 템플릿</h3><p class='hint'>새 템플릿을 등록합니다</p>";
  add.addEventListener("click", () => openEditor(null));
  grid.appendChild(add);

  loadTemplates().forEach((t) => {
    const card = document.createElement("div");
    card.className = "tpl-card";
    const slotsHtml = t.slots.length
      ? t.slots.map((s) => `• <strong>${escapeHtml(s.name)}</strong> — ${escapeHtml(s.definition || "")}`).join("<br>")
      : "<em>(slot 없음)</em>";
    card.innerHTML = `
      <h3>📄 ${escapeHtml(t.name)}</h3>
      <div class="hint">slot ${t.slots.length}개</div>
      <div class="slots">${slotsHtml}</div>
      <div class="card-actions">
        <button class="btn edit">✏️ 편집</button>
        <button class="btn del">🗑️ 삭제</button>
      </div>`;
    $(".edit", card).addEventListener("click", () => openEditor(t.name));
    $(".del", card).addEventListener("click", () => {
      if (confirm(`'${t.name}' 템플릿을 삭제할까요?`)) { deleteTemplate(t.name); renderLibrary(); }
    });
    grid.appendChild(card);
  });
}

let editingName = null;     // null = 새 템플릿
let currentSlots = [];      // 편집 중 구간(segment): {name, definition, element_ids?}
let currentStructure = null;// docx 구조 {elements:[...]} — 색상 미리보기용 (없으면 텍스트 미리보기)
let currentFile = null;     // { name, b64, kind }  — 원본 파일(채우기용)
let currentText = "";       // 업로드 문서의 평문 (미리보기용)

function base64ToBlob(b64, type) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type });
}

const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

// docx → (백엔드 LibreOffice) PDF → pdf.js로 페이지별 렌더 (Word와 동일한 정확한 페이지)
// 페이지를 전부 그린 뒤 한 번에 교체 → '분석 중…'에서 문서가 '뿅' 나타남 (중간 변환 문구 없음)
async function renderDocxAsPdf(v) {
  const blob = base64ToBlob(currentFile.b64, DOCX_MIME);
  const fd = new FormData(); fd.append("file", blob, currentFile.name || "template.docx");
  const res = await fetch("/api/v1/templates/pdf", { method: "POST", body: fd });
  if (!res.ok) throw new Error(`PDF ${res.status}`);
  const ab = await res.arrayBuffer();

  pdfjsLib.GlobalWorkerOptions.workerSrc = "/vendor/pdf.worker.min.js";
  const pdf = await pdfjsLib.getDocument({ data: ab }).promise;

  const row = document.createElement("div"); // 화면 밖에서 먼저 다 그린다
  row.className = "pdf-pages";

  const targetW = 270;                                   // 페이지 표시 폭 (박스에 ~2.5장)
  const dpr = Math.min(window.devicePixelRatio || 1, 2); // 선명도
  for (let i = 1; i <= pdf.numPages; i++) {
    const page = await pdf.getPage(i);
    const base = page.getViewport({ scale: 1 });
    const cssScale = targetW / base.width;
    const vp = page.getViewport({ scale: cssScale * dpr });
    const canvas = document.createElement("canvas");
    canvas.className = "pdf-page";
    canvas.width = vp.width; canvas.height = vp.height;
    canvas.style.width = targetW + "px";
    canvas.style.height = base.height * cssScale + "px";
    row.appendChild(canvas);
    await page.render({ canvasContext: canvas.getContext("2d"), viewport: vp }).promise;
  }

  // 다 그린 뒤 한 번에 교체
  v.innerHTML = "";
  v.appendChild(row);
  // 보기창 높이를 문서(페이지) 높이에 맞춤 → 위아래 여백(.pdf-pages 패딩 16px)이 동일해짐
  // 페이지가 여러 장이라 가로 스크롤바가 생기면 그 높이만큼만 여유를 둔다
  const sbar = row.scrollWidth > v.clientWidth ? 18 : 0;
  v.style.height = row.offsetHeight + sbar + "px";
}

// 업로드 문서를 '서식 그대로' 미리보기 — docx는 PDF 렌더, md는 마크다운, txt는 평문
async function renderPreview() {
  const v = $("#tpl-viewer");
  const kind = currentFile ? currentFile.kind : "text";
  const fname = currentFile ? currentFile.name : "";
  const hasContent = (currentFile && currentFile.b64) || currentText;
  v.classList.remove("plain");
  v.style.height = "";  // 기본 높이로 리셋 (docx PDF 렌더만 문서 크기에 맞춰 덮어씀)
  if (!hasContent) {
    v.innerHTML = `<div class="viewer-empty">
      <button type="button" id="tpl-file-btn" class="btn btn-primary">📎 문서 불러오기</button>
      <div class="hint">.docx · .md · .txt</div>
    </div>`;
    $("#tpl-file-btn", v).addEventListener("click", () => $("#tpl-file").click());
    return;
  }

  if (kind === "docx" && currentFile.b64) {
    try {
      await renderDocxAsPdf(v);
      return;
    } catch (e) {
      // PDF 변환 실패 → docx-preview로 폴백
      if (window.docx) {
        try {
          const blob = base64ToBlob(currentFile.b64, DOCX_MIME);
          v.innerHTML = "";
          await window.docx.renderAsync(blob, v, null, { inWrapper: true, ignoreLastRenderedPageBreak: false });
          return;
        } catch (e2) { /* 평문 폴백 */ }
      }
    }
  }
  if (/\.md$/i.test(fname)) {
    v.innerHTML = `<div class="doc-html">${miniMarkdown(currentText)}</div>`;
  } else {
    v.classList.add("plain");
    v.textContent = currentText;
  }
}

function openEditor(name) {
  editingName = name;
  invalidateDocxRender();  // 다른 템플릿으로 전환 → docx-preview 캐시 무효화
  $("#tpl-library").hidden = true;
  $("#tpl-editor").hidden = false;
  $("#tpl-editor-title").textContent = name ? `✏️ 편집: ${name}` : "➕ 새 템플릿";
  const nameInput = $("#tpl-name");
  nameInput.value = name || "";
  nameInput.disabled = !!name;

  $("#tpl-slots-step").hidden = false; // 제목은 항상 표시
  if (name) {
    const t = getTemplate(name);
    currentSlots = (t.slots || []).map((s) => ({ ...s }));
    currentStructure = t.structure || null;
    currentFile = t.file_b64 ? { name: t.file_name, b64: t.file_b64, kind: t.kind } : null;
    currentText = t.text || "";
    $("#tpl-file-status").textContent = currentFile ? `현재 파일: ${currentFile.name}` : "";
    renderPreview();
    renderSlots();
  } else {
    currentSlots = [];
    currentStructure = null;
    currentFile = null;
    currentText = "";
    $("#tpl-file-status").textContent = "";
    renderPreview();
    renderSlots(); // 빈 상태 안내 표시
  }
}

function structById() {
  const m = new Map();
  (currentStructure?.elements || []).forEach((el) => m.set(el.id, el));
  return m;
}

/* ===== 감지 항목 토글 미리보기: 묶인 원문 요소를 '문서 양식 그대로' =====
 * 고충실 경로: docx-preview로 문서 전체를 Word처럼 한 번 렌더한 뒤,
 *   element_ids(=읽기 순서 index)에 해당하는 최상위 블록(<p>/<table>)만 클론해서 보여준다.
 * 매핑이 구조(structure)의 요소 종류 순서와 어긋나면 → null 반환 → 재구성 폴백.
 */
let _docxRender = null;   // Promise<{segmentNode(ids)->Node} | null> (파일당 1회 렌더 캐시)
let _docxStyles = [];     // head에 붙인 docx-preview <style> 노드 (무효화 시 제거)

function invalidateDocxRender() {
  _docxRender = null;
  _docxStyles.forEach((s) => s.remove());
  _docxStyles = [];
}

// 표 안에 중첩된 것 제외한 '최상위' 문단/표를 읽기 순서대로
function _topBlocks(root) {
  return [...root.querySelectorAll("p, table")].filter((n) =>
    n.tagName === "TABLE" ? !n.parentElement.closest("table") : !n.closest("table")
  );
}

function ensureDocxRender() {
  if (_docxRender) return _docxRender;
  _docxRender = (async () => {
    if (!currentFile || currentFile.kind !== "docx" || !currentFile.b64 || !window.docx || !currentStructure) {
      return null;
    }
    const holder = document.createElement("div");
    holder.style.cssText = "position:fixed;left:-99999px;top:0;width:820px;visibility:hidden;";
    const styleEl = document.createElement("div");
    const bodyEl = document.createElement("div");
    holder.append(styleEl, bodyEl);
    document.body.appendChild(holder);

    let wrapper = null;
    let aligned = false;
    try {
      await window.docx.renderAsync(base64ToBlob(currentFile.b64, DOCX_MIME), bodyEl, styleEl, {
        inWrapper: true, breakPages: false, ignoreLastRenderedPageBreak: true,
        renderHeaders: false, renderFooters: false, renderFootnotes: false, renderEndnotes: false,
      });
      wrapper = bodyEl.querySelector(".docx-wrapper") || bodyEl.firstElementChild;
      // 생성된 <style>은 head로 옮겨야 detached 클론에도 스타일이 적용됨
      [...styleEl.querySelectorAll("style")].forEach((s) => { document.head.appendChild(s); _docxStyles.push(s); });
      if (wrapper) {
        wrapper.remove(); // detached 원본으로 보관 (세그먼트마다 클론)
        const got = _topBlocks(wrapper).map((n) => n.tagName);
        const want = currentStructure.elements.map((el) => (el.kind === "table" ? "TABLE" : "P"));
        aligned = want.length === got.length && want.every((k, i) => k === got[i]);
      }
    } catch (_) {
      aligned = false;
    }
    holder.remove();
    if (!wrapper || !aligned) return null;  // 어긋나면 폴백

    return {
      segmentNode(ids) {
        const set = new Set(ids);
        const clone = wrapper.cloneNode(true);
        _topBlocks(clone).forEach((n, i) => { if (!set.has(i)) n.remove(); });
        // 남은 블록이 없는 section(페이지) 제거
        [...clone.querySelectorAll("section")].forEach((sec) => {
          if (!sec.querySelector("p, table")) sec.remove();
        });
        return clone;
      },
    };
  })();
  return _docxRender;
}

// 폴백: structure 요소들을 문서 양식 HTML로 재구성 (docx 매핑 실패 / 미지원 시)
function reconstructSegmentHtml(ids) {
  const byId = structById();
  return (ids || []).map((id) => {
    const el = byId.get(id);
    if (!el) return "";
    if (el.kind === "table") {
      let t = "<table><tbody>";
      for (let r = 0; r < el.rows; r++) {
        t += "<tr>";
        el.cells.slice(r * el.cols, (r + 1) * el.cols).forEach((c) => {
          const txt = (c.text || "").trim();
          t += txt
            ? `<td>${escapeHtml(txt)}</td>`
            : `<td class="empty-cell"><span class="sf-blank">빈칸</span></td>`;
        });
        t += "</tr>";
      }
      return t + "</tbody></table>";
    }
    if (el.kind === "heading") return `<h4>${escapeHtml(el.text || "")}</h4>`;
    if (el.fillable && el.fill_mode === "append") {
      return `<p><strong>${escapeHtml(el.label)}:</strong> <span class="sf-blank">채울 값</span></p>`;
    }
    const txt = (el.text || "").trim();
    return txt ? `<p>${escapeHtml(txt)}</p>` : `<p><span class="sf-blank">빈칸</span></p>`;
  }).join("");
}

// slot-card 하나에 '원문 보기' 토글을 붙인다 (펼 때 지연 렌더)
function attachSegPreview(card, seg) {
  const ids = seg.element_ids || [];
  if (!ids.length) return;
  const det = document.createElement("details");
  det.className = "seg-preview";
  det.innerHTML = `<summary>원문 보기 (${ids.length})</summary><div class="seg-body"></div>`;
  const body = $(".seg-body", det);
  let loaded = false;
  det.addEventListener("toggle", async () => {
    if (!det.open || loaded) return;
    loaded = true;
    body.innerHTML = `<div class="seg-loading">불러오는 중…</div>`;
    const render = await ensureDocxRender();
    body.innerHTML = "";
    const box = document.createElement("div");
    if (render) {
      box.className = "seg-doc";
      box.appendChild(render.segmentNode(ids));
    } else {
      box.className = "seg-recon";
      box.innerHTML = reconstructSegmentHtml(ids);
    }
    body.appendChild(box);
  });
  card.appendChild(det);
}

// 감지된 항목 영역에 안내 문구만 표시 (분석 중 / 비어 있음). 카드·저장은 숨김.
function showSlotsPlaceholder(msg) {
  const box = $("#tpl-slots");
  box.innerHTML = `<div class="slots-empty">${escapeHtml(msg)}</div>`;
  $("#tpl-slots-count").textContent = "";
  $("#tpl-slots-hint").hidden = true;
  $("#tpl-save-row").hidden = true;
}

// 문서 불러오기 전 빈 상태 — "이렇게 표시돼요" 예시 카드 (실제 감지 결과 아님)
const EXAMPLE_SLOTS = [
  {
    name: "결재 정보",
    def: "결재 라인·담당자·날짜",
    body: `<div class="seg-recon"><table><tbody>
      <tr><td>담당</td><td>팀장</td><td>부서장</td></tr>
      <tr><td class="empty-cell"><span class="sf-blank">빈칸</span></td><td class="empty-cell"><span class="sf-blank">빈칸</span></td><td class="empty-cell"><span class="sf-blank">빈칸</span></td></tr>
      </tbody></table></div>`,
  },
  {
    name: "제안 개요",
    def: "제안 배경과 핵심 요약",
    body: `<div class="seg-recon"><h4>1. 제안 개요</h4>
      <p><span class="sf-blank">여기에 제안 배경·요약이 채워집니다</span></p></div>`,
  },
];

function renderSlotsExample() {
  const box = $("#tpl-slots");
  $("#tpl-slots-count").textContent = "";
  $("#tpl-slots-hint").hidden = true;
  $("#tpl-save-row").hidden = true;
  box.innerHTML = `<p class="slots-example-note">문서를 불러오면 아래처럼 항목이 자동 감지돼요. <strong>(예시)</strong></p>`;
  EXAMPLE_SLOTS.forEach((ex, i) => {
    const card = document.createElement("div");
    card.className = "slot-card is-example";
    card.innerHTML = `
      <div class="slot-num">${i + 1}.</div>
      <div class="slot-card-head">
        <span class="ex-name">${escapeHtml(ex.name)}</span>
        <span class="ex-badge">예시</span>
      </div>
      <div class="ex-def">${escapeHtml(ex.def)}</div>
      <details class="seg-preview"><summary>원문 보기</summary><div class="seg-body">${ex.body}</div></details>`;
    box.appendChild(card);
  });
}

// 구간(묶음) 카드 — 번호 + 이름/설명 수정 + 삭제 + '원문 보기' 토글.
function renderSlots() {
  if (!currentSlots.length) {
    renderSlotsExample();  // 빈 상태 → 예시 카드로 "이렇게 표시돼요" 안내
    return;
  }
  $("#tpl-slots-hint").hidden = false;
  $("#tpl-save-row").hidden = false;
  const box = $("#tpl-slots");
  box.innerHTML = "";
  currentSlots.forEach((s, i) => {
    const card = document.createElement("div");
    card.className = "slot-card";
    card.innerHTML = `
      <div class="slot-num">${i + 1}.</div>
      <div class="slot-card-head">
        <input class="sname" placeholder="묶음 이름" />
        <span class="del" title="이 묶음 삭제">🗑️</span>
      </div>
      <input class="sdef" placeholder="채울 내용 설명 (가이드)" />`;
    $(".sname", card).value = s.name || "";
    $(".sdef", card).value = s.definition || "";
    $(".sname", card).addEventListener("input", (e) => { currentSlots[i].name = e.target.value; });
    $(".sdef", card).addEventListener("input", (e) => { currentSlots[i].definition = e.target.value; });
    $(".del", card).addEventListener("click", () => { currentSlots.splice(i, 1); renderSlots(); });
    attachSegPreview(card, s);  // '원문 보기' 토글 (묶인 원문을 문서 양식으로)
    box.appendChild(card);
  });

  // 총 개수 표시
  const countEl = $("#tpl-slots-count");
  if (countEl) countEl.textContent = currentSlots.length ? `총 ${currentSlots.length}개` : "";
}

function fileToBase64(file) {
  return new Promise((res, rej) => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(",")[1]); // data: 접두사 제거
    r.onerror = rej;
    r.readAsDataURL(file);
  });
}

$("#tpl-back").addEventListener("click", renderLibrary); // 편집기 → 목록으로
// '문서 불러오기' 버튼은 빈 미리보기 창 중앙에 렌더됨(renderPreview) → 거기서 바인딩

// 문서 첨부 → docx는 구조 분할(/detect), md·txt는 텍스트 추출+분할
$("#tpl-file").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  e.target.value = "";
  if (!f) return;
  const status = $("#tpl-file-status");
  const ext = (f.name.split(".").pop() || "").toLowerCase();
  const kind = ext === "docx" ? "docx" : "text";
  status.textContent = "";
  // 미리보기 창 한가운데에 '분석 중…' 표시 (높이는 기본값으로)
  const viewer = $("#tpl-viewer");
  viewer.style.height = "";
  viewer.innerHTML = '<div class="viewer-empty">‘' + escapeHtml(f.name) + '’ 분석 중…</div>';
  // 감지된 항목 영역에도 진행 안내 (미리보기가 먼저 떠도 분할이 끝나기 전까지 표시)
  $("#tpl-slots-step").hidden = false;
  showSlotsPlaceholder(`🔍 ‘${f.name}’을(를) 분석 중입니다…`);
  try {
    const b64 = await fileToBase64(f);
    currentFile = { name: f.name, b64, kind };
    invalidateDocxRender();  // 새 파일 → 이전 docx-preview 캐시 폐기
    currentStructure = null;
    currentSlots = [];

    // 미리보기 PDF는 구간 분할(LLM)과 무관 → 지금 바로 병렬로 렌더 시작 (끝나는 대로 '뿅')
    // 실패는 객체로 감싸 반환(미처리 거부 방지) → 나중에 폴백 렌더
    const pdfPromise = kind === "docx"
      ? renderDocxAsPdf(viewer).then(() => null).catch((e) => ({ __err: e }))
      : null;

    // 평문 추출
    const efd = new FormData(); efd.append("file", f, f.name);
    const exPromise = fetch("/api/v1/templates/extract", { method: "POST", body: efd })
      .then((r) => r.json().then((j) => ({ ok: r.ok, j })));

    let slots = [];
    let structure = null;
    let text = "";
    if (kind === "docx") {
      // 추출 + 구간 분할을 병렬로
      const dfd = new FormData(); dfd.append("file", f, f.name);
      const detPromise = fetch("/api/v1/templates/detect", { method: "POST", body: dfd })
        .then((r) => r.json().then((j) => ({ ok: r.ok, j })));
      const [exr, det] = await Promise.all([exPromise, detPromise]);
      if (!exr.ok) throw new Error(exr.j.detail || "원문 추출 실패");
      if (!det.ok) throw new Error(det.j.detail || "구간 분할 실패");
      text = exr.j.text || "";
      slots = det.j.segments || [];
      structure = det.j.structure || null;
    } else {
      // md·txt: 추출 → 텍스트 미리보기 즉시 표시 → 분할
      const exr = await exPromise;
      if (!exr.ok) throw new Error(exr.j.detail || "원문 추출 실패");
      text = exr.j.text || "";
      currentText = text;
      renderPreview();
      const sp = await fetch("/api/v1/templates/split", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const spd = await sp.json();
      if (!sp.ok) throw new Error(spd.detail || "분할 실패");
      slots = spd.slots || [];
    }

    currentText = text;
    currentStructure = structure;
    currentSlots = slots;

    // docx 미리보기: 병렬 렌더 완료 대기 (실패 시 폴백 렌더로 복구)
    if (pdfPromise) {
      const r = await pdfPromise;
      if (r && r.__err) renderPreview();
    }

    const nameInput = $("#tpl-name");
    if (!nameInput.disabled && !nameInput.value.trim()) nameInput.value = f.name.replace(/\.[^.]+$/, "");
    renderSlots();
  } catch (err) {
    status.textContent = `실패: ${String(err)}`;
    renderPreview(); // 미리보기 창을 '문서 불러오기' 버튼 상태로 복구
    renderSlots();   // 감지된 항목 영역의 '분석 중' 안내 정리
  }
});

$("#tpl-save").addEventListener("click", () => {
  const name = $("#tpl-name").value.trim();
  if (!name) { alert("템플릿 이름을 입력해 주세요."); return; }
  if (!editingName && getTemplate(name)) { alert("같은 이름의 템플릿이 이미 있어요."); return; }
  const slots = currentSlots.filter((s) => (s.name || "").trim());
  upsertTemplate({
    name,
    kind: currentFile ? currentFile.kind : "text",
    file_name: currentFile ? currentFile.name : "",
    file_b64: currentFile ? currentFile.b64 : "",
    text: currentText,
    structure: currentStructure,   // docx 구조 (색상 미리보기·채우기 주입용)
    slots,
  });
  renderLibrary();
  refreshTemplateSelect();
});

/* ======================================================================
 *  채팅 — 상태
 * ==================================================================== */
let threadId = null;
// 첨부: { name, status: 'pending'|'ok'|'error', error }
let attachments = [];
// 근거 하이라이트용 원본 파일 보관 (파일명 → {b64, kind}). 지금은 PDF만.
let chatDocs = {};

const messagesEl = $("#messages");
const scrollDown = () => { messagesEl.scrollTop = messagesEl.scrollHeight; };

/* ===== 첨부 영역 ===== */
function okDocNames() { return attachments.filter((a) => a.status === "ok").map((a) => a.name); }

function renderAttachments() {
  const list = $("#attach-list");
  list.innerHTML = "";
  attachments.forEach((a) => {
    const chip = document.createElement("span");
    chip.className = "chip" + (a.status === "error" ? " is-error" : "");
    if (a.status === "pending") {
      chip.innerHTML = `<span class="spin"></span>${escapeHtml(a.name)}`;
    } else if (a.status === "error") {
      chip.innerHTML = `⚠️ ${escapeHtml(a.name)}<span class="x" title="제거">✕</span>`;
      $(".x", chip).addEventListener("click", () => removeAttachment(a.name));
    } else {
      chip.innerHTML = `📄 ${escapeHtml(a.name)}<span class="x" title="제거">✕</span>`;
      $(".x", chip).addEventListener("click", () => removeAttachment(a.name));
    }
    list.appendChild(chip);
  });
  updateGreeting();
}

function removeAttachment(name) {
  attachments = attachments.filter((a) => a.name !== name);
  delete chatDocs[name];
  renderAttachments();
}

$("#attach-btn").addEventListener("click", () => $("#file-input").click());

$("#file-input").addEventListener("change", async (e) => {
  const files = [...e.target.files];
  e.target.value = ""; // 같은 파일 재선택 허용
  const fresh = files.filter((f) => !attachments.some((a) => a.name === f.name));
  if (!fresh.length) return;

  fresh.forEach((f) => attachments.push({ name: f.name, status: "pending" }));
  // 근거 하이라이트용 원본 바이트를 메모리에 보관 (PDF·docx). docx는 클릭 시 PDF로 변환.
  fresh.forEach((f) => {
    const ext = (f.name.split(".").pop() || "").toLowerCase();
    if (ext === "pdf" || ext === "docx") {
      fileToBase64(f).then((b64) => { chatDocs[f.name] = { b64, kind: ext }; });
    }
  });
  renderAttachments();

  const fd = new FormData();
  fresh.forEach((f) => fd.append("files", f, f.name));
  try {
    const res = await fetch("/api/v1/documents", { method: "POST", body: fd });
    const data = await res.json();
    (data.ingested || []).forEach((r) => {
      const a = attachments.find((x) => x.name === r.doc);
      if (!a) return;
      a.status = r.ok ? "ok" : "error";
      a.error = r.error || "";
    });
  } catch (err) {
    fresh.forEach((f) => {
      const a = attachments.find((x) => x.name === f.name);
      if (a) { a.status = "error"; a.error = String(err); }
    });
  }
  renderAttachments();
});

/* ===== 메시지 렌더링 ===== */
function updateGreeting() {
  let g = $("#greeting");
  if (!g) {
    g = document.createElement("div");
    g.id = "greeting";
    g.className = "msg assistant";
    g.innerHTML = '<div class="bubble"></div>';
    messagesEl.prepend(g);
  }
  const n = okDocNames().length;
  $(".bubble", g).innerHTML = miniMarkdown(
    n === 0
      ? "안녕하세요! 아래 **문서 첨부** 또는 **템플릿 선택**으로 작업을 시작해보세요."
      : `문서 **${n}개**를 받았어요. 이제 이렇게 활용할 수 있어요:\n\n` +
          "- **궁금한 점을 질문**하면 근거와 함께 답해드려요\n" +
          "- **템플릿을 채우려면** 입력창 아래 ‘📄 채울 템플릿’에서 고른 뒤 요청해 주세요"
  );
}

function addUserMessage(text) {
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<div class="bubble"></div>`;
  $(".bubble", el).textContent = text;
  messagesEl.appendChild(el);
  scrollDown();
}

function renderBadge(container, intent) {
  let badge = $(".intent-badge", container);
  if (!badge) {
    badge = document.createElement("div");
    badge.className = "intent-badge";
    container.prepend(badge);
  }
  badge.innerHTML = INTENT_ORDER.map((k) =>
    k === intent
      ? `<span class="pill on">${INTENT_EMOJI[k]} ${INTENT_LABEL[k]}</span>`
      : `<span class="pill">${INTENT_LABEL[k]}</span>`
  ).join('<span class="pill-sep">/</span>');
}

// 빈 assistant 말풍선 생성 → {container, bubble} 반환
function addAssistantMessage() {
  const el = document.createElement("div");
  el.className = "msg assistant";
  el.innerHTML = `<div class="bubble streaming"></div>`;
  messagesEl.appendChild(el);
  scrollDown();
  return { container: el, bubble: $(".bubble", el) };
}

/* ===== 전송 + SSE 스트리밍 ===== */
const composer = $("#composer");
const promptEl = $("#prompt");
const sendBtn = $("#send-btn");

promptEl.addEventListener("input", () => {
  promptEl.style.height = "auto";
  promptEl.style.height = Math.min(promptEl.scrollHeight, 160) + "px";
});
promptEl.addEventListener("keydown", (e) => {
  // e.isComposing: 한글 등 IME 조합 중에는 Enter를 전송으로 처리하지 않는다
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    composer.requestSubmit();
  }
});

composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  // IME 조합 중인 마지막 글자를 강제 확정(blur) → 비운 뒤 되돌아오는 잔류 글자 방지
  promptEl.blur();
  const text = promptEl.value.trim();
  if (!text || sendBtn.disabled) { promptEl.focus(); return; }

  // 첫 메시지 → 가운데 입력창을 하단으로 내리고 대화 모드로
  $(".chat-main").classList.remove("welcome");

  addUserMessage(text);
  promptEl.value = "";
  promptEl.style.height = "auto";
  promptEl.focus();

  const selName = $("#template-select").value;
  const tpl = selName && selName !== "__none__" ? getTemplate(selName) : null;
  const payload = {
    message: text,
    thread_id: threadId,
    documents: okDocNames(),
    template: tpl ? { name: tpl.name, slots: tpl.slots } : null,
  };

  sendBtn.disabled = true;
  const { container, bubble } = addAssistantMessage();

  // 후처리 없이 받는 즉시 그대로 표시한다.
  //  - 게이트웨이가 한꺼번에 던지면 → 한꺼번에 나옴
  //  - 비동기 스트리밍이면 → 토큰이 오는 대로 즉시 한 글자씩 나옴
  let acc = "";           // 받은 토큰 누적(평문)
  let finalized = false;  // done으로 최종 확정했는지

  try {
    const res = await fetch("/api/v1/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buf.indexOf("\n\n")) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        const dataLine = block.split("\n").find((l) => l.startsWith("data:"));
        if (!dataLine) continue;
        const ev = JSON.parse(dataLine.slice(5).trim());

        if (ev.type === "meta") {
          threadId = ev.thread_id || threadId;
          renderBadge(container, ev.intent);
        } else if (ev.type === "token") {
          acc += ev.text;
          bubble.innerHTML = miniMarkdown(acc); // 오는 즉시 마크다운으로 렌더 (미완성 표기는 닫히면 적용됨)
          scrollDown();
        } else if (ev.type === "done") {
          threadId = ev.thread_id || threadId;
          if (ev.intent) renderBadge(container, ev.intent);
          bubble.classList.remove("streaming");
          renderFinal(bubble, ev.reply || acc || "", ev.sources || []); // 답변 + 근거 토글(클릭 시 원문 하이라이트)
          finalized = true;
          scrollDown();
        } else if (ev.type === "error") {
          throw new Error(ev.error || "스트리밍 오류");
        }
      }
    }
    if (!finalized) { // done 없이 끊긴 경우 — 모은 토큰으로 마무리
      bubble.classList.remove("streaming");
      renderFinal(bubble, acc || "_(빈 응답)_", []);
    }
  } catch (err) {
    bubble.classList.remove("streaming");
    bubble.innerHTML = miniMarkdown(
      `⚠️ 백엔드 호출 실패: ${String(err)}\n\n백엔드가 실행 중인지 확인하세요.`
    );
  } finally {
    sendBtn.disabled = false;
    promptEl.focus();
  }
});

/* ===== 대화 재시작 ===== */
$("#reset-btn").addEventListener("click", async () => {
  try { await fetch("/api/v1/documents", { method: "DELETE" }); }
  catch (_) {}
  threadId = null;
  attachments = [];
  chatDocs = {};
  messagesEl.innerHTML = "";
  $(".chat-main").classList.add("welcome"); // 다시 첫 화면(가운데 입력창)으로
  renderAttachments();
});

/* ===== 근거 PDF 모달 닫기 (X · 배경 클릭 · Esc) ===== */
$("#pdf-modal").addEventListener("click", (e) => {
  if (e.target.hasAttribute("data-close")) closePdfModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#pdf-modal").hidden) closePdfModal();
});

/* ===== 초기화 ===== */
refreshTemplateSelect();
renderAttachments(); // greeting 포함
