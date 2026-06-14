import asyncio
import os
import sys
from pathlib import Path

os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("GITHUB_TOKEN", "test")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.mcp_server.server import ToolServer


COBRA_REPO_PATH = os.environ.get("COBRA_REPO_PATH", "/tmp/repos/cobra")


async def main():
    repo_path = Path(COBRA_REPO_PATH)
    if not repo_path.is_dir():
        raise FileNotFoundError(
            f"Cobra clone not found at {repo_path}. Set COBRA_REPO_PATH to a real cobra clone."
        )

    tool_server = ToolServer(str(repo_path), "spf13", "cobra")

    files_result = await tool_server.call_tool(
        "list_files",
        {"directory": "", "recursive": False},
    )
    print("list_files result:")
    print(files_result)

    read_path = "README.md" if (repo_path / "README.md").is_file() else "go.mod"
    read_result = await tool_server.call_tool("read_file", {"path": read_path})
    print(f"\nread_file {read_path} result:")
    print(read_result)


if __name__ == "__main__":
    asyncio.run(main())
