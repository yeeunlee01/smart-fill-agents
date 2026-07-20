"""표 레이아웃 감지: row / col 레코드 표 vs 항목-값(kv) 양식 표.

양식 표는 한 행에 라벨→값 쌍이 1~2개 있을 수 있다.
예: | 제안서 제출 마감일 | ∅ | 사업 기간 | ∅ |
"""
from __future__ import annotations

import re


def normalize_label(s: str) -> str:
    """라벨 매칭용: 공백·전각 차이 무시."""
    return re.sub(r"\s+", "", (s or "").strip())


def is_text_box_table(cells: list[dict], rows: int, cols: int) -> bool:
    """Word '네모 작성란'처럼 논리 셀이 1개인 표인지 (1x1 또는 병합으로 한 칸).

    실제 데이터 표(헤더+여러 칸)와 구분한다.
    """
    if rows != 1 or cols < 1 or not cells:
        return False
    logical = [c for c in cells[:cols] if not c.get("merged_skip")]
    return len(logical) == 1


def text_box_guide(cells: list[dict], cols: int) -> str:
    """작성란 안내 문구(있으면)."""
    for c in range(cols):
        cell = cells[c]
        if cell.get("merged_skip"):
            continue
        return (cell.get("text") or "").strip().replace("\n", " ")
    return ""


def extract_kv_pairs(cells: list[dict], rows: int, cols: int) -> list[dict]:
    """라벨(비fillable+텍스트) → 바로 오른쪽 fillable 값 셀 쌍을 추출.

    반환: [{"label", "r", "c", "fill_mode"}, ...]  (c = 값 셀 열)
    """
    pairs: list[dict] = []
    for r in range(rows):
        c = 0
        while c < cols:
            cell = cells[r * cols + c]
            if cell.get("merged_skip"):
                c += 1
                continue
            label = (cell.get("text") or "").strip().replace("\n", " ")
            if not cell.get("fillable") and label:
                nc = c + 1
                while nc < cols and cells[r * cols + nc].get("merged_skip"):
                    nc += 1
                if nc < cols and cells[r * cols + nc].get("fillable"):
                    val = cells[r * cols + nc]
                    pairs.append({
                        "label": label,
                        "r": r,
                        "c": nc,
                        "fill_mode": val.get("fill_mode") or "replace",
                    })
                    c = nc + 1
                    continue
            c += 1
    return pairs


def is_kv_form(cells: list[dict], rows: int, cols: int, pairs: list[dict] | None = None) -> bool:
    """양식(항목-값) 표인지. 대부분 fillable이 라벨 오른쪽 쌍으로 설명되면 True.

    헤더+데이터 레코드 표(수행실적·투입인력 등)는 쌍으로 커버되지 않아 False.
    """
    pairs = pairs if pairs is not None else extract_kv_pairs(cells, rows, cols)
    if len(pairs) < 2:
        return False
    fillable_n = sum(
        1 for cell in cells if cell.get("fillable") and not cell.get("merged_skip")
    )
    if fillable_n == 0:
        return False
    # 쌍이 fillable의 대부분을 커버 (레코드 표는 행마다 fillable이 많아 실패)
    if len(pairs) < fillable_n * 0.8:
        return False
    labeled_rows = {p["r"] for p in pairs}
    return len(labeled_rows) >= max(1, (rows + 1) // 2)


def _axis_fill(cells: list[dict], rows: int, cols: int) -> tuple[int, int]:
    """행/열별 최대 fillable 수 (병합 중복 셀 제외)."""
    row_fill = 0
    for r in range(rows):
        n = sum(
            1 for c in range(cols)
            if cells[r * cols + c].get("fillable") and not cells[r * cols + c].get("merged_skip")
        )
        row_fill = max(row_fill, n)
    col_fill = 0
    for c in range(cols):
        n = sum(
            1 for r in range(rows)
            if cells[r * cols + c].get("fillable") and not cells[r * cols + c].get("merged_skip")
        )
        col_fill = max(col_fill, n)
    return row_fill, col_fill


def orientation(cells: list[dict], rows: int, cols: int) -> str:
    """표 채움 방향: 'kv'(양식) | 'row'(아래로) | 'col'(오른쪽)."""
    pairs = extract_kv_pairs(cells, rows, cols)
    if is_kv_form(cells, rows, cols, pairs):
        return "kv"
    row_fill, col_fill = _axis_fill(cells, rows, cols)
    return "row" if row_fill >= col_fill else "col"


def table_fields(cells: list[dict], rows: int, cols: int, axis: str | None = None) -> list[str]:
    """채우기 힌트용 고정 필드명 목록."""
    axis = axis or orientation(cells, rows, cols)
    if axis == "kv":
        return [p["label"] for p in extract_kv_pairs(cells, rows, cols)]
    if axis == "row":
        headers = [
            (cells[c].get("text") or "").strip().replace("\n", " ")
            for c in range(cols)
            if not cells[c].get("merged_skip")
        ]
    else:
        headers = [
            (cells[r * cols].get("text") or "").strip().replace("\n", " ")
            for r in range(rows)
        ]
    return [h for h in headers if h]
