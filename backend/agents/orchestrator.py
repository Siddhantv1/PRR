import asyncio
import json
import os
import re
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import uuid4

import git

from backend import db
from backend.agents.contributor import ContributorAgent
from backend.agents.dna_extractor import DNAExtractor
from backend.agents.issue_analyst import IssueAnalyst
from backend.agents.maintainer import MaintainerSimulator
from backend.agents.output_generator import OutputGenerator
from backend.config import config
from backend.db.models import StageResult
from backend.mcp_server.server import ToolServer


class Orchestrator:
    def __init__(
        self,
        run_id: str,
        broadcast_fn: Callable[[dict], Awaitable[None]],
    ):
        self.run_id = run_id
        self.broadcast = broadcast_fn

    async def run(self, issue_url: str) -> dict:
        match = re.match(r"https://github\.com/([^/]+)/([^/]+)/issues/(\d+)", issue_url)
        if not match:
            raise ValueError(f"Invalid GitHub issue URL: {issue_url}")
        owner, repo, issue_number = match.group(1), match.group(2), int(match.group(3))

        await db.update_run(self.run_id, status="running")

        try:
            repo_path = os.path.join(config.REPOS_DIR, f"{owner}_{repo}_{self.run_id}")
            os.makedirs(config.REPOS_DIR, exist_ok=True)
            await self.broadcast(
                {"type": "info", "message": f"Cloning {owner}/{repo}..."}
            )
            clone_url = f"https://{config.GITHUB_TOKEN}@github.com/{owner}/{repo}.git"

            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: git.Repo.clone_from(clone_url, repo_path),
            )
            await self.broadcast({"type": "info", "message": "Repository cloned."})

            tool_server = ToolServer(repo_path=repo_path, owner=owner, repo=repo)

            stage1_start = datetime.utcnow()
            dna = DNAExtractor(tool_server, self.broadcast)
            constitution = await dna.extract(owner, repo, repo_path)
            await db.save_stage_result(
                StageResult(
                    id=str(uuid4()),
                    run_id=self.run_id,
                    stage="dna_extractor",
                    started_at=stage1_start,
                    completed_at=datetime.utcnow(),
                    result_json=json.dumps(constitution),
                )
            )

            stage2_start = datetime.utcnow()
            issue_analysis = await IssueAnalyst(tool_server, self.broadcast).analyze(
                owner,
                repo,
                issue_number,
            )
            issue_analysis["issue_number"] = issue_number
            await db.save_stage_result(
                StageResult(
                    id=str(uuid4()),
                    run_id=self.run_id,
                    stage="issue_analyst",
                    started_at=stage2_start,
                    completed_at=datetime.utcnow(),
                    result_json=json.dumps(issue_analysis),
                )
            )

            all_review_comments = []
            final_diff = ""

            for revision_round in range(config.MAX_REVISION_ROUNDS):
                round_number = revision_round + 1
                await self.broadcast(
                    {
                        "type": "revision_start",
                        "round": round_number,
                        "total": config.MAX_REVISION_ROUNDS,
                    }
                )

                contributor = ContributorAgent(tool_server, self.broadcast)
                blocking_comments = [
                    comment
                    for comment in all_review_comments
                    if comment.get("comment_type") == "BLOCKING"
                ]
                final_diff = await contributor.implement(
                    owner,
                    repo,
                    repo_path,
                    constitution,
                    issue_analysis,
                    blocking_comments if revision_round > 0 else None,
                )

                maintainer = MaintainerSimulator(tool_server, self.broadcast)
                maintainer._run_id = self.run_id
                review_result = await maintainer.review(
                    owner,
                    repo,
                    final_diff,
                    constitution,
                    issue_analysis,
                    round_number,
                )
                for comment in review_result["comments"]:
                    comment.setdefault("round_number", round_number)
                all_review_comments.extend(review_result["comments"])

                if review_result["approved"]:
                    await self.broadcast(
                        {
                            "type": "info",
                            "message": f"Maintainer approved after {round_number} round(s).",
                        }
                    )
                    break
            else:
                await self.broadcast(
                    {
                        "type": "info",
                        "message": f"Revision limit reached ({config.MAX_REVISION_ROUNDS} rounds).",
                    }
                )

            output_gen = OutputGenerator(tool_server, self.broadcast)
            result = await output_gen.generate(
                owner,
                repo,
                repo_path,
                issue_analysis,
                all_review_comments,
                constitution,
            )

            await db.update_run(
                self.run_id,
                status="completed",
                completed_at=datetime.utcnow(),
                result_json=json.dumps(result),
            )
            await self.broadcast({"type": "run_complete", **result})

            return result
        except Exception as e:
            await db.update_run(self.run_id, status="failed", error=str(e))
            await self.broadcast({"type": "run_error", "error": str(e)})
            raise
