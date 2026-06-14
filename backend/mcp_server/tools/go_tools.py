import subprocess
import time


def run_tests(
    repo_path: str,
    package: str = "./...",
    verbose: bool = True,
    timeout_seconds: int = 60,
) -> dict:
    command = ["go", "test"]
    if verbose:
        command.append("-v")
    command.append(package)

    started_at = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=repo_path,
            timeout=timeout_seconds,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return {
            "passed": False,
            "output": f"TIMEOUT after {timeout_seconds}s",
            "failed_tests": [],
            "duration_seconds": float(timeout_seconds),
        }

    duration = time.monotonic() - started_at
    output = f"{result.stdout}{result.stderr}"
    failed_tests = [line for line in output.split("\n") if line.startswith("--- FAIL:")]
    return {
        "passed": result.returncode == 0,
        "output": output[-10_000:],
        "failed_tests": failed_tests,
        "duration_seconds": duration,
    }


def run_vet(repo_path: str, package: str = "./...") -> dict:
    result = subprocess.run(
        ["go", "vet", package],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return {
        "passed": result.returncode == 0,
        "output": result.stderr,
        "issues": [line for line in result.stderr.splitlines() if line.strip()],
    }


def run_build(repo_path: str, package: str = "./...") -> dict:
    result = subprocess.run(
        ["go", "build", package],
        cwd=repo_path,
        capture_output=True,
        text=True,
    )
    return {"passed": result.returncode == 0, "output": result.stderr}
