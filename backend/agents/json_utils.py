import json
import re
from typing import Any


def parse_json_response(raw_text: str, stage: str) -> dict[str, Any]:
    text = _strip_json_fence(raw_text)
    if not text:
        raise ValueError(f"{stage} returned an empty JSON response.")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        extracted = _extract_object(text)
        if extracted == text:
            preview = text[:500].replace("\n", "\\n")
            raise ValueError(
                f"{stage} returned invalid JSON. Response preview: {preview}"
            ) from None
        try:
            parsed = json.loads(extracted)
        except json.JSONDecodeError as exc:
            preview = text[:500].replace("\n", "\\n")
            raise ValueError(
                f"{stage} returned invalid JSON: {exc}. Response preview: {preview}"
            ) from None

    if not isinstance(parsed, dict):
        raise ValueError(f"{stage} returned JSON {type(parsed).__name__}, expected object.")
    return parsed


def _strip_json_fence(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _extract_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]
