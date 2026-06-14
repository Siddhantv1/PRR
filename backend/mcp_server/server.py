import json
import logging
from collections.abc import Callable
from typing import Any

from github import Github

from backend.config import config
from backend.mcp_server.tools.file_tools import (
    file_exists,
    list_files,
    read_file,
    search_code,
    write_file,
)
from backend.mcp_server.tools.git_tools import git_blame, git_diff, git_log, git_status
from backend.mcp_server.tools.github_tools import (
    get_issue,
    get_pr_comments,
    get_pr_diff,
    search_issues,
    search_prs,
)
from backend.mcp_server.tools.go_tools import run_build, run_tests, run_vet


logger = logging.getLogger(__name__)


class ToolServer:
    def __init__(self, repo_path: str, owner: str, repo: str):
        self.repo_path = repo_path
        self.owner = owner
        self.repo = repo
        self.gh = Github(config.GITHUB_TOKEN)

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self._log_call(name, arguments)
        try:
            tool = self._tool_routes().get(name)
            if tool is None:
                raise ValueError(f"Unknown tool: {name}")
            result = tool(**arguments)
            return {"content": [{"type": "text", "text": str(result)}]}
        except Exception as e:
            return {
                "content": [{"type": "text", "text": f"ERROR: {e}"}],
                "isError": True,
            }

    def get_tool_schemas(self) -> list[dict]:
        return [
            {
                "name": "read_file",
                "description": "Read a file from the repository, truncating very large files.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "write_file",
                "description": "Write text content to a file in the repository, creating parent directories as needed.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            {
                "name": "list_files",
                "description": "List repository files, optionally recursively and filtered by extension.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "directory": {"type": "string"},
                        "recursive": {"type": "boolean"},
                        "extensions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            {
                "name": "search_code",
                "description": "Search Go source files for a string or regular expression and return matching lines with context.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string"},
                        "file_pattern": {"type": "string"},
                        "is_regex": {"type": "boolean"},
                        "max_results": {"type": "integer"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "file_exists",
                "description": "Check whether a repository path exists.",
                "input_schema": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            {
                "name": "run_tests",
                "description": "Run go test for a package pattern and return pass/fail output.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "package": {"type": "string"},
                        "verbose": {"type": "boolean"},
                        "timeout_seconds": {"type": "integer"},
                    },
                },
            },
            {
                "name": "run_vet",
                "description": "Run go vet for a package pattern.",
                "input_schema": {
                    "type": "object",
                    "properties": {"package": {"type": "string"}},
                },
            },
            {
                "name": "run_build",
                "description": "Run go build for a package pattern.",
                "input_schema": {
                    "type": "object",
                    "properties": {"package": {"type": "string"}},
                },
            },
            {
                "name": "git_diff",
                "description": "Return the current repository diff, optionally staged changes only.",
                "input_schema": {
                    "type": "object",
                    "properties": {"staged": {"type": "boolean"}},
                },
            },
            {
                "name": "git_log",
                "description": "Return recent commits, optionally scoped to a path.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
            {
                "name": "git_status",
                "description": "Return modified, staged, and untracked repository files.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
            },
            {
                "name": "git_blame",
                "description": "Return git blame information for a range of lines in a file.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "line_start": {"type": "integer"},
                        "line_end": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "get_issue",
                "description": "Fetch a GitHub issue and optionally include issue comments.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "number": {"type": "integer"},
                        "include_comments": {"type": "boolean"},
                    },
                    "required": ["number"],
                },
            },
            {
                "name": "search_prs",
                "description": "Search recently merged GitHub pull requests by title or body text.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
            {
                "name": "get_pr_diff",
                "description": "Fetch a GitHub pull request diff, truncated to 20,000 characters.",
                "input_schema": {
                    "type": "object",
                    "properties": {"number": {"type": "integer"}},
                    "required": ["number"],
                },
            },
            {
                "name": "get_pr_comments",
                "description": "Fetch GitHub pull request issue comments and review comments.",
                "input_schema": {
                    "type": "object",
                    "properties": {"number": {"type": "integer"}},
                    "required": ["number"],
                },
            },
            {
                "name": "search_issues",
                "description": "Search GitHub issues by title or body text.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "state": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
        ]

    def get_gemini_tools(self) -> list[dict]:
        """
        Convert Anthropic-format tool schemas to Gemini function declarations.
        Anthropic: {"name": ..., "description": ..., "input_schema": {...}}
        Gemini:    {"name": ..., "description": ..., "parameters": {...}}
        Also strips any "additionalProperties" keys — Gemini rejects them.
        Also converts any "integer" types to "number" — Gemini's type system is a subset.
        """
        import re as _re

        def clean_schema(schema: dict) -> dict:
            cleaned = {}
            for key, value in schema.items():
                if key == "additionalProperties":
                    continue
                if key == "type" and value == "integer":
                    cleaned[key] = "number"
                elif isinstance(value, dict):
                    cleaned[key] = clean_schema(value)
                elif isinstance(value, list):
                    cleaned[key] = [
                        clean_schema(item) if isinstance(item, dict) else item
                        for item in value
                    ]
                else:
                    cleaned[key] = value
            return cleaned

        result = []
        for tool in self.get_tool_schemas():
            declaration = {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": clean_schema(
                    tool.get("input_schema", {"type": "object", "properties": {}})
                ),
            }
            result.append(declaration)
        assert all(
            _re.match(r"^[a-zA-Z_]\w*$", tool["name"]) for tool in result
        ), "Tool name contains invalid characters for Gemini"
        assert len({tool["name"] for tool in result}) == len(result), (
            "Tool names must be unique for Gemini"
        )
        return result

    def _tool_routes(self) -> dict[str, Callable[..., Any]]:
        return {
            "read_file": lambda **args: read_file(self.repo_path, **args),
            "write_file": lambda **args: write_file(self.repo_path, **args),
            "list_files": lambda **args: list_files(self.repo_path, **args),
            "search_code": lambda **args: search_code(self.repo_path, **args),
            "file_exists": lambda **args: file_exists(self.repo_path, **args),
            "run_tests": lambda **args: run_tests(self.repo_path, **args),
            "run_vet": lambda **args: run_vet(self.repo_path, **args),
            "run_build": lambda **args: run_build(self.repo_path, **args),
            "git_diff": lambda **args: git_diff(self.repo_path, **args),
            "git_log": lambda **args: git_log(self.repo_path, **args),
            "git_status": lambda **args: git_status(self.repo_path, **args),
            "git_blame": lambda **args: git_blame(self.repo_path, **args),
            "get_issue": lambda **args: get_issue(self.gh, self.owner, self.repo, **args),
            "search_prs": lambda **args: search_prs(self.gh, self.owner, self.repo, **args),
            "get_pr_diff": lambda **args: get_pr_diff(self.gh, self.owner, self.repo, **args),
            "get_pr_comments": lambda **args: get_pr_comments(self.gh, self.owner, self.repo, **args),
            "search_issues": lambda **args: search_issues(self.gh, self.owner, self.repo, **args),
        }

    def _log_call(self, name: str, arguments: dict) -> None:
        try:
            serialized_args = json.dumps(arguments, default=str)
        except TypeError:
            serialized_args = str(arguments)
        logger.info("Tool call: %s args=%s", name, serialized_args[:500])
