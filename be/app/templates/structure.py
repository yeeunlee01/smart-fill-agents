"""공통 템플릿 구조 스키마 + 개요 렌더 (포맷 무관).

모든 포맷 파서(parsers/*)는 이 공통 구조를 생성한다:

    {"elements": [ ... ]}   # top-level 요소들, 문서 읽기 순서

요소:
    문단/제목: {id, kind: paragraph|heading, style, text, empty,
                fillable, fill_mode, label, anchor}
    표:        {id, kind: table, rows, cols, cells:[{kind:cell, text, empty,
                fillable, fill_mode, label, anchor}], anchor}

- anchor: 나중에 그 자리에 정확히 내용을 주입(in-place fill)하기 위한 '포맷별' 좌표.
- 빈칸 감지(fillable/fill_mode/label)는 blanks.classify_blank 가 채운다.
- segment.segment_structure 가 이 구조를 받아 논리 블록(slot)으로 묶는다.
"""


def render_outline(structure: dict) -> str:
    """구조를 LLM이 읽기 좋은 '번호 매긴 개요'로. (구간 분할 입력용)

    모든 top-level 요소를 [id]와 '원문 텍스트 그대로' 나열한다.
    LLM은 이 id들을 의미 단위로 묶기만 하고, 텍스트는 생성/변형하지 않는다.
    """
    lines: list[str] = []
    for el in structure["elements"]:
        if el["kind"] == "table":
            lines.append(f"[{el['id']}] 표 ({el['rows']}x{el['cols']})")
            for r in range(el["rows"]):
                row = el["cells"][r * el["cols"]:(r + 1) * el["cols"]]
                # 가로 병합으로 반복된 슬롯은 개요에서 숨김 (실제 논리 셀만)
                cells = " | ".join(
                    (c["text"].strip() or "∅") for c in row if not c.get("merged_skip")
                )
                lines.append(f"    | {cells} |")
        else:
            kind_kr = "제목" if el["kind"] == "heading" else "문단"
            body = el["text"].strip() or "(빈 줄)"
            lines.append(f"[{el['id']}] {kind_kr}: {body}")
    return "\n".join(lines)
