"""
Stand-up update extractor.

Calls openai/gpt-oss-120b via the Groq free-tier API.
Reads the prompt from prompts/extract_v1.md (never inline).
Retries once on invalid output; stores FAILED if both attempts fail.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from groq import Groq
from pydantic import ValidationError

from schemas.update import Extraction, StoredUpdate

MODEL_ID = "openai/gpt-oss-120b"
PROMPT_VERSION = "extract_v1"
REPO_ROOT = Path(__file__).parent.parent
PROMPT_PATH = REPO_ROOT / "prompts" / f"{PROMPT_VERSION}.md"

_client: Groq | None = None


def _get_client() -> Groq:
    global _client
    if _client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Add it to ~/.config/ and source it before running."
            )
        _client = Groq(api_key=api_key)
    return _client


def _load_prompt() -> str:
    return PROMPT_PATH.read_text()


def _call_model(system_prompt: str, user_payload: dict) -> str:
    client = _get_client()
    response = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload)},
        ],
        temperature=0,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


def _parse_extraction(raw_json: str) -> Extraction:
    data = json.loads(raw_json)
    return Extraction.model_validate(data)


def extract(
    raw: str,
    member_id: str,
    standup_date: date,
    update_id: str,
    source: str = "real",
) -> StoredUpdate:
    """
    Extract structured fields from one raw stand-up message.

    Retries once if the model returns invalid JSON or fails schema validation.
    Stores FAILED (never guesses) if both attempts fail.

    Returns a StoredUpdate with provenance fields always populated.
    """
    system_prompt = _load_prompt()
    user_payload = {
        "standup_date": standup_date.isoformat(),
        "member_id": member_id,
        "raw": raw,
    }

    extraction: Extraction | str | None = None

    for attempt in range(2):
        try:
            raw_json = _call_model(system_prompt, user_payload)
            extraction = _parse_extraction(raw_json)
            break
        except (json.JSONDecodeError, ValidationError, Exception) as exc:
            if attempt == 1:
                # Both attempts failed — store FAILED, never guess
                extraction = "FAILED"
                _log_failure(update_id, attempt + 1, exc)

    return StoredUpdate(
        id=update_id,
        raw=raw,
        member_id=member_id,
        standup_date=standup_date,
        source=source,
        model_id=MODEL_ID,
        prompt_version=PROMPT_VERSION,
        extraction=extraction,
    )


def _log_failure(update_id: str, attempt: int, exc: Exception) -> None:
    print(
        f"[extractor] FAILED update={update_id} attempt={attempt} "
        f"error={type(exc).__name__}: {exc}"
    )
