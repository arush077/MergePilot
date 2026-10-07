import time
import requests


def build_session(token: str = "") -> requests.Session:
    """Create a GitHub API session.

    ── Token paths ──────────────────────────────────────────────────────
    Web path: per-user token → Authorization header for this run only.
    CLI path: token is empty → unauthenticated (public repos).
    """
    session = requests.Session()
    session.headers.update({"Accept": "application/vnd.github+json"})
    if token:
        session.headers.update({
            "Authorization": f"Bearer {token}"
        })
    return session


def parse_owner_repo(owner_repo: str) -> tuple[str, str]:
    """Split 'owner/repo' into its parts."""
    if "/" not in owner_repo:
        raise ValueError(f"Invalid repo: {owner_repo}")
    return owner_repo.split("/", 1)


def get_default_branch(owner: str, repo: str, session: requests.Session) -> str:
    url = f"https://api.github.com/repos/{owner}/{repo}"
    resp = rate_limited_get(url, session)
    return resp.json()["default_branch"]


def list_repo_files(owner: str, repo: str, branch: str, session: requests.Session) -> list[dict]:
    url = (f"https://api.github.com/repos/{owner}/{repo}"
           f"/git/trees/{branch}?recursive=1")
    resp = rate_limited_get(url, session)
    return [item for item in resp.json().get("tree", []) if item["type"] == "blob"]


def fetch_raw_file(owner: str, repo: str, path: str, branch: str, session: requests.Session) -> str | None:
    """Fetch file from raw.githubusercontent.com. Returns None on 404."""
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
    resp = session.get(url)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.text


def rate_limited_get(url: str, session: requests.Session, attempt: int = 0, max_attempts: int = 3) -> requests.Response:
    """GET with rate-limit detection + exponential backoff (max 3 attempts)."""
    resp = session.get(url)
    remaining = resp.headers.get("X-RateLimit-Remaining")

    if resp.status_code == 429 or (
        resp.status_code == 403 and remaining is not None and int(remaining) == 0
    ):
        reset_ts = int(resp.headers.get("X-RateLimit-Reset", 0))
        wait = reset_ts - time.time()

        # Reset too far away — fail fast instead of making user wait
        if wait > 120:
            raise RuntimeError(
                f"GitHub API rate limit exceeded. Resets in {wait:.0f}s "
                f"({int(wait/60)} min). Try again later."
            )

        if attempt >= max_attempts:
            raise RuntimeError(
                f"GitHub API rate limit exceeded — failed after {max_attempts} "
                f"retries. Try again later."
            )

        wait = max(wait, 1)
        print(f"  [GitHub] Rate limited — waiting {wait:.0f}s (attempt {attempt+1}/{max_attempts})...")
        time.sleep(wait)
        return rate_limited_get(url, session, attempt + 1, max_attempts)

    resp.raise_for_status()
    return resp