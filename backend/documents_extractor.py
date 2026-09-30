"""
Text and metadata extraction engine for documents.
Supports PDF, DOCX, TXT, MD, CSV, RTF with clean chunking for semantic embeddings.
"""

import os
import re
from typing import Dict, Any, List, Optional, Tuple

def extract_document_text(file_path: str) -> Dict[str, Any]:
    """
    Extracts text, title, page count, and word count from a supported document file.
    Returns:
        {
            "text": str,
            "title": str or None,
            "page_count": int,
            "word_count": int,
            "summary": str,
            "error": str or None
        }
    """
    ext = os.path.splitext(file_path)[1].lower()
    text = ""
    title = None
    page_count = 1
    error = None

    try:
        if ext == ".pdf":
            text, page_count, title = _extract_pdf(file_path)
        elif ext in [".docx", ".doc"]:
            text, page_count, title = _extract_docx(file_path)
        elif ext in [".txt", ".md", ".rtf", ".csv", ".json", ".log"]:
            text = _extract_plaintext(file_path, ext)
            title = _infer_title_from_text(text, os.path.basename(file_path))
        else:
            # Fallback text attempt
            text = _extract_plaintext(file_path, ext)
            title = _infer_title_from_text(text, os.path.basename(file_path))
    except Exception as e:
        error = str(e)
        text = ""

    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)
    
    # Generate concise summary / snippet (first 350 chars or first paragraph)
    summary = ""
    if text:
        clean_text = " ".join(text.split())
        summary = clean_text[:350] + ("..." if len(clean_text) > 350 else "")

    if not title:
        base = os.path.basename(file_path)
        title = os.path.splitext(base)[0].replace("_", " ").replace("-", " ")

    return {
        "text": text,
        "title": title,
        "page_count": max(1, page_count),
        "word_count": word_count,
        "summary": summary,
        "error": error
    }

def _extract_pdf(file_path: str) -> Tuple[str, int, Optional[str]]:
    import pypdf
    reader = pypdf.PdfReader(file_path)
    page_count = len(reader.pages)
    
    title = None
    if reader.metadata:
        title = reader.metadata.title or None

    extracted_pages = []
    for page in reader.pages:
        try:
            pt = page.extract_text()
            if pt:
                extracted_pages.append(pt)
        except Exception:
            continue

    full_text = "\n\n".join(extracted_pages)
    if not title:
        title = _infer_title_from_text(full_text, os.path.basename(file_path))
    return full_text, page_count, title

def _extract_docx(file_path: str) -> Tuple[str, int, Optional[str]]:
    try:
        import docx
        doc = docx.Document(file_path)
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        
        # Tables text
        for table in doc.tables:
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    paras.append(row_text)

        full_text = "\n\n".join(paras)
        # Rough page count estimate: ~350 words per page
        words = len(re.findall(r"\b\w+\b", full_text))
        page_count = max(1, (words + 349) // 350)
        title = _infer_title_from_text(full_text, os.path.basename(file_path))
        return full_text, page_count, title
    except Exception as e:
        # If older binary .doc format or parsing error, fallback to string extraction
        return _extract_plaintext(file_path, ".doc"), 1, None

def _extract_plaintext(file_path: str, ext: str) -> str:
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252", "ascii"]
    raw = None
    for enc in encodings:
        try:
            with open(file_path, "r", encoding=enc, errors="replace") as f:
                raw = f.read()
                break
        except Exception:
            continue

    if raw is None:
        with open(file_path, "rb") as f:
            raw = f.read().decode("utf-8", errors="ignore")

    if ext == ".rtf":
        # Strip basic RTF control words
        clean = re.sub(r"\\[a-z0-9]+(\s|;)?", "", raw)
        clean = re.sub(r"[{}]", "", clean)
        return clean.strip()

    return raw.strip()

def _infer_title_from_text(text: str, fallback_filename: str) -> str:
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    for line in lines[:5]:
        # If line looks like a title: 3 to 100 characters, no strange syntax
        if 3 <= len(line) <= 100 and not line.startswith(("{", "<", "/*", "#!", "http")):
            return re.sub(r"^#+\s*", "", line)  # Remove markdown header hashes
    base = os.path.splitext(fallback_filename)[0]
    return base.replace("_", " ").replace("-", " ")

def chunk_document_text(text: str, chunk_size_words: int = 250, overlap_words: int = 50) -> List[str]:
    """
    Splits text into overlapping chunks of words for precise semantic retrieval.
    """
    words = text.split()
    if not words:
        return []
    if len(words) <= chunk_size_words:
        return [" ".join(words)]

    chunks = []
    step = max(1, chunk_size_words - overlap_words)
    for i in range(0, len(words), step):
        chunk = words[i:i + chunk_size_words]
        if chunk:
            chunks.append(" ".join(chunk))
        if i + chunk_size_words >= len(words):
            break

    return chunks
