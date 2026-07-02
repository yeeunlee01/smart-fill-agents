"""공통 구조 → 의미 단위 구간(segment=slot) 분할 (LLM). 포맷 무관.

구조(structure) → 개요 텍스트 → LLM → 구간 묶음.
LLM은 '요소 id를 묶기만' 하고 텍스트는 생성하지 않는다. → 원문 100% 보존.
각 구간은 나중에 채우기(fill) 단위가 되며, 포함된 요소의 anchor로 그 자리에 주입한다.
"""
from pydantic import BaseModel, Field

from app.agents.prompts.templates import SEGMENT_SYSTEM_PROMPT
from app.llm.client import get_llm
from app.templates.structure import render_outline


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
