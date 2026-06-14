import json

from backend.agents.base import AgentBase


INVESTIGATE_TOOLS = [
    "read_file",
    "list_files",
    "search_code",
    "file_exists",
    "git_log",
    "git_blame",
    "git_status",
    "git_diff",
    "get_issue",
    "search_prs",
    "get_pr_diff",
    "search_issues",
]

IMPLEMENT_TOOLS = [
    "read_file",
    "write_file",
    "file_exists",
    "run_tests",
    "run_vet",
    "run_build",
    "git_diff",
    "git_status",
]
# No GitHub API tools in implement phase — reading done, now write.


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
            feedback_lines = "\n".join(
                f"- {comment['content']}" for comment in blocking
            )
            phase1_msg = f"""
Maintainer blocked this PR. Read the diff and relevant files to understand
what needs to change.

BLOCKING issues:
{feedback_lines}

Use read_file, search_code, git_diff to understand current state.
Do NOT write any files yet. Investigate only.
When you fully understand the problem, say: INVESTIGATION_COMPLETE
"""
        else:
            phase1_msg = f"""
Investigate the repository to understand what needs to change.
Issue: {issue_analysis["one_line_summary"]}
Root cause: {issue_analysis["root_cause"]}
Likely files: {", ".join(issue_analysis["affected_files"])}

Use read_file, search_code, list_files, git_log to gather evidence.
Do NOT write any files yet. Investigate only.
When you have read all relevant files and understand the fix needed,
say: INVESTIGATION_COMPLETE
"""

        await self.broadcast({"type": "info", "message": "Phase 1: Investigating..."})
        _, tokens1, history = await self.run_loop(
            system_prompt=system,
            initial_message=phase1_msg,
            max_iterations=6,
            allowed_tools=INVESTIGATE_TOOLS,
            pressure_at=5,
            pressure_message=(
                "You have 1 investigation iteration left. Wrap up. "
                "Say INVESTIGATION_COMPLETE now."
            ),
            return_history=True,
        )

        phase2_msg = """
Investigation complete. Now implement the fix.

Rules:
1. Make the SMALLEST correct change. No unrelated edits.
2. Write the fix using write_file.
3. Add or update tests using write_file.
4. Run run_tests — if fail, fix and re-run. Max 2 test cycles.
5. Run run_vet — fix any issues.
6. Call git_diff to confirm your changes look correct.
7. When tests pass and vet is clean, write: CONTRIBUTOR_DONE

Start writing now.
"""

        await self.broadcast({"type": "info", "message": "Phase 2: Implementing..."})
        final_text, tokens2, final_history = await self.run_loop(
            system_prompt=system,
            initial_message=phase2_msg,
            max_iterations=8,
            allowed_tools=IMPLEMENT_TOOLS,
            pressure_at=6,
            pressure_message=(
                "2 iterations left. If tests pass: call git_diff then write "
                "CONTRIBUTOR_DONE immediately. If tests still failing: write "
                "best-effort fix and write CONTRIBUTOR_DONE."
            ),
            initial_contents=history,
            return_history=True,
        )

        if "CONTRIBUTOR_DONE" not in final_text:
            await self.broadcast({"type": "info", "message": "Forcing finalization..."})
            force_msg = (
                "Time is up. Call git_diff RIGHT NOW to show your changes, "
                "then write CONTRIBUTOR_DONE on its own line. No more edits."
            )
            final_text, tokens_f, final_history = await self.run_loop(
                system_prompt=system,
                initial_message=force_msg,
                max_iterations=2,
                allowed_tools=["git_diff", "git_status"],
                initial_contents=final_history,
                return_history=True,
            )
            tokens2 += tokens_f

        total_tokens = tokens1 + tokens2

        diff_result = await self.tool_server.call_tool("git_diff", {})
        diff_text = diff_result["content"][0]["text"]

        if diff_text == "No changes." or not diff_text.strip():
            await self.broadcast(
                {
                    "type": "info",
                    "message": (
                        "Warning: no file changes detected after contributor phase."
                    ),
                }
            )

        await self.broadcast(
            {
                "type": "stage_complete",
                "stage": "contributor",
                "token_count": total_tokens,
                "diff_lines": diff_text.count("\n"),
            }
        )
        return diff_text
