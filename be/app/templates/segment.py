"""공통 구조 → 의미 단위 구간(segment=slot) 분할 (LLM). 포맷 무관.

구조(structure) → 개요 텍스트 → LLM → 구간 묶음.
LLM은 '요소 id를 묶기만' 하고 텍스트는 생성하지 않는다. → 원문 100% 보존.
각 구간은 나중에 채우기(fill) 단위가 되며, 포함된 요소의 anchor로 그 자리에 주입한다.
"""
from pydantic import BaseModel, Field

from app.agents.prompts.templates import DETECT_SYSTEM_PROMPT, SEGMENT_SYSTEM_PROMPT
from app.llm.client import get_llm
from app.templates.structure import render_outline
from app.templates.table_layout import is_text_box_table
from app.templates.table_layout import orientation as table_orientation
from app.templates.table_layout import table_fields


class _Segment(BaseModel):
    name: str = Field(description="한국어 묶음 이름 (원문 제목/항목 기반, 짧게)")
    definition: str = Field(default="", description="이 구간에 들어갈 내용 한 줄 설명 (검색·작성 가이드)")
    element_ids: list[int] = Field(description="이 구간에 속한 요소들의 [id]")


class _SegmentResult(BaseModel):
    segments: list[_Segment]


def _short(el: dict) -> str:
    if el["kind"] == "table":
        return f"표 {el['rows']}x{el['cols']}"
    return (el["text"].strip()[:20] or "빈 줄")


async def segment_structure(structure: dict) -> list[dict]:
    """구조 → LLM 구간 분할 → [{name, definition, element_ids}] (문서 순서, 전체 커버)."""
    outline = render_outline(structure)
    elems = structure["elements"]
    by_id = {el["id"]: el for el in elems}

    llm = get_llm().with_structured_output(_SegmentResult)
    result: _SegmentResult = await llm.ainvoke(
        [
            {"role": "system", "content": SEGMENT_SYSTEM_PROMPT},
            {"role": "user", "content": outline},
        ]
    )

    segments: list[dict] = []
    seen: set[int] = set()
    for s in result.segments:
        # 유효 id만, 중복 제거 (문서 순서 유지)
        ids = [i for i in s.element_ids if i in by_id and i not in seen]
        if not ids:
            continue
        seen.update(ids)
        # 불변식: 한 구간에 표는 최대 1개. 표를 만나면 그 앞의 라벨/제목 문단(buffer)과 묶어 끊는다.
        # → "결재 정보" 제목 + 결재 표 = 한 구간. 표 2개가 묶여오면 각각 자기 앞 라벨을 데려가 분리.
        buffer: list[int] = []
        for i in ids:
            if by_id[i]["kind"] == "table":
                name = s.name if buffer else _short(by_id[i])  # 라벨 없이 홀로 남은 표만 축약 이름
                segments.append({"name": name, "definition": s.definition, "element_ids": buffer + [i]})
                buffer = []
            else:
                buffer.append(i)
        if buffer:  # 표 뒤에 남은 문단들 → 한 구간
            segments.append({"name": s.name, "definition": s.definition, "element_ids": buffer})

    # 누락된 요소 처리 (문서 전체 커버 보장)
    #  - 빈 문단(간격용): 독립 항목으로 승격하지 말고 인접 구간에 조용히 흡수 → '빈 줄' 노이즈 방지.
    #    (채울 자리인 빈 문단은 LLM이 이미 어느 구간에 묶어 넣었고, 여기 남은 건 섹션 사이 여백뿐)
    #  - 내용 있는 요소/표: LLM이 실수로 빠뜨린 진짜 항목일 수 있으니 단독 구간으로 남김 (안전망)
    seg_by_id: dict[int, dict] = {i: seg for seg in segments for i in seg["element_ids"]}
    for el in elems:
        eid = el["id"]
        if eid in seen:
            continue
        is_blank_para = el["kind"] != "table" and not (el.get("text") or "").strip()
        host = None
        if is_blank_para:
            # 앞쪽에서 가장 가까운 이미 배정된 요소의 구간에 흡수 (앞이 없으면 뒤쪽)
            host = next((seg_by_id[j] for j in range(eid - 1, -1, -1) if j in seg_by_id), None) \
                or next((seg_by_id[j] for j in range(eid + 1, len(elems)) if j in seg_by_id), None)
        if host is not None:
            host["element_ids"].append(eid)
        else:  # 흡수 대상 없음(내용 요소/표, 혹은 아직 구간이 하나도 없음) → 단독 구간
            host = {"name": _short(el), "definition": "", "element_ids": [eid]}
            segments.append(host)
        seg_by_id[eid] = host
        seen.add(eid)

    # 문서에 나타난 순서대로 정렬 (id가 곧 읽기 순서) — 구간 내부/구간 간 모두
    for seg in segments:
        seg["element_ids"].sort()
    segments.sort(key=lambda s: min(s["element_ids"]))
    return segments


