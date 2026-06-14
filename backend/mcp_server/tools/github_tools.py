import httpx

from backend.config import config


MAX_GITHUB_SEARCH_SCAN = 75
MAX_PR_RESULTS = 8
MAX_PR_DIFF_CHARS = 8_000
MAX_ISSUE_RESULTS = 6
MAX_ISSUE_COMMENTS = 10


def get_issue(
    gh,
    owner: str,
    repo: str,
    number: int,
    include_comments: bool = True,
) -> dict:
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
        comments = sorted(
            issue.get_comments(),
            key=lambda comment: comment.created_at,
        )[-MAX_ISSUE_COMMENTS:]
        result["comments"] = [
            {
                "author": comment.user.login,
                "body": comment.body,
                "created_at": str(comment.created_at),
            }
            for comment in comments
        ]
    return result


def search_prs(
    gh,
    owner: str,
    repo: str,
    query: str = "",
    limit: int = MAX_PR_RESULTS,
) -> list[dict]:
    github_repo = gh.get_repo(f"{owner}/{repo}")
    normalized_query = query.lower()
    limit = min(_positive_int(limit, MAX_PR_RESULTS), MAX_PR_RESULTS)
    results: list[dict] = []
    scanned = 0

    for pr in github_repo.get_pulls(state="closed", sort="updated", direction="desc"):
        scanned += 1
        if scanned > MAX_GITHUB_SEARCH_SCAN:
            break
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
    return response.text[:MAX_PR_DIFF_CHARS]


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
    limit: int = MAX_ISSUE_RESULTS,
) -> list[dict]:
    github_repo = gh.get_repo(f"{owner}/{repo}")
    normalized_query = query.lower()
    limit = min(_positive_int(limit, MAX_ISSUE_RESULTS), MAX_ISSUE_RESULTS)
    results: list[dict] = []
    scanned = 0

    for issue in github_repo.get_issues(state=state):
        scanned += 1
        if scanned > MAX_GITHUB_SEARCH_SCAN:
            break
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


def _positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)
