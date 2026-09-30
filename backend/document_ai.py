"""Local document analysis through an Ollama model running on this computer."""

import json
import re
from typing import Any, Dict, List
from urllib import error, request

from backend.documents_db import save_document_analysis

OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
DEFAULT_MODEL = "qwen3:8b"


def _extract_json(raw: str) -> Dict[str, Any]:
    """Extracts the first JSON object from a model response."""
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Local model did not return a JSON object")
    return json.loads(cleaned[start:end + 1])


def analyze_document(doc: Dict[str, Any], interest_lists: List[Dict[str, Any]], model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """Analyzes one extracted document and persists the structured result."""
    interests = "\n".join(f"- {item['name']}: {item['description']}" for item in interest_lists)
    prompt = f"""You are a careful personal document triage assistant.
Analyze the document below against the user's interest lists.
Return JSON only with keys: summary, document_type, highlights, matches, suggested_status.
summary must be 2-5 concise sentences. highlights must contain exact short quotes copied from the document,
with category, quote, reason, and confidence from 0 to 1. Only flag a match when the document contains evidence.
Suggested status must be keep, review, or remove. Never recommend remove solely because the document is uninteresting.
Interest lists:
{interests or '- No custom lists yet'}

Title: {doc.get('title') or doc.get('file_name')}
Document text:
{(doc.get('extracted_text') or '')[:30000]}
"""
    payload = json.dumps({"model": model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
    req = request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with request.urlopen(req, timeout=180) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError) as exc:
        raise RuntimeError("Ollama is not running at http://127.0.0.1:11434") from exc

    result = _extract_json(body.get("response", ""))
    result.setdefault("summary", "")
    result.setdefault("highlights", [])
    result.setdefault("matches", [])
    result.setdefault("suggested_status", "review")
    if result["suggested_status"] not in {"keep", "review", "remove"}:
        result["suggested_status"] = "review"
    save_document_analysis(doc["id"], result["summary"], result)
    return result