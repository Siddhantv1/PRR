import httpx

from backend.config import config


def get_issue(gh, owner: str, repo: str, number: int, include_comments: bool = True) -> dict:
    github_repo = gh.get_repo(f"{owner}/{repo}")
    issue = github_repo.get_issue(number)
    result = {
        "number": issue.number,
        "title": issue.title,
        "body": issue.body,
        "state": issue.state,
        "labels": [label.name for label in issue.labels],
        "created_at": str(issue.created_at),
    }
    if include_comments:
        result["comments"] = [
            {
                "author": comment.user.login,
                "body": comment.body,
                "created_at": str(comment.created_at),
            }
            for comment in issue.get_comments()
        ]
    return result


def search_prs(gh, owner: str, repo: str, query: str = "", limit: int = 15) -> list[dict]:
    github_repo = gh.get_repo(f"{owner}/{repo}")
    normalized_query = query.lower()
    results: list[dict] = []

    for pr in github_repo.get_pulls(state="closed", sort="updated", direction="desc"):
        if len(results) >= limit:
            break
        if pr.merged_at is None:
            continue
        searchable = f"{pr.title or ''} {pr.body or ''}".lower()
        if normalized_query and normalized_query not in searchable:
            continue
        results.append(
            {
                "number": pr.number,
                "title": pr.title,
                "body": (pr.body or "")[:500],
                "author": pr.user.login,
                "merged_at": str(pr.merged_at),
                "additions": pr.additions,
                "deletions": pr.deletions,
            }
        )

    return results


def get_pr_diff(gh, owner: str, repo: str, number: int) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    response = httpx.get(
        url,
        headers={
            "Accept": "application/vnd.github.v3.diff",
            "Authorization": f"Bearer {config.GITHUB_TOKEN}",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.text[:20_000]


def get_pr_comments(gh, owner: str, repo: str, number: int) -> list[dict]:
    github_repo = gh.get_repo(f"{owner}/{repo}")
    issue = github_repo.get_issue(number)
    pr = github_repo.get_pull(number)
    comments = [
        {
            "author": comment.user.login,
            "body": comment.body,
            "created_at": str(comment.created_at),
        }
        for comment in issue.get_comments()
    ]
    comments.extend(
        {
            "author": comment.user.login,
            "body": comment.body,
            "created_at": str(comment.created_at),
            "path": comment.path,
            "line": comment.line,
        }
        for comment in pr.get_review_comments()
    )
    return comments


def search_issues(
    gh,
    owner: str,
    repo: str,
    query: str = "",
    state: str = "closed",
    limit: int = 10,
) -> list[dict]:
    github_repo = gh.get_repo(f"{owner}/{repo}")
    normalized_query = query.lower()
    results: list[dict] = []

    for issue in github_repo.get_issues(state=state):
        if len(results) >= limit:
            break
        searchable = f"{issue.title or ''} {issue.body or ''}".lower()
        if normalized_query and normalized_query not in searchable:
            continue
        results.append(
            {
                "number": issue.number,
                "title": issue.title,
                "body": (issue.body or "")[:300],
                "state": issue.state,
                "labels": [label.name for label in issue.labels],
            }
        )

    return results
