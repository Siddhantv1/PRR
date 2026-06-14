import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Optional

import aiosqlite

from backend.config import config
from backend.db.models import ReviewComment, Run, RunStatus, StageResult


@asynccontextmanager
async def get_db():
    db = await aiosqlite.connect(config.DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        yield db
    finally:
        await db.close()


async def init_db():
    async with get_db() as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                issue_url TEXT,
                repo_owner TEXT,
                repo_name TEXT,
                issue_number INTEGER,
                status TEXT,
                created_at TEXT,
                completed_at TEXT,
                error TEXT,
                result_json TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS stage_results (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                stage TEXT,
                started_at TEXT,
                completed_at TEXT,
                result_json TEXT,
                token_count INTEGER,
                error TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS review_comments (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                round_number INTEGER,
                role TEXT,
                content TEXT,
                comment_type TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS constitutions (
                repo_key TEXT PRIMARY KEY,
                constitution_json TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        await db.commit()


async def create_run(run: Run) -> Run:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO runs (
                id, issue_url, repo_owner, repo_name, issue_number, status,
                created_at, completed_at, error, result_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run.id,
                run.issue_url,
                run.repo_owner,
                run.repo_name,
                run.issue_number,
                run.status.value,
                _datetime_to_text(run.created_at),
                _datetime_to_text(run.completed_at),
                run.error,
                _json_to_text(run.result),
            ),
        )
        await db.commit()
    return run


async def update_run(run_id: str, **kwargs) -> None:
    if not kwargs:
        return

    allowed_fields = {
        "issue_url",
        "repo_owner",
        "repo_name",
        "issue_number",
        "status",
        "created_at",
        "completed_at",
        "error",
        "result",
        "result_json",
    }
    unknown_fields = set(kwargs) - allowed_fields
    if unknown_fields:
        raise ValueError(f"Unknown run fields: {', '.join(sorted(unknown_fields))}")

    assignments: list[str] = []
    values: list[Any] = []
    for key, value in kwargs.items():
        column = "result_json" if key == "result" else key
        assignments.append(f"{column} = ?")
        values.append(_serialize_run_update_value(key, value))
    values.append(run_id)

    async with get_db() as db:
        await db.execute(
            f"UPDATE runs SET {', '.join(assignments)} WHERE id = ?",
            values,
        )
        await db.commit()


async def get_run(run_id: str) -> Optional[Run]:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
        row = await cursor.fetchone()
    return _row_to_run(row) if row else None


async def list_runs(limit: int = 20) -> list[Run]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = await cursor.fetchall()
    return [_row_to_run(row) for row in rows]


async def save_stage_result(result: StageResult) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO stage_results (
                id, run_id, stage, started_at, completed_at,
                result_json, token_count, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.id,
                result.run_id,
                result.stage,
                _datetime_to_text(result.started_at),
                _datetime_to_text(result.completed_at),
                result.result_json,
                result.token_count,
                result.error,
            ),
        )
        await db.commit()


async def get_stage_results(run_id: str) -> list[StageResult]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM stage_results WHERE run_id = ?",
            (run_id,),
        )
        rows = await cursor.fetchall()
    return [
        StageResult(
            id=row["id"],
            run_id=row["run_id"],
            stage=row["stage"],
            started_at=_text_to_datetime(row["started_at"]),
            completed_at=_text_to_datetime(row["completed_at"]),
            result_json=row["result_json"],
            token_count=row["token_count"] or 0,
            error=row["error"],
        )
        for row in rows
    ]


async def save_review_comment(comment: ReviewComment) -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO review_comments (
                id, run_id, round_number, role, content, comment_type
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                comment.id,
                comment.run_id,
                comment.round_number,
                comment.role,
                comment.content,
                comment.comment_type,
            ),
        )
        await db.commit()


async def get_review_comments(run_id: str) -> list[ReviewComment]:
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT * FROM review_comments
            WHERE run_id = ?
            ORDER BY round_number, id
            """,
            (run_id,),
        )
        rows = await cursor.fetchall()
    return [
        ReviewComment(
            id=row["id"],
            run_id=row["run_id"],
            round_number=row["round_number"],
            role=row["role"],
            content=row["content"],
            comment_type=row["comment_type"],
        )
        for row in rows
    ]


async def save_constitution(repo_key: str, constitution: dict) -> None:
    now = _datetime_to_text(datetime.utcnow())
    async with get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO constitutions (
                repo_key, constitution_json, created_at, updated_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (repo_key, json.dumps(constitution), now, now),
        )
        await db.commit()


async def get_constitution(repo_key: str) -> Optional[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT constitution_json FROM constitutions WHERE repo_key = ?",
            (repo_key,),
        )
        row = await cursor.fetchone()
    return json.loads(row["constitution_json"]) if row else None


def _row_to_run(row: aiosqlite.Row) -> Run:
    return Run(
        id=row["id"],
        issue_url=row["issue_url"],
        repo_owner=row["repo_owner"],
        repo_name=row["repo_name"],
        issue_number=row["issue_number"],
        status=RunStatus(row["status"]),
        created_at=_text_to_datetime(row["created_at"]),
        completed_at=_text_to_datetime(row["completed_at"]),
        error=row["error"],
        result=json.loads(row["result_json"]) if row["result_json"] else None,
    )


def _serialize_run_update_value(key: str, value: Any) -> Any:
    if key == "status" and isinstance(value, RunStatus):
        return value.value
    if key in {"created_at", "completed_at"}:
        return _datetime_to_text(value)
    if key in {"result", "result_json"}:
        return value if isinstance(value, str) or value is None else _json_to_text(value)
    return value


def _datetime_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _text_to_datetime(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _json_to_text(value: dict | None) -> str | None:
    return json.dumps(value) if value is not None else None
