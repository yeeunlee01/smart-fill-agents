"""의미 단위(문단/문장) 기반 청킹.

글자 수로 문장을 끊지 않고, 문단 → 문장 경계를 존중해 자른다.
  1) 줄바꿈으로 문단 분리
  2) 문단을 문장(. ! ? 등 종결부호 + 공백) 단위로 분리
  3) 의미 조각들을 MAX_CHARS 한도 안에서 묶어 청크 생성 (문장 중간 절단 없음)
지나치게 긴 단일 조각(표 덤프 등)만 안전장치로 글자 분할한다.
"""
import re

MAX_CHARS = 1000  # 청크 최대 길이 (이 한도 안에서 문장 단위로 묶음)

# 종결부호(., !, ?, 。) 뒤 공백, 또는 줄바꿈을 문장/문단 경계로 본다
_BOUNDARY = re.compile(r"(?<=[.!?。])\s+|\n+")


def _hard_wrap(s: str, limit: int) -> list[str]:
    """한 조각이 limit를 넘으면 어쩔 수 없이 글자 길이로 분할 (안전장치)."""
    return [s[i : i + limit] for i in range(0, len(s), limit)]


def _units(text: str, max_chars: int) -> list[str]:
    units: list[str] = []
    for part in _BOUNDARY.split(text):
        u = " ".join(part.split())  # 조각 내부 공백 정규화
        if not u:
            continue
        units.extend(_hard_wrap(u, max_chars) if len(u) > max_chars else [u])
    return units


def chunk_text(text: str, max_chars: int = MAX_CHARS) -> list[str]:
    """문장/문단 의미 단위로 묶은 청크 리스트를 반환."""
    chunks: list[str] = []
    cur = ""
    for u in _units(text, max_chars):
        if not cur:
            cur = u
        elif len(cur) + 1 + len(u) <= max_chars:
            cur = f"{cur} {u}"
        else:
            chunks.append(cur)
            cur = u
    if cur:
        chunks.append(cur)
    return chunks
