"""빈칸 감지 규칙 (텍스트 수준, 포맷 무관).

문단/셀의 '텍스트'만 보고 채울 수 있는 빈칸인지, 어떻게 채울지 판정한다.
포맷별 파서(parsers/*)가 요소를 만들 때 이 규칙을 호출해
fillable / fill_mode / label 을 채운다. → 감지 규칙을 여기 한 곳에서만 고도화하면
모든 포맷에 동시에 반영된다.

fill_mode:
- "replace": 빈 문단 / 빈 셀      → 그 자리에 내용을 넣음
- "append":  "라벨: " (값이 빈 라벨) → 라벨 뒤에 값을 이어붙임
- "prefix":  "원 (부가가치세 별도)" 처럼 단위/안내만 있는 셀 → 값 앞에 붙임
- "list_item": "• " / "1. " 처럼 불릿·번호만 있는 목록 자리 → 항목 반복 틀
"""
import re

# "작성자:" / "작성일 :" 처럼 라벨만 있고 값이 비어 있는 문단 (콜론이 끝에)
_LABEL_BLANK = re.compile(r"^(.{1,30}?)\s*[:：]\s*$")

# 목록 항목 마커 + 본문. 본문이 비었거나 플레이스홀더면 채울(반복 가능) 불릿으로 본다.
# "1. 사업 개요"처럼 본문이 있는 제목형 줄은 채움 대상으로 보지 않음.
_LIST_ITEM = re.compile(
    r"^(?P<marker>"
    r"[-*•·○●◦▪▸►]"
    r"|\d+[.)]"
    r"|[①-⑳]"
    r"|[가나다라마바사아자차카타파하][.)]"
    r"|[a-zA-Z][.)]"
    r")\s*(?P<body>.*)$"
)

# 안내 텍스트 플레이스홀더 패턴 (공백 제거한 텍스트에 대해 매칭):
#   "성명 입력", "...요약하여 입력", "입력하십시오", "YYYY. MM. DD.", "○○○", "____", "▶" 등
# NOTE: "예:"(예시 도입부)는 뺐다 — "(예: 처리 시간, 비용 …)" 같은 안내 문장을 자리표시로 오인해
#       그 문단 전체를 fillable로 잘못 잡던 과다감지의 주범이었음. 애매한 판단은 detect_regions(LLM) 몫.
_PLACEHOLDER = re.compile(
    r"입력하|(입력|기입|작성)$"      # ...입력 / 입력하십시오
    r"|Y{4}|M{2}\.?D{2}|D{2}\."     # 날짜 자리 YYYY / MM.DD
    r"|[○◯xX]{3,}|_{3,}|[▶►]"       # 기호형 자리표시
)

# 표 셀에만: 금액/수량 단위·부가세 안내처럼 '값 앞자리'만 비어 있는 경우
#   "원 (부가가치세 별도)", "명", "일" 등 — 본문이 긴 작성요령 셀은 길이로 제외
# NOTE: '대'/'인'/'부' 같은 한 글자는 '대표자'·'담당자' 라벨 첫 글자와 충돌하므로 쓰지 않음
_UNIT_CELL = re.compile(
    r"^원($|[(\uff08\s])"           # 원 / 원 (부가…)
    r"|^([명일건개회%])$"            # 단독 단위
    r"|부가가치세|VAT",
    re.I,
)

# 1칸짜리 작성란(네모 박스) 안의 자리 안내 — 표 데이터가 아니라 줄글 자리
# NOTE: 문서 맨 앞 '작 성 요 령 / 1. …' 같은 규칙 안내문은 제외 (작성요령: …기재 형태만)
_WRITING_GUIDE = re.compile(
    r"작성\s*요령\s*[:：]"
    r"|이내로\s*기재|요약하여\s*(입력|기재|작성)|기술하여|서술하여"
    r"|자유롭게\s*작성|이내로\s*작성"
)


def is_placeholder(text: str) -> bool:
    """안내 텍스트('성명 입력' 등)처럼 '채워질 자리'인지. (공백은 무시하고 판정)"""
    compact = re.sub(r"\s+", "", text or "")
    return bool(compact) and bool(_PLACEHOLDER.search(compact))


def classify_blank(text: str, *, is_heading: bool = False) -> tuple[bool, str, str]:
    """텍스트 → (fillable, fill_mode, label).

    list_item 일 때 label 에는 불릿/번호 마커(예: "•", "1.")를 담는다.
    """
    stripped = text.strip()
    if not stripped:
        return True, "replace", ""  # 빈 문단 / 빈 셀
    if not is_heading:
        m = _LABEL_BLANK.match(stripped)
        if m:
            return True, "append", m.group(1).strip()  # "라벨: " (값 비어있음)
        lm = _LIST_ITEM.match(stripped)
        if lm:
            body = (lm.group("body") or "").strip()
            marker = lm.group("marker")
            # 마커만 있거나 본문이 자리표시 → 목록 틀 (내용에 따라 항목 수 확장)
            if not body or is_placeholder(body):
                return True, "list_item", marker
        if is_placeholder(stripped):
            return True, "replace", ""  # 안내 텍스트 플레이스홀더 → 그 자리에 내용 주입
    return False, "", ""


def classify_cell_blank(text: str) -> tuple[bool, str, str]:
    """표 셀용 빈칸 판정. 단위/안내만 있는 셀은 prefix로 채운다."""
    fillable, mode, label = classify_blank(text)
    if fillable:
        return fillable, mode, label
    stripped = text.strip()
    compact = re.sub(r"\s+", "", stripped)
    # 공백 제거본·원문 둘 다 검사 (원문 패턴은 띄어쓰기 있는 "원 (…)" 용)
    if compact and len(compact) <= 40 and (
        _UNIT_CELL.search(stripped) or _UNIT_CELL.search(compact)
    ):
        return True, "prefix", ""
    # "(작성요령: …기재합니다.)" 같은 문단 작성란 안내 → 줄글로 교체
    if compact and _WRITING_GUIDE.search(stripped):
        return True, "replace", ""
    return False, "", ""
