"""docx → PDF 변환 (LibreOffice headless).

미리보기를 Word와 거의 동일하게 '페이지 단위'로 보여주기 위해, 정확한 페이지네이션을
LibreOffice의 실제 레이아웃 엔진으로 처리한다. (docx-preview는 내용 높이 기반 자동 분할을 못 함)
"""
import os
import subprocess
import tempfile

from app.core.logging import get_logger

logger = get_logger(__name__)


def docx_to_pdf(data: bytes) -> bytes:
    """docx 바이트 → PDF 바이트."""
    with tempfile.TemporaryDirectory() as tmp:
        inp = os.path.join(tmp, "in.docx")
        with open(inp, "wb") as f:
            f.write(data)
        # 동시 호출 시 프로필 잠금 충돌 방지를 위해 임시 UserInstallation 사용
        profile = "file://" + os.path.join(tmp, "lo_profile")
        proc = subprocess.run(
            [
                "libreoffice", "--headless", f"-env:UserInstallation={profile}",
                "--convert-to", "pdf", "--outdir", tmp, inp,
            ],
            capture_output=True,
            timeout=120,
        )
        out = os.path.join(tmp, "in.pdf")
        if proc.returncode != 0 or not os.path.exists(out):
            logger.error("libreoffice 변환 실패: %s", proc.stderr.decode("utf-8", "ignore")[:300])
            raise RuntimeError("PDF 변환 실패")
        with open(out, "rb") as f:
            return f.read()
