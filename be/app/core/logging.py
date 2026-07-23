"""로깅 설정."""
import logging


class _DropRateLimitLog(logging.Filter):
    """httpx가 INFO로 찍는 'HTTP/1.1 429 Too Many Requests' 노이즈 제거.

    재시도는 app.agents.utils 쪽 'evidence 추출 rate limit …' 로그만으로 확인한다.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "429" not in msg and "Too Many Requests" not in msg


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # OpenAI/게이트웨이 rate limit 응답은 httpx INFO로 매 요청마다 찍혀 로그를 가린다
    for name in ("httpx", "httpcore", "openai"):
        logging.getLogger(name).addFilter(_DropRateLimitLog())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
