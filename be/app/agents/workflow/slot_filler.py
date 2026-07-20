"""Slot filler: 템플릿 항목 1개를 채운다 (RAG 검색 → 작성).

fill_dispatch가 Send로 slot마다 이 노드를 병렬로 띄운다.
입력 state(=Send 페이로드): {"slot": {name, definition}, "idx": int, "documents": [...]}
출력: {"filled_slots": [채운 결과 1개]}  (operator.add 리듀서로 누적됨)
"""
import asyncio

from app.agents.prompts.fill import SLOT_FILL_SYSTEM_PROMPT
from app.agents.utils import extract_evidence
from app.core.logging import get_logger
from app.llm.client import get_llm
from app.rag.retriever import search

logger = get_logger(__name__)

_SEARCH_TOP_K = 10


def _format_context(hits: list[dict]) -> str:
    return "\n\n".join(
        f"[{i + 1}] ({h.get('doc')} · {h.get('location')})\n{h.get('text')}"
        for i, h in enumerate(hits)
    )


def _format_hint(layout: dict) -> str:
    """slot 구조(layout)에 맞춘 '출력 형식' 지시. 필드(열헤더/행라벨)는 고정, 나머지 축은 동적."""
    layout = layout or {}
    if layout.get("type") == "list":
        marker = (layout.get("fields") or ["•"])[0] or "•"
        return (
            f"\n\n[출력 형식] 이 항목은 '불릿/번호 목록'입니다. "
            f"각 항목을 `{marker} 내용` 형태의 마크다운 목록으로 출력하세요. "
            "참고 자료에 맞게 항목 개수를 필요한 만큼 늘리거나 줄이세요. "
            "제목·서론 없이 목록만 쓰세요. 예:\n"
            f"{marker} (항목 1)\n{marker} (항목 2)\n{marker} (항목 3)"
        )
    if layout.get("type") == "box":
        blanks = [b for b in (layout.get("blanks") or []) if b]
        guide = (" 안내: " + " / ".join(blanks)) if blanks else ""
        return (
            f"\n\n[출력 형식] 이 항목은 '문단 작성란'(네모 박스)입니다.{guide}\n"
            "마크다운 표(| … |)·표 헤더·구분선(|---|)을 절대 쓰지 마세요. "
            "불릿 목록도 쓰지 말고, 자연스러운 줄글로만 작성하세요. "
            "가독성을 위해 의미 단위(도입·핵심 기능·차별점 등)마다 빈 줄로 문단을 나누세요. "
            "한 덩어리로 길게 이어 쓰지 말고, 문단당 2~4문장 정도로 끊으세요. "
            "안내 문구 자체는 출력에 넣지 말고, 요구 분량·성격에 맞는 본문만 쓰세요."
        )
    if layout.get("type") != "table":
        # 텍스트 slot: 빈칸 안내문("○○○ 주식회사" 등)이 있으면 그 값만 간결히
        blanks = [b for b in (layout.get("blanks") or []) if b]
        if blanks:
            guide = " / ".join(blanks)
            return (
                f"\n\n[출력 형식] 이 자리에 들어갈 빈칸(안내 문구): {guide}\n"
                "안내 문구가 요구하는 값만, 그 안내가 가리키는 형식·분량에 맞게 채우세요. "
                "(항목이 짧으면 짧게, '…요약하여 입력'처럼 문단을 요구하면 문단으로 — 안내에 맞게.) "
                "안내 문구·라벨을 그대로 옮기지 말고, 요구되지 않은 제목·목차·다른 섹션은 만들지 말고 값만 쓰세요. "
                "마크다운 표(| … |)로 바꿔 쓰지 마세요."
            )
        return ""
    fields = [f for f in (layout.get("fields") or []) if f]
    if not fields:
        return ""
    bar = " | ".join(fields)
    orient = layout.get("orientation")
    if orient in ("col", "kv"):
        # kv(양식): 한 행에 라벨→값 쌍이 여러 개일 수 있음 → 항목마다 | 항목 | 값 | 한 행
        rows = "\n".join(f"| {f} | (값) |" for f in fields)
        kind = "항목-값 양식 표" if orient == "kv" else "세로 표"
        return (
            f"\n\n[출력 형식] 이 항목은 '{kind}'입니다. 항목 [{bar}] 은 고정입니다. "
            "각 항목을 마크다운 표의 첫 열에 그대로 두고, 값은 오른쪽 열에 채우세요. "
            "항목 이름을 바꾸거나 빼거나 새로 만들지 마세요"
            + (" (한 행에 항목이 두 개 있어도 각각 별도 행으로 출력)." if orient == "kv" else
               " (데이터 계열이 여러 개면 열을 더 추가).")
            + f" 예:\n| 항목 | 값 |\n| --- | --- |\n{rows}"
        )
    sep = " | ".join(["---"] * len(fields))
    expand = (
        "템플릿에 예시 행이 1개만 있어도, 참고 자료에 있는 건수(예: 프로젝트 3건)만큼 "
        "데이터 행을 모두 만드세요. 예시 행 개수에 맞추어 1행만 쓰지 마세요. "
        if layout.get("repeatable", True) and orient not in ("col", "kv")
        else "행(데이터)은 참고 자료 내용에 맞게 필요한 만큼 만드세요. "
    )
    return (
        f"\n\n[출력 형식] 이 항목은 '표'입니다. 열은 [{bar}] 로 고정입니다. "
        "열 이름·개수를 바꾸거나 새로 만들지 말고, 아래 마크다운 표 형식으로 출력하세요:\n"
        f"| {bar} |\n| {sep} |\n| (값) | ... |\n"
        f"{expand}값이 없는 칸은 비워 두세요."
    )


