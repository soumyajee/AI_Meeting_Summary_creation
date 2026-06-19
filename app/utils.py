import io
from typing import List

import docx
import pdfplumber
from fastapi import UploadFile


def read_upload_file(upload: UploadFile) -> str:
    if not upload.filename:
        raise ValueError("Uploaded file must have a filename.")

    filename = upload.filename.lower()

    try:
        content = upload.file.read()
    finally:
        upload.file.close()

    if not content:
        raise ValueError("Uploaded file is empty.")

    if filename.endswith(".txt"):
        return content.decode("utf-8", errors="ignore")

    if filename.endswith(".pdf"):
        try:
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception as e:
            raise ValueError(f"Failed to read PDF file: {str(e)}") from e

    if filename.endswith(".docx"):
        try:
            document = docx.Document(io.BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs)
        except Exception as e:
            raise ValueError(f"Failed to read DOCX file: {str(e)}") from e

    raise ValueError("Unsupported file type. Only .txt, .pdf, and .docx are allowed.")


def chunk_transcript(
    transcript: str,
    chunk_size: int = 250,
    overlap: int = 50,
) -> List[str]:
    if not transcript or not transcript.strip():
        return []

    words = transcript.split()
    chunks = []
    start = 0

    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))

        if end == len(words):
            break

        start += chunk_size - overlap

    return chunks