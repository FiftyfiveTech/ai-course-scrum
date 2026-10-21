"""
Pydantic models for a labelled stand-up update extraction.

Mirrors schemas/update.json. Used both as the target for model output
validation and as the storage type for the database layer.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

Origin = Literal["reported", "inferred"]
DateType = Literal["explicit", "implied"]
Source = Literal["real", "synthetic"]


class DoneItem(BaseModel):
    text: str
    origin: Origin
    task_id: Optional[str] = None


class NextItem(BaseModel):
    text: str
    origin: Origin
    task_id: Optional[str] = None


class BlockerItem(BaseModel):
    text: str
    origin: Origin
    task_id: Optional[str] = None
    owner_id: Optional[str] = None


class TaskRef(BaseModel):
    task_id: str
    origin: Origin
    mention: Optional[str] = None


class CommitmentItem(BaseModel):
    text: str
    origin: Origin
    due_date: Optional[date] = None
    date_type: DateType
    task_id: Optional[str] = None


class Extraction(BaseModel):
    """
    The structured output of the extractor for one developer's stand-up message.
    All five arrays must be present; they may be empty.
    """

    done: list[DoneItem] = Field(default_factory=list)
    next: list[NextItem] = Field(default_factory=list)
    blockers: list[BlockerItem] = Field(default_factory=list)
    task_ids: list[TaskRef] = Field(default_factory=list)
    commitments: list[CommitmentItem] = Field(default_factory=list)


class StoredUpdate(BaseModel):
    """
    Everything persisted for one stand-up update:
    the raw message, extraction result, and provenance fields.
    """

    id: str
    raw: str
    member_id: str
    standup_date: date
    source: Source = "real"

    # Provenance — always stored alongside the extraction
    model_id: str = Field(description="HF repo id of the model used, e.g. openai/gpt-oss-120b")
    prompt_version: str = Field(description="Prompt filename stem, e.g. extract_v1")

    # None means extraction has not run yet; "FAILED" means both attempts failed
    extraction: Optional[Extraction | Literal["FAILED"]] = None

    notes: Optional[str] = None