# ── 채울 영역 분해 (요소 안을 fixed 뼈대 / fill 자리로) ──────────────────
class _Region(BaseModel):
    label: str = Field(default="", description="이 영역의 짧은 이름 (원문 소제목/표 이름 기반)")
    kind: str = Field(default="value", description="value | fixed_struct | table_records | text_list")
    repeatable: bool = Field(default=False, description="항목 개수가 열려 있어 더 늘 수 있으면 true, 고정이면 false")
    fixed: list[str] = Field(default_factory=list, description="채우지 않는 고정 뼈대 이름들(소제목/헤더/행라벨)")
    guide: str = Field(default="", description="이 영역에 무엇을 채우는지 한 줄")


class _SegRegions(BaseModel):
    regions: list[_Region] = Field(default_factory=list)


class _DetectResult(BaseModel):
    items: list[_SegRegions] = Field(default_factory=list)


# 세그먼트의 원문 요소를 '온전히'(자르지 않고) 렌더 → LLM이 개요를 베끼는 게 아니라 실제 내용으로 판단.
def _seg_full(seg: dict, by_id: dict) -> str:
    lines: list[str] = []
    for e in seg["element_ids"]:
        el = by_id.get(e)
        if not el:
            continue
        if el["kind"] == "table":
            rows, cols, cells = el["rows"], el["cols"], el["cells"]
            lines.append(f"  표 {rows}x{cols}:")
            for r in range(rows):
                parts = []
                for c in range(cols):
                    cell = cells[r * cols + c]
                    if cell.get("merged_skip"):
                        continue  # 가로 병합 중복 슬롯은 개요에서 숨김
                    parts.append((cell.get("text") or "").strip().replace("\n", " ") or "∅")
                lines.append(f"    | {' | '.join(parts)} |")
        else:
            t = (el.get("text") or "").strip().replace("\n", " ")
            lines.append(f"  · {t}" if t else "  · (빈 줄)")
    return "\n".join(lines)


# 입력 개요의 설명용 표기를 그대로 베낀 fixed 아티팩트만 걸러내는 백스톱. (뼈대 이름 자체는 원문 보존)
_COPY_ARTIFACT = ("표 ", "· ", "∅", "(빈")


def _clean_fixed(fixed: list[str]) -> list[str]:
    return [t for f in (fixed or []) if (t := (f or "").strip()) and not t.startswith(_COPY_ARTIFACT)]