async def slot_filler_node(state: dict) -> dict:
    slot = state.get("slot") or {}
    idx = state.get("idx", 0)
    documents = state.get("documents") or []
    name = slot.get("name", "")
    definition = slot.get("definition", "")

    # 제목·항목 라벨 등 채울 칸이 없으면 LLM/RAG 생략
    # - needs_fill=False (프론트 판정) 또는 regions=[] (detect_regions: 채울 자리 없음)
    regions = slot.get("regions")
    skip = (not slot.get("needs_fill", True)) or (isinstance(regions, list) and len(regions) == 0)
    if skip:
        logger.info("slot_filler: %r → skipped (needs_fill=%s regions=%s)",
                    name[:30], slot.get("needs_fill", True),
                    "[]" if isinstance(regions, list) and len(regions) == 0 else type(regions).__name__)
        return {
            "filled_slots": [
                {"idx": idx, "name": name, "definition": definition,
                 "content": "", "sources": [], "evidence": [], "skipped": True}
            ]
        }

    layout = slot.get("layout") or {}
    hint = _format_hint(layout)  # 표면 열 고정 형식 지시

    # RAG 검색 (블로킹 → 스레드로 빼서 slot들끼리 병렬 유지)
    query = f"{name} {definition}".strip()
    hits = await asyncio.to_thread(search, query, _SEARCH_TOP_K, documents or None)

    evidence: list[dict] = []
    if not hits:
        content = "(관련 내용을 문서에서 찾지 못했습니다)"
    else:
        context = _format_context(hits)
        llm = get_llm(temperature=0.2)
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": SLOT_FILL_SYSTEM_PROMPT},
                {"role": "user", "content": f"항목: {name}\n채울 내용(가이드): {definition}{hint}\n\n참고 자료:\n{context}"},
            ]
        )
        content = resp.content
        # 채우기 성공한 경우만 근거 문장 추출 ("못 찾음"이면 인용할 근거가 없으므로 건너뜀)
        if "찾지 못했" not in content:
            evidence = await extract_evidence(content, context, hits)

    logger.info("slot_filler: %r → hits=%d", name[:30], len(hits))
    return {
        "filled_slots": [
            {"idx": idx, "name": name, "definition": definition,
             "content": content, "sources": hits, "evidence": evidence, "skipped": False}
        ]
    }
