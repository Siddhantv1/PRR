import git


def git_diff(repo_path: str, staged: bool = False) -> str:
    repo = git.Repo(repo_path)
    diff = repo.git.diff("--cached") if staged else repo.git.diff("HEAD")
    return diff or "No changes."


def git_log(repo_path: str, path: str | None = None, limit: int = 10) -> list[dict]:
    repo = git.Repo(repo_path)
    commits = repo.iter_commits(paths=path, max_count=limit)
    return [
        {
            "hash": commit.hexsha[:8],
            "message": commit.message.strip()[:120],
            "author": commit.author.name,
            "date": str(commit.authored_datetime.date()),
            "files": list(commit.stats.files.keys())[:10],
        }
        for commit in commits
    ]


def git_status(repo_path: str) -> dict:
    repo = git.Repo(repo_path)
    return {
        "modified": [item.a_path for item in repo.index.diff(None)],
        "staged": [item.a_path for item in repo.index.diff("HEAD")],
        "untracked": repo.untracked_files,
    }


def git_blame(
    repo_path: str,
    path: str,
    line_start: int = 1,
    line_end: int | None = None,
) -> list[dict]:
    repo = git.Repo(repo_path)
    effective_line_end = line_end if line_end is not None else line_start + 30
    blame_entries = repo.blame(None, path)
    results: list[dict] = []
    current_line = 1

    for commit, lines in blame_entries:
        for line in lines:
            if line_start <= current_line <= effective_line_end:
                results.append(
                    {
                        "line": current_line,
                        "hash": commit.hexsha[:8],
                        "author": commit.author.name,
                        "content": line,
                    }
                )
            if current_line > effective_line_end:
                return results
            current_line += 1

    return results
