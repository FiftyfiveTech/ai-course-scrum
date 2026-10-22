"""
Stand-up update extractor.

Calls openai/gpt-oss-120b via the Groq free-tier API, wired through LangChain
(ChatGroq with structured output into the Extraction schema).
Reads the prompt from prompts/extract_v1.md (never inline).
Retries once on invalid output; stores FAILED if both attempts fail.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from langchain_core.runnables import Runnable
from langchain_groq import ChatGroq

from schemas.update import Extraction, StoredUpdate

MODEL_ID = "openai/gpt-oss-120b"
PROMPT_VERSION = "extract_v1"
REPO_ROOT = Path(__file__).parent.parent
PROMPT_PATH = REPO_ROOT / "prompts" / f"{PROMPT_VERSION}.md"

_chain: Runnable | None = None


def _get_chain() -> Runnable:
    """Lazily build the ChatGroq model bound to the Extraction schema.

    json_mode mirrors the prior response_format={"type": "json_object"} contract:
    the prompt describes the schema and the model returns a single JSON object,
    which LangChain validates into an Extraction for us.
    """
    global _chain
    if _chain is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set. Add it to ~/.config/ and source it before running."
            )
        llm = ChatGroq(model=MODEL_ID, temperature=0, api_key=api_key)
        _chain = llm.with_structured_output(Extraction, method="json_mode")
    return _chain


def _load_prompt() -> str:
    return PROMPT_PATH.read_text()


def _call_model(system_prompt: str, user_payload: dict) -> Extraction:
    chain = _get_chain()
    return chain.invoke(
        [
            ("system", system_prompt),
            ("human", json.dumps(user_payload)),
        ]
    )


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
            extraction = _call_model(system_prompt, user_payload)
            break
        except Exception as exc:
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
