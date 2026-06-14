import json
import re
from uuid import uuid4

from backend import db
from backend.agents.base import AgentBase
from backend.db.models import ReviewComment


class MaintainerSimulator(AgentBase):
    def build_system_prompt(
        self,
        repo_name: str,
        constitution: dict,
        sample_prs: list[dict],
    ) -> str:
        constitution_text = json.dumps(constitution, indent=2)
        pr_examples = "\n".join(
            f"PR #{pr['number']}: {pr['title']} — {pr.get('key_pattern', '')}"
            for pr in sample_prs[:5]
        )
        return f"""
You are a senior maintainer of {repo_name}. You have merged hundreds of pull requests for this project and have strong opinions about code quality.

PROJECT CONSTITUTION (your standards):
{constitution_text}

Examples of PRs you have approved in the past:
{pr_examples}

You are doing a code review of a proposed fix. Review this diff with the same scrutiny you apply to real contributions.

Check for:
- Missing or weak tests (every behavior change needs a test)
- Violations of the Project Constitution (naming, error handling, import style, comment style)
- Unhandled edge cases that the issue description implies
- Unnecessary changes (touching code unrelated to the fix)
- Incorrect error wrapping or propagation
- Race conditions or nil pointer risks
- Missing documentation for exported symbols

Format your response as a list of comments. Each comment MUST start with exactly one of these tags on its own:
[BLOCKING] — must be fixed before this can be merged
[SUGGESTION] — would improve quality but not a hard requirement
[QUESTION] — you need clarification before deciding
[APPROVED] — use this alone (no other tags) when you have no blocking issues

For each comment, be specific: quote the relevant code or line, explain why it's a problem, and suggest the fix.

If everything looks good, respond with only: [APPROVED]
"""

    async def review(
        self,
        owner: str,
        repo: str,
        diff: str,
        constitution: dict,
        issue_analysis: dict,
        round_number: int,
    ) -> dict:
        await self.broadcast(
            {
                "type": "stage_start",
                "stage": "maintainer",
                "description": f"Reviewing diff (round {round_number})",
            }
        )

        sample_prs = constitution.get("sample_prs", [])
        system = self.build_system_prompt(f"{owner}/{repo}", constitution, sample_prs)

        user_message = f"""
Issue being fixed: {issue_analysis["one_line_summary"]}
Root cause: {issue_analysis["root_cause"]}

PROPOSED DIFF:
```diff
{diff}
```

Review this diff carefully.
"""

        review_text, tokens = await self.run_single_call(system, user_message)
        comments = self._parse_review_comments(review_text, round_number)

        for comment in comments:
            await self.broadcast(
                {
                    "type": "review_comment",
                    "round": round_number,
                    "kind": comment["comment_type"],
                    "text": comment["content"],
                }
            )
            await db.save_review_comment(
                ReviewComment(
                    id=str(uuid4()),
                    run_id=self._run_id,
                    round_number=round_number,
                    role="maintainer",
                    content=comment["content"],
                    comment_type=comment["comment_type"],
                )
            )

        is_approved = not any(
            comment["comment_type"] == "BLOCKING" for comment in comments
        )
        await self.broadcast(
            {
                "type": "stage_complete",
                "stage": "maintainer",
                "approved": is_approved,
                "token_count": tokens,
            }
        )

        return {"approved": is_approved, "comments": comments, "raw_review": review_text}

    def _parse_review_comments(self, review_text: str, round_number: int) -> list[dict]:
        """Parse [BLOCKING], [SUGGESTION], [QUESTION], [APPROVED] tags from review text."""
        comments = []
        pattern = re.compile(r"\[(BLOCKING|SUGGESTION|QUESTION|APPROVED)\]", re.IGNORECASE)
        parts = pattern.split(review_text)

        i = 1
        while i < len(parts) - 1:
            tag = parts[i].upper()
            content = parts[i + 1].strip()
            if content:
                comments.append({"comment_type": tag, "content": content[:1000]})
            i += 2

        if not comments and "APPROVED" in review_text.upper():
            comments.append(
                {"comment_type": "APPROVED", "content": "No blocking issues found."}
            )

        return comments
