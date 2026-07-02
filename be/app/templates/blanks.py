"""빈칸 감지 규칙 (텍스트 수준, 포맷 무관).

문단/셀의 '텍스트'만 보고 채울 수 있는 빈칸인지, 어떻게 채울지 판정한다.
포맷별 파서(parsers/*)가 요소를 만들 때 이 규칙을 호출해
fillable / fill_mode / label 을 채운다. → 감지 규칙을 여기 한 곳에서만 고도화하면
모든 포맷에 동시에 반영된다.

fill_mode:
- "replace": 빈 문단 / 빈 셀      → 그 자리에 내용을 넣음
- "append":  "라벨: " (값이 빈 라벨) → 라벨 뒤에 값을 이어붙임
"""
import re

# "작성자:" / "작성일 :" 처럼 라벨만 있고 값이 비어 있는 문단 (콜론이 끝에)
_LABEL_BLANK = re.compile(r"^(.{1,30}?)\s*[:：]\s*$")


def classify_blank(text: str, *, is_heading: bool = False) -> tuple[bool, str, str]:
    """텍스트 → (fillable, fill_mode, label)."""
    stripped = text.strip()
    if not stripped:
        return True, "replace", ""  # 빈 문단 / 빈 셀
    if not is_heading:
        m = _LABEL_BLANK.match(stripped)
        if m:
            return True, "append", m.group(1).strip()  # "라벨: " (값 비어있음)
    return False, "", ""
