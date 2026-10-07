from __future__ import annotations

import json
import re
import time


def parse_response(raw: str) -> dict:
    """Strip markdown fences and parse JSON."""
    text = raw.strip()
    if text.startswith("```"):
        idx = text.find("\n")
        if idx != -1:
            text = text[idx:]
        text = text.rsplit("```", 1)[0].strip()
    return json.loads(text)


_ISSUE_TYPES = frozenset({"bug", "feature", "refactor", "docs"})
_COMPLEXITIES = frozenset({"low", "medium", "high"})


def validate_issue_analysis(parsed: dict) -> dict:
    """Check enum fields and return normalised result."""
    issue_type = parsed.get("issue_type", "").lower()
    if issue_type not in _ISSUE_TYPES:
        raise ValueError(f"Invalid issue_type: '{issue_type}'")

    complexity = parsed.get("complexity", "").lower()
    if complexity not in _COMPLEXITIES:
        raise ValueError(f"Invalid complexity: '{complexity}'")

    return {
        "issue_type": issue_type,
        "affected_areas": parsed.get("affected_areas", []),
        "suggested_files": parsed.get("suggested_files", []),
        "complexity": complexity,
        "summary": parsed.get("summary", ""),
    }


def chunk_file(content: str, filepath: str) -> list[dict]:
    """Return the entire file as a single chunk (language-agnostic)."""
    lines = content.splitlines()
    return [{
        "file": filepath,
        "name": "<module>",
        "type": "module",
        "start_line": 1,
        "end_line": len(lines),
        "content": content
    }]


def extract_lines(content: str, line_spec: str) -> str:
    """Extract a line range (e.g. '12-45') from file content."""
    parts = line_spec.split("-")
    try:
        start, end = int(parts[0]), int(parts[1])
        all_lines = content.splitlines()
        return "\n".join(all_lines[start - 1:end])
    except (ValueError, IndexError):
        return content


def validate_snippet(snippet: str, filepath: str) -> bool:
    if filepath.endswith(".py"):
        try:
            compile(snippet, "<fix>", "exec")
            return True
        except SyntaxError:
            return False
    return True


# Groq TPM rejection: "Limit 8000, Used 7600, Requested 950" (transient —
# window nearly full) or "Limit 8000, Requested 8128" (deterministic —
# request alone exceeds the plan).
_TPM_LIMIT_RE = re.compile(
    r"Limit\s+(\d+),\s+(?:Used\s+\d+,\s+)?Requested\s+(\d+)"
)
_RETRY_IN_RE = re.compile(r"try again in\s+([\d.]+)\s*s")


def _create_with_tpm_guard(client, messages, agent_name, max_tokens):
    """chat.completions.create with Groq TPM rate-limit handling.

    Oversized requests (Requested > Limit) fail fast with a clear message —
    a retry can never succeed.  Transient bucket exhaustion waits once for
    the window reset, then re-raises.
    """
    for rl_attempt in range(2):
        try:
            return client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                temperature=0,
                max_tokens=max_tokens,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            if status not in (413, 429):
                raise
            msg = str(exc)
            limit_match = _TPM_LIMIT_RE.search(msg)
            if limit_match and int(limit_match.group(2)) > int(limit_match.group(1)):
                raise ValueError(
                    f"Request too large for Groq plan: "
                    f"{limit_match.group(2)} tokens requested, limit "
                    f"{limit_match.group(1)} TPM — reduce file context "
                    f"or upgrade the Groq plan"
                ) from exc
            if rl_attempt == 1:
                raise
            wait = 60.0
            retry_match = _RETRY_IN_RE.search(msg)
            if retry_match:
                wait = min(float(retry_match.group(1)) + 0.5, 60.0)
            print(
                f"  [{agent_name}] Groq rate limit — waiting {wait:.1f}s "
                f"(attempt {rl_attempt + 1}/2)..."
            )
            time.sleep(wait)


# This function is used to call the LLM with a retry mechanism.
# Currently we retry twice if the response is not valid JSON.
def call_llm_with_retry(
    client,
    messages: list[dict[str, str]],
    state,
    agent_name: str,
    max_tokens: int,
    post_process=None,
) -> dict:
    """Call the Groq chat-completion API with a JSON-parse retry.

    Internal retry loop (max 2 attempts).  If the model wraps the JSON
    in fences or adds commentary, the first parse will fail and we nudge
    it with a stronger instruction.  If the second attempt also fails the
    orchestrator handles the retry.

    ``post_process`` (if given) runs *inside* the try block so that its
    failures (e.g. schema validation) also trigger the re-prompt retry.
    """
    for attempt in range(2):
        response = _create_with_tpm_guard(
            client, messages, agent_name, max_tokens,
        )
        log_usage(state, response, agent_name)
        raw = response.choices[0].message.content or ""
        try:
            parsed = parse_response(raw)
            if post_process is not None:
                return post_process(parsed)
            return parsed
        except (json.JSONDecodeError, ValueError) as exc:
            if attempt == 0:
                # Append the failed raw response as an assistant turn and
                # re-prompt — this changes the context enough to push the
                # model toward valid JSON on the second attempt.
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": (
                        "The previous response was not valid JSON. "
                        "Return ONLY valid JSON matching the schema."
                    ),
                })
                continue
            raise ValueError(
                f"Groq response still invalid after retry: {exc}"
            ) from exc


def log_usage(state, response, agent: str) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    pt = getattr(usage, "prompt_tokens", 0) or 0
    ct = getattr(usage, "completion_tokens", 0) or 0
    tt = getattr(usage, "total_tokens", 0) or 0
    state.usage["prompt_tokens"] += pt
    state.usage["completion_tokens"] += ct
    state.usage["total_tokens"] += tt
    print(f"  [{agent}] tokens: {tt} ({pt}+{ct})")