async def detect_regions(structure: dict, segments: list[dict]) -> list[dict]:
    """각 segment를 채울 영역(regions)으로 분해해 붙인다.

    LLM이 요소 안을 fixed(뼈대)/fill(채울 자리)로 나누고 kind·repeatable을 판단.
    표는 헤더·방향을 구조에서 보강한다(LLM 추측보다 정확). repeatable은 하드코딩하지 않고 LLM 판단을 존중.
    """
    by_id = {el["id"]: el for el in structure["elements"]}
    outline = "\n\n".join(f"[{i}] 세그먼트: {s['name']}\n{_seg_full(s, by_id)}"
                          for i, s in enumerate(segments))
    try:
        llm = get_llm().with_structured_output(_DetectResult)
        result: _DetectResult = await llm.ainvoke(
            [{"role": "system", "content": DETECT_SYSTEM_PROMPT}, {"role": "user", "content": outline}]
        )
        items = result.items
    except Exception:  # noqa: BLE001 — 감지 실패해도 채우기는 가능
        items = []

    for i, s in enumerate(segments):
        sr = items[i] if i < len(items) else None
        regions: list[dict] = []
        for r in (sr.regions if sr else []):
            regions.append({
                "label": (r.label or "").strip(),
                "kind": r.kind or "value",
                "repeatable": bool(r.repeatable),
                "fixed": _clean_fixed(r.fixed),
                "guide": (r.guide or "").strip(),
            })
        # 표 세그먼트: 헤더·방향은 구조에서 확정.
        # kv 양식 표는 한 행에 라벨→값 쌍이 여러 개일 수 있어 col0/row0만 보면 오른쪽 라벨이 빠짐
        tbl = next((by_id[e] for e in s["element_ids"] if e in by_id and by_id[e]["kind"] == "table"), None)
        if tbl:
            rows, cols, cells = tbl["rows"], tbl["cols"], tbl["cells"]
            has_fill = any(c.get("fillable") and not c.get("merged_skip") for c in cells)
            # 1칸 네모 작성란 → 표 레코드가 아니라 문단(value)
            if is_text_box_table(cells, rows, cols):
                regions = [x for x in regions if x.get("kind") != "table_records"]
                if has_fill:
                    guide = next(
                        ((c.get("text") or "").strip().replace("\n", " ") for c in cells if not c.get("merged_skip")),
                        "",
                    )
                    rec = next((x for x in regions if x.get("kind") == "value"), None)
                    if rec is None:
                        rec = {
                            "label": s["name"],
                            "kind": "value",
                            "repeatable": False,
                            "fixed": [],
                            "guide": guide or (s.get("definition") or "").strip(),
                        }
                        regions.insert(0, rec)
                    else:
                        rec["repeatable"] = False
                        if guide and not rec.get("guide"):
                            rec["guide"] = guide
            elif has_fill:
                axis = table_orientation(cells, rows, cols)
                headers = table_fields(cells, rows, cols, axis)
                rec = next((x for x in regions if x["kind"] == "table_records"), None)
                if rec is None:
                    rec = {"label": s["name"], "kind": "table_records", "repeatable": False, "fixed": [], "guide": ""}
                    regions.insert(0, rec)
                rec["fixed"] = headers            # 헤더/행라벨/양식 항목명은 구조가 정확
                rec["orientation"] = axis
                if axis == "kv":
                    # 양식 표만 구조로 확정(행·열 복제 대상 아님). row/col의 repeatable은 등록 시 LLM 판단 유지.
                    rec["repeatable"] = False
            else:
                # 채울 칸 없는 표(작성요령·첨부목록 등) → table_records 강제 생성하지 않음
                regions = [x for x in regions if x.get("kind") != "table_records"]
        # 불릿/번호 목록 틀(list_item): 표의 예시 행처럼 반복 가능 — 구조로 text_list 확정
        list_els = [
            by_id[e] for e in s["element_ids"]
            if e in by_id and by_id[e].get("fill_mode") == "list_item"
        ]
        if list_els:
            rec = next((x for x in regions if x.get("kind") == "text_list"), None)
            if rec is None:
                rec = {
                    "label": s["name"],
                    "kind": "text_list",
                    "repeatable": True,
                    "fixed": [],
                    "guide": (s.get("definition") or "").strip(),
                }
                regions.append(rec)
            rec["kind"] = "text_list"
            rec["repeatable"] = True
            markers = sorted({(e.get("label") or "•") for e in list_els})
            if markers:
                rec["fixed"] = markers
        s["regions"] = regions
    return segments
