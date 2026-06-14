import asyncio
import re
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend import db
from backend.agents.orchestrator import Orchestrator
from backend.api.websocket import get_broadcast_fn
from backend.db.models import Run


router = APIRouter()
ISSUE_URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/issues/(\d+)$")


class CreateRunRequest(BaseModel):
    issue_url: str


@router.post("/runs")
async def create_run(request: CreateRunRequest):
    match = ISSUE_URL_RE.match(request.issue_url)
    if not match:
        raise HTTPException(
            status_code=400,
            detail="issue_url must match https://github.com/{owner}/{repo}/issues/{number}",
        )

    owner, repo, issue_number = match.group(1), match.group(2), int(match.group(3))
    run = Run(
        id=str(uuid4()),
        issue_url=request.issue_url,
        repo_owner=owner,
        repo_name=repo,
        issue_number=issue_number,
    )
    await db.create_run(run)
    asyncio.create_task(run_pipeline(run.id, request.issue_url))
    return {"run_id": run.id, "status": "pending"}


@router.get("/runs")
async def list_runs():
    runs = await db.list_runs(limit=20)
    return [
        {
            "id": run.id,
            "issue_url": run.issue_url,
            "repo_owner": run.repo_owner,
            "repo_name": run.repo_name,
            "issue_number": run.issue_number,
            "status": run.status.value,
            "created_at": run.created_at.isoformat(),
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        for run in runs
    ]


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    run = await db.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    stages = await db.get_stage_results(run_id)
    comments = await db.get_review_comments(run_id)
    run_data = run.model_dump(mode="json")
    run_data["status"] = run.status.value
    run_data["stages"] = [stage.model_dump(mode="json") for stage in stages]
    run_data["comments"] = [comment.model_dump(mode="json") for comment in comments]
    return run_data


@router.get("/constitutions/{owner}/{repo}")
async def get_constitution(owner: str, repo: str):
    repo_key = f"{owner}/{repo}"
    constitution = await db.get_constitution(repo_key)
    if constitution is None:
        raise HTTPException(status_code=404, detail="Constitution not found")
    return constitution


async def run_pipeline(run_id: str, issue_url: str):
    broadcast = get_broadcast_fn(run_id)
    try:
        orchestrator = Orchestrator(run_id=run_id, broadcast_fn=broadcast)
        await orchestrator.run(issue_url)
    except Exception as e:
        await db.update_run(
            run_id,
            status="failed",
            error=str(e),
            completed_at=datetime.utcnow(),
        )
        await broadcast({"type": "run_error", "error": str(e)})
