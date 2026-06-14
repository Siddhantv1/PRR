from backend.agents.base import AgentBase
from backend.agents.json_utils import parse_json_response


class IssueAnalyst(AgentBase):
    SYSTEM_PROMPT = """
You are a bug triage engineer analyzing a GitHub issue to produce a precise fix plan.

Work in this order:
1. get_issue to read the full issue + comments
2. search_code for every function name, type name, or file name mentioned in the issue
3. git_log on each file you find to understand recent change history
4. search_issues with the core error message or symptom as query — find similar past issues
5. search_prs with the same query — find if this has been fixed before or attempted

After your research, output ONLY a valid JSON object with these keys:
{
  "type": "bug | feature | docs | refactor",
  "one_line_summary": "precise one-sentence description of what needs to change",
  "root_cause": "what is actually wrong and why",
  "affected_files": ["relative/path/to/file.go", "..."],
  "fix_strategy": "paragraph describing exactly what change to make, what NOT to change, and why",
  "related_prs": [{"number": N, "title": "...", "relevance": "why this is related"}],
  "related_issues": [{"number": N, "title": "..."}],
  "confidence": "high | medium | low",
  "ambiguities": ["any unclear aspects of the issue that may require judgment calls"]
}

Be conservative with affected_files — only list files you're confident need changes.
"""

    async def analyze(self, owner: str, repo: str, issue_number: int) -> dict:
        await self.broadcast(
            {
                "type": "stage_start",
                "stage": "issue_analyst",
                "description": f"Analyzing issue #{issue_number}",
            }
        )

        initial_message = f"Analyze issue #{issue_number} in {owner}/{repo}. Produce the fix plan JSON."
        raw_text, tokens = await self.run_loop(self.SYSTEM_PROMPT, initial_message)

        analysis = parse_json_response(raw_text, "issue_analyst")

        await self.broadcast(
            {
                "type": "stage_complete",
                "stage": "issue_analyst",
                "token_count": tokens,
                "summary": analysis["one_line_summary"],
            }
        )
        return analysis
