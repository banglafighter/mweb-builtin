from pathlib import Path

from weasyprint import HTML
from mweb import MWebResponse
from mweb_crud.common import MWebCRUDException


class HTMLToPDF:

    @classmethod
    async def from_text(cls, html_text: str, file_path: str | None = None, filename: str | None = None, base_url: str | Path | None = None):
        if not html_text:
            raise MWebCRUDException(message="Invalid pdf content")

        pdf_bytes = HTML(string=html_text, base_url=base_url).write_pdf()

        if file_path:
            with open(file_path, "wb") as file:
                file.write(pdf_bytes)

        return await MWebResponse.response_pdf(
            bytes_content=pdf_bytes,
            filename=filename,
        )
