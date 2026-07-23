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

// 아주 가벼운 마크다운 → HTML (굵게/코드/제목/구분선/불릿/문단/표)
// 빈 줄 = 문단 구분(마크다운과 동일). 연속 비어있지 않은 줄은 한 문단으로 이음.
function miniMarkdown(src) {
  const lines = escapeHtml(src).split("\n");
  let html = "";
  let inList = false;
  let paraBuf = [];
  const inline = (t) =>
    t
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  const closeList = () => {
    if (inList) { html += "</ul>"; inList = false; }
  };
  const flushPara = () => {
    if (!paraBuf.length) return;
    closeList();
    html += `<p>${inline(paraBuf.join(" "))}</p>`;
    paraBuf = [];
  };
  const isSep = (s) => s.includes("|") && /-/.test(s) && /^[\s:|-]+$/.test(s); // 표 구분행
  const cells = (s) => s.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    // 표: 헤더행 + |---|---| 구분행 + 본문행들
    if (line.includes("|") && i + 1 < lines.length && isSep(lines[i + 1].trim())) {
      flushPara();
      closeList();
      const head = cells(line);
      let t = "<table><thead><tr>" + head.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
      i += 2;
      for (; i < lines.length && lines[i].trim().includes("|"); i++) {
        const row = cells(lines[i].trim());
        t += "<tr>" + row.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
      }
      i--; // for 루프가 ++ 하므로 되돌림
      html += t + "</tbody></table>";
      continue;
    }
    if (line === "") { flushPara(); closeList(); continue; } // 빈 줄 → 문단 경계
    if (/^---+$/.test(line)) { flushPara(); closeList(); html += "<hr>"; continue; }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) {
      flushPara();
      closeList();
      html += `<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`;
      continue;
    }
    // 템플릿/LLM이 쓰는 • · 1. 등도 목록으로 (이전이면 줄마다 <p>라서 떨어져 보였음)
    const li = line.match(/^([-*•·○●◦▪▸►]|\d+[.)]|[①-⑳])\s+(.*)$/);
    if (li) {
      flushPara();
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(li[2])}</li>`;
      continue;
    }
    paraBuf.push(line);
  }
  flushPara();
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

// 최종 답변 렌더.
//  - TemplateFill(filled 있음) → 항목별 카드
//  - 구조화 sources 있음 → 클릭 가능한 근거 토글
//  - 그 외 → 마크다운 폴백
function renderFinal(bubble, text, sources, filled, tpl) {
  if (filled && filled.length) {
    renderFillResult(bubble, filled, tpl);
    return;
  }
  if (!sources || !sources.length) {
    bubble.innerHTML = renderReply(text);
    return;
  }
  const m = text.match(SOURCES_MARK);
  const answer = m ? text.slice(0, m.index) : text; // 본문에 붙은 마크다운 근거는 떼고
  bubble.innerHTML = miniMarkdown(answer);
  bubble.appendChild(buildSourcesToggle(sources)); // 구조화 근거로 새로 그림
}

let lastFilled = null; // 최근 채우기 결과(편집 반영본) — 나중 다운로드/미리보기가 이어받음

function _normLabel(s) {
  return (s || "").replace(/\s+/g, "").trim();
}

// 표에서 라벨→값 쌍 추출 (백엔드 extract_kv_pairs와 동일). {label, r, labelC, valueC, fill_mode, hint}
function extractKvPairsFromTable(tbl) {
  if (!tbl || !tbl.cols || !tbl.rows) return [];
  const cell = (r, c) => tbl.cells[r * tbl.cols + c] || {};
  const pairs = [];
  for (let r = 0; r < tbl.rows; r++) {
    for (let c = 0; c < tbl.cols; ) {
      const cur = cell(r, c);
      if (cur.merged_skip) { c++; continue; }
      const label = ((cur.text) || "").replace(/\s+/g, " ").trim();
      if (!cur.fillable && label) {
        let nc = c + 1;
        while (nc < tbl.cols && cell(r, nc).merged_skip) nc++;
        const val = cell(r, nc);
        if (nc < tbl.cols && val.fillable && !val.merged_skip) {
          pairs.push({
            label,
            r,
            labelC: c,
            valueC: nc,
            fill_mode: val.fill_mode || "replace",
            hint: ((val.text) || "").replace(/\s+/g, " ").trim(),
          });
          c = nc + 1;
          continue;
        }
      }
      c++;
    }
  }
  return pairs;
}

function slotTable(tpl, slot) {
  const byId = new Map((tpl.structure && tpl.structure.elements || []).map((e) => [e.id, e]));
  const els = (slot.element_ids || []).map((i) => byId.get(i)).filter(Boolean);
  return els.find((e) => e.kind === "table") || null;
}

// 수동 채움 on 시 붙일 최소 region (detect 결과가 비어 있을 때)
function defaultFillRegion(slot, tpl) {
  const probe = tpl || { structure: currentStructure };
  const hasTable = !!slotTable(probe, slot);
  return {
    label: ((slot.name || "").trim()) || (hasTable ? "표" : "값"),
    kind: hasTable ? "table_records" : "value",
    repeatable: false,
    fixed: [],
    guide: (slot.definition || "").trim(),
  };
}

// 템플릿 편집기에서 slot 채움 on/off. regions·needs_fill을 맞춰 저장한다.
function setSlotFillEnabled(slot, enabled, tpl) {
  slot.fill_manual = true;
  slot.needs_fill = !!enabled;
  if (enabled) {
    if (!Array.isArray(slot.regions) || slot.regions.length === 0) {
      slot.regions = [defaultFillRegion(slot, tpl)];
    }
  } else {
    slot.regions = [];
  }
}

// slot을 LLM으로 채울지.
// - fill_manual: 편집기 토글로 수동 지정한 needs_fill 우선
// - regions: []  → 스킵 / regions: […] → 채움
// - regions 없음 → structure의 실질 fillable로 판정
function slotNeedsFill(tpl, slot) {
  if (slot && slot.fill_manual && typeof slot.needs_fill === "boolean") {
    return slot.needs_fill;
  }
  if (Array.isArray(slot.regions) && slot.regions.length === 0) return false;
  if (Array.isArray(slot.regions) && slot.regions.length > 0) return true;

  if (!tpl || !tpl.structure) return true;
  const byId = new Map((tpl.structure.elements || []).map((e) => [e.id, e]));
  const els = (slot.element_ids || []).map((i) => byId.get(i)).filter(Boolean);
  for (const el of els) {
    if (el.kind === "table") {
      if ((el.cells || []).some((c) => c.fillable && !c.merged_skip)) return true;
    } else if (el.fillable) {
      // 여백용 빈 문단만으로는 채움 대상으로 보지 않음. 불릿 틀·라벨: 은 채움.
      if (el.fill_mode === "list_item" || el.fill_mode === "append") return true;
      const t = (el.text || "").trim();
      if (t) return true;
    }
  }
  return false;
}

// LLM이 낸 | 항목 | 값 | 마크다운 → {정규화라벨: 값}
function parseKvValues(content) {
  const map = {};
  for (const raw of (content || "").split("\n")) {
    const line = raw.trim();
    if (!line.includes("|")) continue;
    if (/^[\s:|-]+$/.test(line) && line.includes("-")) continue; // 구분행
    const cells = line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|").map((c) => c.trim());
    if (cells.length < 2 || !cells[1]) continue;
    const key = _normLabel(cells[0]);
    if (!key || key === "항목" || key === "값") continue;
    map[key] = cells[1];
  }
  return map;
}

// 양식(kv) 표를 원본 격자(한 행에 쌍 2개·병합 colspan)대로 HTML로 재구성
function renderKvFormHtml(tbl, content) {
  const pairs = extractKvPairsFromTable(tbl);
  const values = parseKvValues(content);
  const labelAt = new Map(pairs.map((p) => [`${p.r},${p.labelC}`, p]));
  const valueAt = new Map(pairs.map((p) => [`${p.r},${p.valueC}`, p]));

  let html = '<table class="kv-form"><tbody>';
  for (let r = 0; r < tbl.rows; r++) {
    html += "<tr>";
    for (let c = 0; c < tbl.cols; ) {
      const cur = tbl.cells[r * tbl.cols + c] || {};
      if (cur.merged_skip) { c++; continue; }
      let span = 1;
      while (c + span < tbl.cols && (tbl.cells[r * tbl.cols + c + span] || {}).merged_skip) span++;
      const key = `${r},${c}`;
      let text = "";
      let cls = "";
      if (labelAt.has(key)) {
        text = labelAt.get(key).label;
        cls = "kv-label";
      } else if (valueAt.has(key)) {
        const p = valueAt.get(key);
        const val = values[_normLabel(p.label)] || "";
        if (p.fill_mode === "prefix" && p.hint) {
          text = val ? `${val} ${p.hint}` : p.hint;
        } else {
          text = val;
        }
        cls = "kv-value";
      } else {
        text = ((cur.text) || "").replace(/\s+/g, " ").trim();
      }
      const spanAttr = span > 1 ? ` colspan="${span}"` : "";
      const clsAttr = cls ? ` class="${cls}"` : "";
      html += `<td${spanAttr}${clsAttr}>${escapeHtml(text)}</td>`;
      c += span;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  // 표에 없는 여분 항목이 있으면 아래에 보충 (LLM이 추가 필드를 낸 경우)
  const used = new Set(pairs.map((p) => _normLabel(p.label)));
  const extras = Object.entries(values).filter(([k]) => !used.has(k));
  if (extras.length) {
    html += '<table class="kv-form kv-extra"><tbody>';
    for (const [k, v] of extras) {
      html += `<tr><td class="kv-label">${escapeHtml(k)}</td><td class="kv-value">${escapeHtml(v)}</td></tr>`;
    }
    html += "</tbody></table>";
  }
  return html;
}

// 채우기 카드 표시용: kv 양식이면 원본 표 형태로, 아니면 마크다운
function formatFillDisplay(f, idx, tpl) {
  const slot = tpl && (tpl.slots || [])[idx];
  if (!slot || !tpl || !tpl.structure) return miniMarkdown(f.content || "");
  const layout = slotLayout(tpl, slot);
  if (layout.orientation !== "kv") return miniMarkdown(f.content || "");
  const tbl = slotTable(tpl, slot);
  if (!tbl || extractKvPairsFromTable(tbl).length < 2) return miniMarkdown(f.content || "");
  return renderKvFormHtml(tbl, f.content || "");
}

// slot의 문서상 형식(구조 힌트): 표 방향(행/열/kv) + 고정 필드명. → 백엔드 slot_filler의 구조 인식 생성용.
function slotLayout(tpl, slot) {
  const byId = new Map((tpl.structure && tpl.structure.elements || []).map((e) => [e.id, e]));
  const els = (slot.element_ids || []).map((i) => byId.get(i)).filter(Boolean);
  const tbl = els.find((e) => e.kind === "table");
  // Word 네모 작성란 = 논리 셀 1개인 표 → 표 출력이 아니라 줄글(box)
  if (tbl && tbl.rows === 1 && tbl.cols >= 1) {
    let logical = 0;
    let guide = "";
    for (let c = 0; c < tbl.cols; c++) {
      const cell = tbl.cells[c] || {};
      if (cell.merged_skip) continue;
      logical++;
      if (!guide) guide = ((cell.text) || "").replace(/\s+/g, " ").trim();
    }
    if (logical === 1) {
      return {
        type: "box",
        orientation: "",
        fields: [],
        blanks: guide ? [guide] : ["문단 작성란"],
        repeatable: false,
      };
    }
  }
  if (!tbl || !tbl.cols || !tbl.rows) {
    // 불릿/번호 목록 틀 → 표의 예시 행처럼 항목 수를 늘릴 수 있음
    const listEls = els.filter((e) => e.kind !== "table" && e.fill_mode === "list_item");
    const listRec = (slot.regions || []).find((r) => r && r.kind === "text_list");
    if (listEls.length || listRec) {
      const marker = (listEls[0] && listEls[0].label)
        || ((listRec && listRec.fixed && listRec.fixed[0]) || "•");
      return {
        type: "list",
        orientation: "",
        fields: [marker],
        blanks: [],
        repeatable: listRec ? !!listRec.repeatable : true,
      };
    }
    // 텍스트 slot: 채울 빈칸(placeholder 텍스트)들 → slot_filler가 그 분량·용도에 맞게 간결히 생성
    const blanks = els
      .filter((e) => e.kind !== "table" && e.fillable)
      .map((e) => (e.text || "").replace(/\s+/g, " ").trim())
      .filter((t) => t);
    return { type: "text", orientation: "", fields: [], blanks, repeatable: false };
  }

  // detect_regions가 붙인 방향·필드·repeatable이 있으면 우선 (등록 시 판단)
  const rec = (slot.regions || []).find((r) => r && r.kind === "table_records" && r.orientation);
  if (rec) {
    return {
      type: "table",
      orientation: rec.orientation,
      fields: (rec.fixed || []).filter(Boolean),
      repeatable: !!rec.repeatable,
    };
  }

  const cell = (r, c) => tbl.cells[r * tbl.cols + c] || {};
  const fillable = (r, c) => !!(cell(r, c).fillable && !cell(r, c).merged_skip);
  const text = (r, c) => ((cell(r, c).text) || "").replace(/\s+/g, " ").trim();

  const pairs = extractKvPairsFromTable(tbl);
  let fillN = 0;
  for (let r = 0; r < tbl.rows; r++) for (let c = 0; c < tbl.cols; c++) if (fillable(r, c)) fillN++;
  if (pairs.length >= 2 && fillN > 0 && pairs.length >= fillN * 0.8) {
    return { type: "table", orientation: "kv", fields: pairs.map((p) => p.label), repeatable: false };
  }

  // 방향 감지: 빈칸이 '한 행에 여러 열' vs '한 열에 여러 행' (백엔드 orientation과 동일)
  // repeatable은 regions에 없을 때만 false 기본(등록 시 detect_regions가 넣는 값을 씀)
  let rowFill = 0, colFill = 0;
  for (let r = 0; r < tbl.rows; r++) { let n = 0; for (let c = 0; c < tbl.cols; c++) if (fillable(r, c)) n++; rowFill = Math.max(rowFill, n); }
  for (let c = 0; c < tbl.cols; c++) { let n = 0; for (let r = 0; r < tbl.rows; r++) if (fillable(r, c)) n++; colFill = Math.max(colFill, n); }
  const orientation = rowFill >= colFill ? "row" : "col";
  const fields = [];
  if (orientation === "row") {
    for (let c = 0; c < tbl.cols; c++) if (!cell(0, c).merged_skip) fields.push(text(0, c));
  } else {
    for (let r = 0; r < tbl.rows; r++) fields.push(text(r, 0));
  }
  return { type: "table", orientation, fields: fields.filter(Boolean), repeatable: false };
}

// 채우기 결과 렌더. docx 템플릿이면 3열(원본 | 채운 문서 | 항목별) 나란히, 아니면 카드만.
function renderFillResult(bubble, filled, tpl) {
  const canDoc = tpl && tpl.kind === "docx" && tpl.file_b64 && tpl.structure;
  if (!canDoc) { renderFillCards(bubble, filled, tpl); return; }

  bubble.innerHTML = "";
  const bar = document.createElement("div");
  bar.className = "fill-doc-bar";
  bar.innerHTML =
    `<span class="fill-doc-title">📄 채우기 결과</span>` +
    `<button class="fill-doc-download" disabled>📥 다운로드</button>`;
  const split = document.createElement("div");
  split.className = "fill-doc-split";
  split.innerHTML =
    `<div class="fill-doc-pane"><div class="fill-doc-pane-label">원본 템플릿</div>` +
      `<div class="fill-doc-pane-body" data-pane="orig"><div class="pdf-modal-msg">불러오는 중…</div></div></div>` +
    `<div class="fill-doc-pane"><div class="fill-doc-pane-label">항목별 보기</div>` +
      `<div class="fill-doc-pane-body" data-pane="cards"></div></div>`;
  bubble.appendChild(bar);
  bubble.appendChild(split);

  const dlBtn = $(".fill-doc-download", bar);
  const origBody = $('[data-pane="orig"]', split);
  const cardsBody = $('[data-pane="cards"]', split);
  let filledDocx = null; // 채워진 docx bytes (다운로드용)

  // 항목별 보기 카드 (즉시) — kv 양식은 원본 표 형태로 표시
  renderFillCards(cardsBody, filled, tpl);
  // 원본 템플릿 (병렬)
  (async () => {
    try {
      const pdf = await _docxToPdf(base64ToBlob(tpl.file_b64, DOCX_MIME));
      origBody.innerHTML = ""; await _renderAllPages(origBody, pdf, 0, []);
    } catch (e) { origBody.innerHTML = `<div class="pdf-modal-msg">원본 로드 실패</div>`; }
  })();
  // 채워진 docx 생성 — 미리보기 열은 없애고 다운로드용 bytes만 준비
  (async () => {
    try {
      const built = await buildFilledDocx(tpl, filled);
      filledDocx = built.docxBytes; dlBtn.disabled = false;
    } catch (e) { /* 생성 실패 → 다운로드 비활성 유지 */ }
  })();

  dlBtn.addEventListener("click", () => {
    if (!filledDocx) return;
    const url = URL.createObjectURL(new Blob([filledDocx], { type: DOCX_MIME }));
    const a = document.createElement("a");
    a.href = url; a.download = (tpl.name || "채워진문서") + ".docx";
    a.click(); URL.revokeObjectURL(url);
  });
}

// docx Blob → 백엔드 /pdf 변환 → pdf.js 문서
async function _docxToPdf(blob) {
  pdfjsLib.GlobalWorkerOptions.workerSrc = "/vendor/pdf.worker.min.js";
  const fd = new FormData();
  fd.append("file", blob, "doc.docx");
  const res = await fetch("/api/v1/templates/pdf", { method: "POST", body: fd });
  if (!res.ok) throw new Error(`PDF ${res.status}`);
  return pdfjsLib.getDocument({ data: new Uint8Array(await res.arrayBuffer()) }).promise;
}

// 템플릿 docx + 채운 내용 → /fill 로 주입된 docx → PDF (다운로드용 bytes + 미리보기 pdf)
async function buildFilledDocx(tpl, filled) {
  // filled.idx ↔ tpl.slots[idx] 매핑 (스킵된 slot이 끼어도 안 꼬임)
  const slots = tpl.slots || [];
  const injections = filled.map((f, i) => {
    if (isFillSkipped(f, tpl) || isFillNotFound(f) || !(f.content || "").trim()) return null;
    const s = slots[f.idx != null ? f.idx : i];
    if (!s) return null;
    const inj = { element_ids: s.element_ids || [], content: f.content || "" };
    // 표/목록: 등록 시 regions.repeatable (detect_regions) 따름
    const rec = (s.regions || []).find((r) => r.kind === "table_records" || r.kind === "text_list");
    if (rec) inj.repeatable = !!rec.repeatable;
    else if (s.layout && s.layout.type === "list") inj.repeatable = s.layout.repeatable !== false;
    return inj;
  }).filter((inj) => inj && inj.element_ids.length);

  const fd = new FormData();
  fd.append("file", base64ToBlob(tpl.file_b64, DOCX_MIME), tpl.file_name || "template.docx");
  fd.append("injections", JSON.stringify(injections));
  const res = await fetch("/api/v1/templates/fill", { method: "POST", body: fd });
  if (!res.ok) throw new Error(`주입 ${res.status}`);
  const docxBytes = new Uint8Array(await res.arrayBuffer());
  const pdf = await _docxToPdf(new Blob([docxBytes], { type: DOCX_MIME }));
  return { docxBytes, pdf };
}

// 채울 필요 없는 slot(regions:[], needs_fill=false, skipped) — 오류가 아님
function isFillSkipped(f, tpl) {
  if (f && f.skipped) return true;
  if (!f || !tpl) return false;
  const s = (tpl.slots || [])[f.idx != null ? f.idx : -1];
  if (!s) return false;
  return !slotNeedsFill(tpl, s);
}

// 진짜 검색/생성 실패만 경고. 빈 내용·스킵은 여기 포함하지 않음.
function isFillNotFound(f) {
  return /찾지 못했|찾을 수 없/.test((f && f.content) || "");
}

// 채우기 결과를 항목별 카드로. 내용은 마크다운 렌더(표/목록), '편집'으로 원문 수정, 항목별 근거, 못 채운 항목 강조.
// kv 양식 표는 LLM의 | 항목 | 값 | 을 원본 격자(한 행 두 쌍 등)로 재구성해 보여준다. 편집은 원문 유지.
// 스킵 slot도 목록에 포함하되, 경고 없이 "(채움 생략)"만 표시.
function renderFillCards(bubble, filled, tpl) {
  const items = [...(filled || [])].sort((a, b) => (a.idx ?? 0) - (b.idx ?? 0));
  lastFilled = filled;
  bubble.innerHTML = "";
  items.forEach((f, i) => {
    const slotIdx = f.idx != null ? f.idx : i;
    const skipped = isFillSkipped(f, tpl);
    const notFound = !skipped && isFillNotFound(f);
    const card = document.createElement("div");
    card.className = "fill-card" + (notFound ? " not-found" : "") + (skipped ? " fill-skipped" : "");

    const head = document.createElement("div");
    head.className = "fill-head";
    head.innerHTML = `<span class="fill-title">${notFound ? "⚠️ " : ""}${i + 1}. ${escapeHtml(f.name || "")}</span>`;
    card.appendChild(head);

    const body = document.createElement("div");
    body.className = "fill-body doc-html";
    card.appendChild(body);

    const showView = () => {
      if (skipped) {
        body.innerHTML = "<p>(채움 생략)</p>";
      } else if (notFound) {
        // 표 재구성 하지 말고 실패 문구 그대로 표시
        body.innerHTML = miniMarkdown(f.content || "(관련 내용을 문서에서 찾지 못했습니다)");
      } else {
        body.innerHTML = formatFillDisplay(f, slotIdx, tpl);
      }
    };
    // 스킵·못찾음은 편집 불필요 (스킵은 원문 고정, 못찾음은 내용 없음)
    if (!notFound && !skipped) {
      const editBtn = document.createElement("button");
      editBtn.className = "fill-edit";
      editBtn.textContent = "✏️ 편집";
      let editing = false;
      editBtn.addEventListener("click", () => {
        editing = !editing;
        if (editing) {
          const ta = document.createElement("textarea");
          ta.className = "fill-edit-area";
          ta.value = f.content || "";
          body.innerHTML = "";
          body.appendChild(ta);
          ta.style.height = Math.min(ta.scrollHeight + 4, 400) + "px";
          ta.focus();
          editBtn.textContent = "✓ 완료";
        } else {
          const ta = $(".fill-edit-area", body);
          if (ta) f.content = ta.value; // 편집값 보관
          showView();
          editBtn.textContent = "✏️ 편집";
        }
      });
      head.appendChild(editBtn);
    }
    showView();

    if (!skipped && f.sources && f.sources.length) card.appendChild(buildSourcesToggle(f.sources));
    bubble.appendChild(card);
  });

  // 전체 복사
  const bar = document.createElement("div");
  bar.className = "fill-actions";
  const copyBtn = document.createElement("button");
  copyBtn.className = "fill-copy";
  copyBtn.textContent = "📋 전체 복사";
  copyBtn.addEventListener("click", () => {
    const text = items.map((f) => {
      const body = isFillSkipped(f, tpl) ? "(채움 생략)" : (f.content || "");
      return `${f.name}\n${body}`;
    }).join("\n\n");
    navigator.clipboard.writeText(text).then(() => {
      copyBtn.textContent = "✓ 복사됨";
      setTimeout(() => { copyBtn.textContent = "📋 전체 복사"; }, 1500);
    });
  });
  bar.appendChild(copyBtn);
  bubble.appendChild(bar);
}

// 주입 스킵용: 비었거나 못 찾음 메시지. (UI 경고는 isFillNotFound 사용 — 빈 스킵과 구분)
function _isEmptyFill(content) {
  return !content || /찾지 못했|찾을 수 없/.test(content);
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
  _evCtx = null;
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
let _evCtx = null; // 현재 근거 창 렌더 컨텍스트 (창 크기 조절 시 다시 렌더용)
async function renderEvidence(container, pdf, page, texts) {
  let focus = page ? Math.min(Math.max(page, 1), pdf.numPages) : null;
  if (focus === null) focus = (await _findPageWithText(pdf, texts)) || 1;
  _evCtx = { container, pdf, focus, texts, w: container.clientWidth || 0 };
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
  const mark = (from, to) => {
    // 매칭 구간이 걸친 '첫 item ~ 끝 item' 사이의 모든 item을 칠한다.
    // (③·구두점처럼 SIG 문자가 없어 owner에 안 잡히는 중간 item도 포함 → 문장 중간 특수기호도 하이라이트)
    const a = owner[from], b = owner[to - 1];
    for (let ii = a; ii <= b; ii++) {
      if (!seen.has(ii)) { seen.add(ii); rects.push(_itemRect(items[ii], viewport)); }
    }
  };
  (texts || []).forEach((raw) => {
    const needle = _sigChars(raw);
    if (needle.length < 4) return;
    // 1) 문장 전체가 연속으로 맞으면 그대로 (PDF처럼 추출이 거의 같을 때)
    const whole = compact.indexOf(needle);
    if (whole >= 0) { mark(whole, whole + needle.length); return; }
    // 2) 전체가 안 맞으면(추출 엔진 차이로 일부 어긋남) 겹치는 창으로 쪼개 '맞는 부분'만 하이라이트
    const W = 14, STEP = 7;
    let any = false;
    for (let p = 0; p + W <= needle.length; p += STEP) {
      const si = compact.indexOf(needle.slice(p, p + W));
      if (si >= 0) { mark(si, si + W); any = true; }
    }
    // 3) 창도 안 맞고 짧은 문장이면 앞부분만이라도
    if (!any && needle.length >= 8) {
      const si = compact.indexOf(needle.slice(0, 8));
      if (si >= 0) mark(si, si + 8);
    }
  });
  return _mergeRects(rects); // 같은 줄 인접 조각을 하나로 병합 → 띄어쓰기까지 매끈하게
}

// 매칭된 박스들을 '같은 줄'끼리 하나의 연속 사각형으로 병합.
// 같은 줄이면 간격과 무관하게 처음~끝을 한 바로 이어붙여, 문장 중간의 기호(③)·구두점·공백에
// 텍스트 item이 없거나 순서가 어긋나도 빈틈 없이 칠해지게 한다.
function _mergeRects(rects) {
  const sorted = rects.slice().sort((a, b) => (a.y - b.y) || (a.x - b.x));
  const out = [];
  let cur = null;
  for (const r of sorted) {
    const sameLine = cur && Math.abs(r.y - cur.y) <= cur.h * 0.6;
    if (cur && sameLine) {
      const right = Math.max(cur.x + cur.w, r.x + r.w);
      cur.x = Math.min(cur.x, r.x);
      cur.w = right - cur.x;
      cur.y = Math.min(cur.y, r.y);
      cur.h = Math.max(cur.h, r.h);
    } else {
      cur = { ...r };
      out.push(cur);
    }
  }
  return out;
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
 *  템플릿 저장소 (백엔드 API — Postgres 메타 + MinIO 원본 파일)
 *  서버가 영구 저장을 담당하고, 프론트는 메모리 캐시(_tplCache)로 동기 접근을 유지.
 *  과거 localStorage(sfa_templates) 데이터는 최초 접속 시 1회 서버로 자동 이전.
 * ==================================================================== */
const TPL_KEY = "sfa_templates"; // 구버전 localStorage 마이그레이션용
const TPL_API = "/api/v1/templates";
let _tplCache = [];

function loadTemplates() { return _tplCache; }
function getTemplate(name) { return _tplCache.find((t) => t.name === name) || null; }

async function _apiSaveTemplate(tpl) {
  const res = await fetch(TPL_API, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: tpl.name,
      kind: tpl.kind || "text",
      file_name: tpl.file_name || "",
      file_b64: tpl.file_b64 || "",
      text: tpl.text || tpl.raw_text || "",
      structure: tpl.structure || null,
      slots: tpl.slots || [],
    }),
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
}

// 캐시를 즉시 갱신해 UI는 바로 반영하고, 서버 저장은 백그라운드로 (실패 시 알림)
function upsertTemplate(tpl) {
  const i = _tplCache.findIndex((t) => t.name === tpl.name);
  if (i >= 0) _tplCache[i] = tpl; else _tplCache.push(tpl);
  _apiSaveTemplate(tpl).catch((e) => alert(`템플릿 서버 저장 실패: ${e.message || e}`));
}

function deleteTemplate(name) {
  _tplCache = _tplCache.filter((t) => t.name !== name);
  fetch(`${TPL_API}?name=${encodeURIComponent(name)}`, { method: "DELETE" })
    .then((res) => { if (!res.ok && res.status !== 404) throw new Error(`HTTP ${res.status}`); })
    .catch((e) => alert(`템플릿 서버 삭제 실패: ${e.message || e}`));
}

async function initTemplates() {
  try {
    const res = await fetch(TPL_API);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    _tplCache = await res.json();
  } catch (e) {
    console.error("템플릿 목록 로드 실패:", e);
    return;
  }
  // 구버전 localStorage 데이터 1회 이전 (서버에 없는 이름만) → 완료 후 제거
  try {
    const raw = localStorage.getItem(TPL_KEY);
    if (raw) {
      const old = JSON.parse(raw);
      const names = new Set(_tplCache.map((t) => t.name));
      for (const t of Array.isArray(old) ? old : []) {
        if (!t || !t.name || names.has(t.name)) continue;
        await _apiSaveTemplate(t);
        _tplCache.push(t);
      }
      localStorage.removeItem(TPL_KEY);
    }
  } catch (e) {
    console.error("localStorage 템플릿 이전 실패 (다음 접속 시 재시도):", e);
  }
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
      ? t.slots.map((s, i) =>
          `<div class="slot-item"><strong>${i + 1}. ${escapeHtml(s.name)}</strong><br>: ${escapeHtml(s.definition || "")}</div>`
        ).join("")
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
          if (c.merged_skip) return; // 가로 병합 중복 슬롯은 미리보기에서 숨김
          const txt = (c.text || "").trim();
          if (c.fillable) {
            const hint = txt ? `${escapeHtml(txt)} ` : "";
            t += `<td class="empty-cell">${hint}<span class="sf-blank">빈칸</span></td>`;
          } else {
            t += `<td>${escapeHtml(txt)}</td>`;
          }
        });
        t += "</tr>";
      }
      return t + "</tbody></table>";
    }
    if (el.kind === "heading") return `<h4>${escapeHtml(el.text || "")}</h4>`;
    if (el.fillable && el.fill_mode === "append") {
      return `<p><strong>${escapeHtml(el.label)}:</strong> <span class="sf-blank">채울 값</span></p>`;
    }
    if (el.fillable && el.fill_mode === "list_item") {
      const marker = escapeHtml(el.label || "•");
      return `<p>${marker} <span class="sf-blank">목록 항목</span></p>`;
    }
    const txt = (el.text || "").trim();
    return txt ? `<p>${escapeHtml(txt)}</p>` : `<p><span class="sf-blank">빈칸</span></p>`;
  }).join("");
}

// slot-card에 '분해' 토글을 붙인다 — 코드레벨 확인용으로 slot state를 raw JSON 그대로 덤프.
function attachRegions(card, seg) {
  if (!seg || seg.regions === undefined) return;  // 감지 정보 없는 slot(구버전)은 생략
  // 실제 state로 전달되는 값 그대로 (감지 결과 = currentSlots[i]).
  const state = {
    name: seg.name,
    definition: seg.definition,
    element_ids: seg.element_ids,
    regions: seg.regions,
  };
  const det = document.createElement("details");
  det.className = "seg-regions";
  det.innerHTML = `<summary>분해 state (JSON) · 영역 ${(seg.regions || []).length}개</summary>`
    + `<pre class="seg-regions-json"></pre>`;
  $(".seg-regions-json", det).textContent = JSON.stringify(state, null, 2);
  card.appendChild(det);
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
// loading=true면 회전 스피너를 함께 표시해 '진행 중'임을 보여준다.
function showSlotsPlaceholder(msg, loading = false) {
  const box = $("#tpl-slots");
  const spinner = loading ? '<div class="loading-spinner"></div>' : "";
  box.innerHTML = `<div class="slots-empty">${spinner}${escapeHtml(msg)}</div>`;
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

// 구간(묶음) 카드 — 번호 + 이름/설명 수정 + 채움 on/off + 삭제 + '원문 보기' 토글.
function renderSlots() {
  if (!currentSlots.length) {
    renderSlotsExample();  // 빈 상태 → 예시 카드로 "이렇게 표시돼요" 안내
    return;
  }
  $("#tpl-slots-hint").hidden = false;
  $("#tpl-save-row").hidden = false;
  const box = $("#tpl-slots");
  box.innerHTML = "";
  const tplProbe = { structure: currentStructure };
  let nFill = 0;
  currentSlots.forEach((s, i) => {
    const needs = slotNeedsFill(tplProbe, s);
    if (needs) nFill++;
    const card = document.createElement("div");
    card.className = "slot-card" + (needs ? "" : " slot-skip");
    card.innerHTML = `
      <div class="slot-num">${i + 1}.</div>
      <div class="slot-card-head">
        <input class="sname" placeholder="묶음 이름" />
        <button type="button" class="slot-fill-toggle ${needs ? "is-on" : "is-off"}"
          title="클릭하여 채움 대상/생략을 바꿉니다">${needs ? "채움 대상" : "채움 생략"}</button>
        <span class="del" title="이 묶음 삭제">🗑️</span>
      </div>
      <input class="sdef" placeholder="채울 내용 설명 (가이드)" />`;
    $(".sname", card).value = s.name || "";
    $(".sdef", card).value = s.definition || "";
    $(".sname", card).addEventListener("input", (e) => { currentSlots[i].name = e.target.value; });
    $(".sdef", card).addEventListener("input", (e) => { currentSlots[i].definition = e.target.value; });
    $(".slot-fill-toggle", card).addEventListener("click", () => {
      setSlotFillEnabled(currentSlots[i], !slotNeedsFill(tplProbe, currentSlots[i]), tplProbe);
      renderSlots();
    });
    $(".del", card).addEventListener("click", () => { currentSlots.splice(i, 1); renderSlots(); });
    attachSegPreview(card, s);  // '원문 보기' 토글 (묶인 원문을 문서 양식으로)
    attachRegions(card, s);     // '분해' 토글 (LLM 판단: 채울 영역 fixed/fill)
    box.appendChild(card);
  });

  // 총 개수 표시
  const countEl = $("#tpl-slots-count");
  if (countEl) {
    const nSkip = currentSlots.length - nFill;
    countEl.textContent = currentSlots.length
      ? `총 ${currentSlots.length}개 (채움 ${nFill}${nSkip ? ` · 생략 ${nSkip}` : ""})`
      : "";
  }
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
  viewer.innerHTML = '<div class="viewer-empty"><div class="loading-spinner"></div>‘' + escapeHtml(f.name) + '’ 분석 중…</div>';
  // 감지된 항목 영역에도 진행 안내 (미리보기가 먼저 떠도 분할이 끝나기 전까지 표시)
  $("#tpl-slots-step").hidden = false;
  showSlotsPlaceholder(`‘${f.name}’을(를) 분석 중입니다…`, true);
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
    template: tpl ? {
      name: tpl.name,
      slots: tpl.slots.map((s) => ({
        name: s.name,
        definition: s.definition || "",
        layout: slotLayout(tpl, s),
        needs_fill: slotNeedsFill(tpl, s),
        // 백엔드 이중 가드용 (regions:[] 이면 LLM 스킵)
        regions: Array.isArray(s.regions) ? s.regions : undefined,
      })),
    } : null,
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
          renderFinal(bubble, ev.reply || acc || "", ev.sources || [], ev.filled || [], tpl); // 답변/근거 or 채우기(문서/카드)
          finalized = true;
          scrollDown();
        } else if (ev.type === "error") {
          throw new Error(ev.error || "스트리밍 오류");
        }
      }
    }
    if (!finalized) { // done 없이 끊긴 경우 — 모은 토큰으로 마무리
      bubble.classList.remove("streaming");
      renderFinal(bubble, acc || "_(빈 응답)_", [], [], tpl);
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

/* ===== 근거 PDF 모달 닫기 (X · Esc) ===== */
$("#pdf-modal").addEventListener("click", (e) => {
  if (e.target.hasAttribute("data-close")) closePdfModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#pdf-modal").hidden) closePdfModal();
});

/* ===== 근거 창 드래그 이동 (헤더 잡고) ===== */
(function () {
  const panel = $(".pdf-modal-panel");
  const head = $(".pdf-modal-head");
  if (!panel || !head) return;
  let drag = false, sx = 0, sy = 0, ox = 0, oy = 0;
  head.addEventListener("mousedown", (e) => {
    if (e.target.closest(".pdf-modal-close")) return; // 닫기 버튼은 제외
    const r = panel.getBoundingClientRect();
    ox = r.left; oy = r.top; sx = e.clientX; sy = e.clientY;
    panel.style.left = ox + "px"; panel.style.top = oy + "px"; panel.style.transform = "none";
    drag = true;
    document.body.style.userSelect = "none";
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!drag) return;
    // 창이 화면 밖으로 완전히 사라지지 않게 가장자리 클램프
    const nx = Math.max(-panel.offsetWidth + 100, Math.min(ox + e.clientX - sx, window.innerWidth - 100));
    const ny = Math.max(0, Math.min(oy + e.clientY - sy, window.innerHeight - 44));
    panel.style.left = nx + "px"; panel.style.top = ny + "px";
  });
  window.addEventListener("mouseup", () => { drag = false; document.body.style.userSelect = ""; });
})();

/* ===== 근거 창 크기 조절 시 PDF를 새 폭에 맞춰 다시 렌더 ===== */
(function () {
  const body = $("#pdf-modal-body");
  if (!body || !window.ResizeObserver) return;
  let timer = null;
  new ResizeObserver(() => {
    if ($("#pdf-modal").hidden || !_evCtx) return;
    const w = body.clientWidth;
    if (Math.abs(w - _evCtx.w) < 12) return; // 미세 변화·같은 폭이면 무시
    _evCtx.w = w;
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (_evCtx) renderEvidence(_evCtx.container, _evCtx.pdf, _evCtx.focus, _evCtx.texts);
    }, 180);
  }).observe(body);
})();

/* ===== 초기화 ===== */
refreshTemplateSelect();
renderAttachments(); // greeting 포함
// 서버에서 템플릿 목록 로드 (+구버전 localStorage 1회 이전) 후 화면 갱신
initTemplates().then(() => {
  refreshTemplateSelect();
  if (!$("#tpl-library").hidden) renderLibrary();
});
