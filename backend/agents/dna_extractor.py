import json
import re

from backend import db
from backend.agents.base import AgentBase


class DNAExtractor(AgentBase):
    SYSTEM_PROMPT = """
You are a repository archaeologist. Your job is to build a Project Constitution — a structured JSON document that captures the coding conventions of this Go open-source project so deeply that any generated code will be indistinguishable from code written by the core team.

Work methodically:
1. read_file CONTRIBUTING.md (if it exists — use file_exists first)
2. read_file README.md
3. list_files with recursive=true, extensions=[".go"] — then read_file on 8–10 representative files: pick a mix of core logic files, test files, and utility files
4. search_prs with query="" limit=15 — read at least 5 of their diffs with get_pr_diff to understand what kinds of changes get merged and how they're written
5. search_code for error handling patterns: search for "fmt.Errorf" and "errors.New" and "errors.Is"
6. search_code for test function name patterns: search for "func Test"

After gathering evidence, output ONLY a valid JSON object with exactly these keys — no markdown, no explanation, just the JSON:
{
  "error_handling": "precise description of how errors are created, wrapped with %w or not, and returned",
  "naming": "exact naming conventions for variables, functions, exported types, unexported types, constants",
  "test_patterns": "how tests are structured — table-driven style, helper functions, assertion style, naming like TestFoo or TestFoo_whenBar",
  "imports": "how imports are grouped — stdlib then external then internal, alias conventions",
  "comments": "doc comment conventions — when godoc is required, format for exported symbols",
  "pr_norms": "based on merged PR analysis: what kinds of changes get merged, typical PR scope, what reviewers ask for",
  "red_flags": ["list", "of", "patterns", "this", "project", "explicitly", "avoids"],
  "sample_prs": [{"number": 123, "title": "...", "type": "bug|feature|refactor|docs", "key_pattern": "one sentence about what made this PR good"}]
}
"""

    async def extract(self, owner: str, repo: str, repo_path: str) -> dict:
        repo_key = f"{owner}/{repo}"
        cached = await db.get_constitution(repo_key)
        if cached:
            await self.broadcast(
                {
                    "type": "stage_info",
                    "message": f"Using cached constitution for {repo_key}",
                }
            )
            return cached

        await self.broadcast(
            {
                "type": "stage_start",
                "stage": "dna_extractor",
                "description": f"Analyzing {repo_key} conventions",
            }
        )

        initial_message = f"Analyze the repository {owner}/{repo}. Build the Project Constitution."
        raw_text, tokens = await self.run_loop(self.SYSTEM_PROMPT, initial_message)

        json_text = raw_text.strip()
        if json_text.startswith("```"):
            json_text = re.sub(r"```(?:json)?\n?", "", json_text).strip("` \n")
        constitution = json.loads(json_text)

        await db.save_constitution(repo_key, constitution)
        await self.broadcast(
            {
                "type": "stage_complete",
                "stage": "dna_extractor",
                "token_count": tokens,
            }
        )
        return constitution
