"""포맷 → 공통 구조 파서 라우팅.

새 포맷(txt/md 등) 추가는 여기서 끝난다:
  1) 이 폴더에 파서 파일을 만들고 (bytes → 공통 구조 dict 반환)
  2) 아래 _PARSERS 에 확장자를 등록

빈칸 감지(blanks)·논리 블록 묶음(segment)은 포맷과 무관하므로 건드릴 필요 없다.
"""
from app.templates.parsers.docx import parse_structure as _parse_docx

# 확장자(소문자) → (bytes -> 공통 구조 dict)
_PARSERS = {
    "docx": _parse_docx,
}


def supported_formats() -> list[str]:
    """현재 파싱 가능한 확장자 목록."""
    return list(_PARSERS)


def parse_template(filename: str, data: bytes) -> dict:
    """파일명의 확장자로 파서를 골라 공통 구조를 만든다.

    미지원 형식이면 ValueError (호출부에서 400으로 변환).
    """
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    parser = _PARSERS.get(ext)
    if parser is None:
        raise ValueError(
            f"지원하지 않는 템플릿 형식입니다: .{ext or '?'} "
            f"(지원: {', '.join(supported_formats())})"
        )
    return parser(data)
