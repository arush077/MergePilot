from __future__ import annotations

import base64
import json
import os
import re
from dotenv import load_dotenv
from groq import Groq
import requests

from mergepilot.state import AgentState
from mergepilot.common import (
    log_usage,
    parse_response,
    validate_issue_analysis,
    chunk_file,
    validate_snippet,
    call_llm_with_retry,
)
from mergepilot.github import (
    build_session,
    parse_owner_repo,
    get_default_branch,
    list_repo_files,
    fetch_raw_file,
)
from mergepilot.prompts import (
    ISSUE_ANALYZER_SYSTEM_PROMPT, build_issue_analyzer_prompt,
    CODEBASE_RESEARCHER_SYSTEM_PROMPT, build_codebase_researcher_prompt,
    FIX_DRAFTER_SYSTEM_PROMPT, build_fix_drafter_prompt,
    TEST_WRITER_SYSTEM_PROMPT, build_test_writer_prompt,
    PR_CREATOR_SYSTEM_PROMPT, build_pr_creator_prompt,
)

load_dotenv()


def _groq_client() -> Groq:
    """Create a Groq client, failing fast if the API key is missing."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("LLM API key environment variable is not set")
    return Groq(api_key=api_key)


def analyze_issue(state: AgentState) -> None:
    """Extract structured info from a GitHub issue via the Groq API."""
    client = _groq_client()

    print(
        f"[Issue Analyzer] Parsing issue #{state.issue.get('number')}:"
        f" {state.issue.get('title')}"
    )

    user_prompt = build_issue_analyzer_prompt(state.issue)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": ISSUE_ANALYZER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    # Internal retry loop (max 2 attempts) lives in call_llm_with_retry.
    # validate_issue_analysis runs inside its try block, so an invalid enum
    # value triggers the same re-prompt retry as a JSON parse failure.
    validated = call_llm_with_retry(
        client, messages, state, "analyze_issue", 512,
        post_process=validate_issue_analysis,
    )

    # Updating the state with the response.
    state.relevant_files = validated["suggested_files"]
    state.issue_type = validated["issue_type"]
    state.affected_areas = validated["affected_areas"]
    state.complexity = validated["complexity"]
    state.summary = validated["summary"]
    state.status = "researching"


# ── Codebase Researcher ─────────────────────────────────────────────────────

# Lockfiles are machine-generated — never fetched, even when the issue
# explicitly names one.
_LOCKFILE_NAMES = frozenset({
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Cargo.lock", "poetry.lock", "Pipfile.lock",
    "Gemfile.lock", "composer.lock",
})

# FixDrafter's total request must fit Groq's free-tier TPM (8,000/min,
# shared with the analyzer/researcher calls made in the same minute) —
# budget the whole prompt, not just the code.  Issue-named target files
# are checked against the per-file cap up front and fail the pipeline
# loudly (a size-413 from Groq can never succeed on retry).
_MAX_FIX_PROMPT_TOKENS = 5000
_MAX_FILE_TOKENS = 4000


def _estimate_tokens(text: str) -> int:
    """Conservative token estimate (~3 chars/token for source code).

    Intentionally overestimates rather than accidentally allowing an
    oversized request through to Groq's 413 check.
    """
    return max(1, len(text) // 3)


_ISSUE_PATH_RE = re.compile(
    r"(?:[A-Za-z0-9_.\-]+/)*[A-Za-z0-9_.\-]+\."
    r"(?:py|jsx|tsx|js|ts|json|md|txt|yml|yaml|toml|cfg|ini|css|scss"
    r"|less|html|htm|xml|csv|env|cpp|cs|kt|rs|go|java|rb|php|c|h"
    r"|swift|scala)\b"
)


def _is_lockfile(filepath: str) -> bool:
    return filepath.rsplit("/", 1)[-1] in _LOCKFILE_NAMES


def _extract_issue_paths(issue: dict) -> list[str]:
    """Repo-relative file paths explicitly mentioned in the issue text.

    These are the guaranteed fix targets, so they are force-fetched and
    always sent to FixDrafter first — independent of the (blind) research
    selection.
    """
    text = f"{issue.get('title', '')}\n{issue.get('body') or ''}"
    paths: list[str] = []
    for match in _ISSUE_PATH_RE.findall(text):
        path = match.removeprefix("./")
        if path not in paths:
            paths.append(path)
    return paths


def research_codebase(state: AgentState) -> None:
    """Fetch files from the target repo, chunk them, and let Groq identify
    which snippets are relevant to the issue."""
    groq_client = _groq_client()
    session = build_session(state.github_token)

    owner, repo = parse_owner_repo(state.issue.get("repo", ""))

    print(f"[Codebase Researcher] Target: {owner}/{repo}")
    print(f"  Suggested files: {state.relevant_files}")

    # ---- 1. Determine the default branch ----
    branch = get_default_branch(owner, repo, session)
    print(f"  Branch: {branch}")

    issue_paths = _extract_issue_paths(state.issue)

    # ---- 2. Try fetching the suggested files first ----
    fetched: dict[str, str] = {}
    for filepath in state.relevant_files:
        if _is_lockfile(filepath):
            print(f"  [skip lockfile] {filepath}")
            continue
        content = fetch_raw_file(owner, repo, filepath, branch, session)
        if content is None:
            print(f"  [!] {filepath} not found — skipping")
            continue
        fetched[filepath] = content
        print(f"  [ok] {filepath}")

    # ---- 3. Force-fetch paths mentioned in the issue itself ----
    # (issue_analyzer frequently hallucinates paths and omits the one the
    # user explicitly named — this layer guarantees the real target arrives.)
    for filepath in issue_paths:
        if filepath in fetched:
            continue
        if _is_lockfile(filepath):
            print(f"  [skip lockfile] {filepath}")
            continue
        content = fetch_raw_file(owner, repo, filepath, branch, session)
        if content is None:
            print(f"  [!] {filepath} not found — skipping")
            continue
        fetched[filepath] = content
        print(f"  [issue] {filepath}")

    # Issue-named files are the guaranteed fix targets — refuse to continue
    # when one is too large to send whole (loud failure, not truncation).
    issue_tokens = 0
    for filepath in issue_paths:
        content = fetched.get(filepath, "")
        tokens = _estimate_tokens(content)
        if tokens > _MAX_FILE_TOKENS:
            state.status = "failed"
            state.error = (
                f"File too large for tier budget: {filepath} "
                f"({tokens} est. tokens > {_MAX_FILE_TOKENS} token limit)"
            )
            return
        issue_tokens += tokens

    # Combined issue-named files must also fit the whole-prompt budget —
    # otherwise the request is oversized even with everything else removed.
    if issue_tokens > _MAX_FIX_PROMPT_TOKENS:
        state.status = "failed"
        state.error = (
            f"Combined issue-named files too large for tier budget: "
            f"({issue_tokens} est. tokens > {_MAX_FIX_PROMPT_TOKENS} "
            f"token limit)"
        )
        return

    _TEXT_EXTENSIONS = frozenset({
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css",
        ".scss", ".less", ".txt", ".md", ".rst", ".json", ".yaml",
        ".yml", ".toml", ".cfg", ".ini", ".csv", ".xml", ".svg",
        ".env", ".gitignore", ".dockerfile",
        ".java", ".cpp", ".c", ".h", ".hpp", ".cs", ".go", ".rs",
        ".rb", ".php", ".swift", ".kt", ".scala",
    })

    # ---- 4. Fall back to listing the repo if nothing matched ----
    if not fetched:
        print("  No suggested files found — listing repo contents...")
        tree = list_repo_files(owner, repo, branch, session)
        text_files = [
            f for f in tree
            if any(f["path"].endswith(ext) for ext in _TEXT_EXTENSIONS)
            and not _is_lockfile(f["path"])
        ]
        for entry in text_files:
            content = fetch_raw_file(owner, repo, entry["path"],
                                      branch, session)
            if content:
                fetched[entry["path"]] = content
                print(f"  [ok] {entry['path']}")

    if not fetched:
        state.status = "failed"
        state.error = "No files could be fetched from the repository"
        return

    # ---- 4. Chunk each file (one chunk per file) ----
    all_chunks: list[dict] = []
    for filepath, content in fetched.items():
        all_chunks.extend(chunk_file(content, filepath))
    print(f"  Created {len(all_chunks)} chunks across {len(fetched)} file(s)")

    # ---- 5. Send chunks + issue to Groq for relevance filtering ----
    user_prompt = build_codebase_researcher_prompt(state.issue, all_chunks)

    messages: list[dict[str, str]] = [
        {"role": "system", "content": CODEBASE_RESEARCHER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    parsed = call_llm_with_retry(
        groq_client, messages, state, "codebase_researcher", 1024,
    )
    relevant: list[dict] = parsed.get("relevant_chunks", [])

    # ---- 6. Build code_context: FULL contents, issue-named files first ----
    # The surgical matcher validates quotes against state.original_files,
    # so FixDrafter must see the same bytes — no line-range slicing.
    issue_files = [fp for fp in issue_paths if fp in fetched]
    picks: list[str] = []
    for chunk_info in relevant:
        filepath = chunk_info.get("file", "")
        if (
            filepath
            and filepath in fetched
            and filepath not in issue_files
            and filepath not in picks
        ):
            picks.append(filepath)

    code_context: dict[str, str] = {}
    # Budget covers code tokens only — _MAX_FIX_PROMPT_TOKENS leaves
    # headroom for the system prompt + issue + instructions (~1k tokens).
    total_tokens = 0

    # Issue-named targets are never dropped (their per-file cap was
    # already enforced above).
    for filepath in issue_files:
        content = fetched[filepath]
        total_tokens += _estimate_tokens(content)
        code_context[filepath] = content

    for filepath in picks:
        content = fetched[filepath]
        tokens = _estimate_tokens(content)
        if tokens > _MAX_FILE_TOKENS:
            print(
                f"  [!] Skipping {filepath} — too large "
                f"({tokens} est. tokens > {_MAX_FILE_TOKENS})"
            )
            state.low_confidence = True
            continue
        if total_tokens + tokens > _MAX_FIX_PROMPT_TOKENS:
            print(
                f"  [!] Skipping {filepath} — prompt token budget "
                f"({_MAX_FIX_PROMPT_TOKENS}) reached"
            )
            state.low_confidence = True
            continue
        total_tokens += tokens
        code_context[filepath] = content

    # ---- 7. Flag low confidence if nothing was relevant ----
    if not relevant:
        state.low_confidence = True
        print("  Warning: Groq returned no relevant chunks (low confidence)")

    state.code_context = code_context
    state.original_files = dict(fetched)
    state.status = "drafting"
    print(f"  Selected {len(code_context)} full file(s) for FixDrafter")


# This function is used by draft_fix to apply the surgical changes to the original files.
def _apply_surgical_changes(
    original_files: dict[str, str],
    changes: list[dict],
) -> dict[str, str]:
    modified: dict[str, str] = {}
    for change in changes:
        filepath = change.get("file", "")
        action = change.get("action", "edit")  # default: edit

        if not filepath:
            continue

        if action == "create":
            content = change.get("content", "")
            if not content:
                print(f"  [!] Create action for {filepath} missing content — skipping")
                continue
            if filepath in original_files:
                print(f"  [!] File {filepath} already exists — skipping create")
                continue
            if filepath.endswith(".py") and not validate_snippet(content, filepath):
                print(f"  [!] Syntax error in new file {filepath}")
                continue
            modified[filepath] = content
            continue

        # --- edit action (existing logic) ---
        original = change.get("original", "")
        replacement = change.get("replacement", "")
        if not original:
            continue
        if filepath not in original_files:
            print(f"  [!] File {filepath} not in original_files — skipping")
            continue
        content = original_files[filepath]
        idx = content.find(original)
        if idx == -1:
            print(f"  [!] Could not find original text in {filepath} — skipping")
            continue
        new_content = content[:idx] + replacement + content[idx + len(original):]
        if new_content != content:
            modified[filepath] = new_content
    return modified


def draft_fix(state: AgentState) -> None:
    groq_client = _groq_client()

    if not state.code_context:
        state.status = "failed"
        state.error = "No code context available — cannot draft a fix"
        return

    print(f"[Fix Drafter] Drafting fix for {len(state.code_context)} file(s)...")

    user_prompt = build_fix_drafter_prompt(state.issue, state.code_context)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": FIX_DRAFTER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    parsed = call_llm_with_retry(
        groq_client, messages, state, "fix_drafter", 4096,
    )

    if parsed.get("cannot_fix", False):
        state.status = "failed"
        state.error = parsed.get("reason", "FixDrafter could not determine a fix")
        return

    changes = parsed.get("changes", [])
    if not changes:
        state.status = "failed"
        state.error = "FixDrafter returned no changes"
        return

    applied = _apply_surgical_changes(state.original_files, changes)

    if not state.original_files:
        state.low_confidence = True

    if not applied:
        state.status = "failed"
        state.error = (
            f"FixDrafter could not apply any surgical changes — "
            f"none of the {len(changes)} change(s)"
            f" matched the original file content"
        )
        return

    for change in changes:
        fp = change.get("file", "")
        action = change.get("action", "edit")
        if action == "create":
            content = change.get("content", "")
            if fp.endswith(".py") and content and not validate_snippet(content, fp):
                print(f"  [!] Syntax error in new file {fp}")
                state.low_confidence = True
        else:
            rep = change.get("replacement", "")
            if fp.endswith(".py") and rep and not validate_snippet(rep, fp):
                print(f"  [!] Syntax error in {fp}")
                state.low_confidence = True

    state.proposed_fix = applied
    state.status = "testing"
    diff = sum(1 for c in changes if c.get("file"))
    print(f"  {len(changes)} surgical change(s) across {diff} file(s)")


def write_tests(state: AgentState) -> None:
    """Generate tests via Groq, but only if the issue explicitly asks for them."""
    groq_client = _groq_client()

    if not state.proposed_fix:
        state.status = "failed"
        state.error = "No proposed fix — cannot write tests"
        return

    # Only generate tests if the issue explicitly mentions them.
    title = (state.issue.get("title") or "").lower()
    body = (state.issue.get("body") or "").lower()
    if "test" not in title and "test" not in body:
        print("[Test Writer] No tests requested — skipping")
        state.status = "opening_pr"
        return

    print(f"[Test Writer] Writing tests for {len(state.proposed_fix)} file(s)...")

    user_prompt = build_test_writer_prompt(state.issue, state.proposed_fix)
    messages: list[dict[str, str]] = [
        {"role": "system", "content": TEST_WRITER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    parsed = call_llm_with_retry(
        groq_client, messages, state, "test_writer", 2048,
    )

    state.test_file_path = parsed.get("test_file", "")
    state.test_code = parsed.get("test_code", "")
    state.status = "opening_pr"
    print(f"  Tests: {len(state.test_code)} chars → {state.test_file_path}")


def _commit_file(
    session: requests.Session,
    owner: str,
    repo: str,
    filepath: str,
    content: str,
    branch: str,
    message: str,
) -> None:
    """Create or update one file on the branch via the Contents API."""
    put_url = (f"https://api.github.com/repos/{owner}/{repo}"
               f"/contents/{filepath}")

    sha = None
    get_resp = session.get(put_url, params={"ref": branch})
    if get_resp.status_code == 200:
        sha = get_resp.json()["sha"]

    body = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha

    resp = session.put(put_url, json=body)
    resp.raise_for_status()
    print(f"  Committed {filepath}")


def create_pr(state: AgentState) -> None:
    """Create a branch, commit fix + tests, and open a PR.

    ── Token resolution ──────────────────────────────────────────────────
    Web path (backend/main.py):
        state.github_token is set → used for this run, never persisted.
    CLI path (python -m mergepilot):
        state.github_token is empty → falls back to GITHUB_TOKEN from .env.
    """
    token = state.github_token or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "GITHUB_TOKEN not set — provide a token via the web UI "
            "or set GITHUB_TOKEN in .env for CLI usage."
        )

    print("[PR Creator] Creating branch, committing files, opening PR...")

    owner, repo = parse_owner_repo(state.issue.get("repo", ""))
    issue_number = state.issue.get("number", 0)

    # Validate the LLM key before any side effects (branch / commits).
    groq_client = _groq_client()

    session = build_session(token)

    # ── 1. Get default branch + latest commit SHA ──
    default_branch = get_default_branch(owner, repo, session)

    ref_url = (f"https://api.github.com/repos/{owner}/{repo}"
               f"/git/refs/heads/{default_branch}")
    resp = session.get(ref_url)
    resp.raise_for_status()
    latest_sha = resp.json()["object"]["sha"]

    # ── 2. Create branch ──
    branch_name = f"mergepilot/fix-{issue_number}"
    print(f"  Branch: {branch_name}")

    create_ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
    resp = session.post(create_ref_url, json={
        "ref": f"refs/heads/{branch_name}",
        "sha": latest_sha,
    })
    if resp.status_code == 422:
        session.delete(
            f"https://api.github.com/repos/{owner}/{repo}"
            f"/git/refs/heads/{branch_name}"
        )
        resp = session.post(create_ref_url, json={
            "ref": f"refs/heads/{branch_name}",
            "sha": latest_sha,
        })
    resp.raise_for_status()

    # ── 3. Commit each proposed-fix file ──
    for filepath, content in state.proposed_fix.items():
        _commit_file(
            session, owner, repo, filepath, content, branch_name,
            f"fix: {filepath} — automated fix for #{issue_number}",
        )

    # ── 4. Commit test file ──
    if state.test_code:
        test_path = state.test_file_path or "tests/test_fix.py"
        _commit_file(
            session, owner, repo, test_path, state.test_code, branch_name,
            f"test: add tests for #{issue_number}",
        )

    # ── 5. Generate PR body via Groq ──
    body_prompt = build_pr_creator_prompt(
        state.issue, state.proposed_fix, state.test_code
    )
    body_messages: list[dict[str, str]] = [
        {"role": "system", "content": PR_CREATOR_SYSTEM_PROMPT},
        {"role": "user", "content": body_prompt},
    ]
    body_resp = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=body_messages,
        temperature=0,
        max_tokens=1024,
    )
    log_usage(state, body_resp, "pr_body")
    raw = body_resp.choices[0].message.content or "{}"
    try:
        parsed = parse_response(raw)
        pr_body = parsed.get(
            "body",
            "Automated fix generated by MergePilot."
        )
    except (json.JSONDecodeError, ValueError):
        pr_body = "Automated fix generated by MergePilot."

    # ── 6. Create pull request ──
    pr_create_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
    resp = session.post(pr_create_url, json={
        "title": state.issue.get(
            "title", f"Fix for issue #{issue_number}"
        ),
        "body": pr_body,
        "head": branch_name,
        "base": default_branch,
    })
    resp.raise_for_status()
    pr_data = resp.json()
    pr_number = pr_data["number"]
    state.pr_url = pr_data["html_url"]
    print(f"  PR #{pr_number}: {state.pr_url}")

    # ── 7. Add label to the PR eg : {auto-generated, bug} ──
    labels_url = (f"https://api.github.com/repos/{owner}/{repo}"
                  f"/issues/{pr_number}/labels")
    try:
        session.post(labels_url, json={
            "labels": ["auto-generated", state.issue_type],
        })
    except Exception:
        pass

    state.status = "done"
