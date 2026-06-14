from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Run(BaseModel):
    id: str
    issue_url: str
    repo_owner: str
    repo_name: str
    issue_number: int
    status: RunStatus = RunStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[dict] = None


class StageResult(BaseModel):
    id: str
    run_id: str
    stage: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    result_json: Optional[str] = None
    token_count: int = 0
    error: Optional[str] = None


class ReviewComment(BaseModel):
    id: str
    run_id: str
    round_number: int
    role: str
    content: str
    comment_type: Optional[str] = None
