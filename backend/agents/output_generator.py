from backend.agents.base import AgentBase
from backend.agents.json_utils import parse_json_response


class OutputGenerator(AgentBase):
    async def generate(
        self,
        owner: str,
        repo: str,
        repo_path: str,
        issue_analysis: dict,
        review_comments: list[dict],
        constitution: dict,
    ) -> dict:
        await self.broadcast(
            {
                "type": "stage_start",
                "stage": "output_generator",
                "description": "Generating PR description",
            }
        )

        diff = await self.tool_server.call_tool("git_diff", {})
        diff_text = diff["content"][0]["text"]

        rounds = {}
        for comment in review_comments:
            round_number = comment.get("round_number", 1)
            rounds.setdefault(round_number, []).append(comment)

        transcript_parts = []
        for round_number, comments in sorted(rounds.items()):
            transcript_parts.append(f"### Review Round {round_number}")
            for comment in comments:
                transcript_parts.append(
                    f"**[{comment['comment_type']}]** {comment['content']}"
                )
        transcript = "\n\n".join(transcript_parts)

        pr_norms = constitution.get("pr_norms", "")
        system = f"""
You generate pull request descriptions for the {owner}/{repo} repository.
PR style for this project: {pr_norms}

Write a PR description that:
- Has a concise, descriptive title (no "fix:" prefix unless that's this project's convention)
- Has a body with: what changed and why, how it was tested, any caveats
- References the issue number
- Is written in the same tone as other PRs in this project

Output ONLY a JSON object with keys: "title" (string) and "body" (string, markdown).
"""
        user_msg = f"""
Issue #{issue_analysis.get('issue_number', '?')}: {issue_analysis['one_line_summary']}

Root cause: {issue_analysis['root_cause']}

Changes made:
{diff_text[:5000]}
"""
        raw, tokens = await self.run_single_call(system, user_msg)
        pr = parse_json_response(raw, "output_generator")

        result = {
            "diff": diff_text,
            "pr_title": pr["title"],
            "pr_body": pr["body"],
            "review_transcript": transcript,
            "review_rounds": len(rounds),
            "total_review_comments": len(review_comments),
        }
        await self.broadcast(
            {
                "type": "stage_complete",
                "stage": "output_generator",
                "token_count": tokens,
            }
        )
        return result
