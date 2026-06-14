import json

from backend.agents.base import AgentBase


class ContributorAgent(AgentBase):
    def build_system_prompt(
        self,
        repo_name: str,
        constitution: dict,
        issue_analysis: dict,
    ) -> str:
        constitution_text = json.dumps(constitution, indent=2)
        return f"""
You are an experienced Go developer contributing to {repo_name}. You are fixing a reported issue.

═══════════════════════════════════════
PROJECT CONSTITUTION — FOLLOW ALL RULES
═══════════════════════════════════════
{constitution_text}
═══════════════════════════════════════

Issue type: {issue_analysis["type"]}
Summary: {issue_analysis["one_line_summary"]}
Root cause: {issue_analysis["root_cause"]}
Files likely affected: {", ".join(issue_analysis["affected_files"])}

Fix strategy:
{issue_analysis["fix_strategy"]}

RULES (non-negotiable):
1. Make the SMALLEST possible correct change. Do not refactor, rename, or clean up unrelated code.
2. Every code change must have a corresponding test. No exceptions.
3. Follow EVERY convention in the Project Constitution above — naming, error handling, test structure, imports.
4. After writing code, ALWAYS run run_tests to verify. If tests fail, fix them.
5. After tests pass, run run_vet. Fix any vet issues.
6. Only use write_file, read_file, search_code, list_files, run_tests, run_vet, git_diff, git_status.
7. When you are fully satisfied — tests passing, vet clean — call git_diff and then write exactly "CONTRIBUTOR_DONE" on its own line.

Begin by reading the affected files to understand the current code, then implement the fix.
"""

    async def implement(
        self,
        owner: str,
        repo: str,
        repo_path: str,
        constitution: dict,
        issue_analysis: dict,
        revision_feedback: list[dict] | None = None,
    ) -> str:
        await self.broadcast(
            {
                "type": "stage_start",
                "stage": "contributor",
                "description": "Implementing fix",
            }
        )

        system = self.build_system_prompt(f"{owner}/{repo}", constitution, issue_analysis)

        if revision_feedback:
            blocking = [
                comment
                for comment in revision_feedback
                if comment.get("comment_type") == "BLOCKING"
            ]
            feedback_lines = "\n".join(f"- {comment['content']}" for comment in blocking)
            initial_message = f"""
The maintainer reviewed your last fix and has the following BLOCKING issues that must be resolved:

{feedback_lines}

Review your current changes with git_diff, then fix each blocking issue. Run tests again when done. Write "CONTRIBUTOR_DONE" when complete.
"""
        else:
            initial_message = "Begin implementing the fix. Start by reading the relevant files."

        raw_text, tokens = await self.run_loop(system, initial_message)

        diff = await self.tool_server.call_tool("git_diff", {})
        diff_text = diff["content"][0]["text"]

        await self.broadcast(
            {
                "type": "stage_complete",
                "stage": "contributor",
                "token_count": tokens,
                "diff_lines": diff_text.count("\n"),
            }
        )
        return diff_text
