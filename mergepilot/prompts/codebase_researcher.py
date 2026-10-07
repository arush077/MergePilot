SYSTEM_PROMPT = """\
You are a codebase researcher. Given a GitHub issue and code chunks,
identify which chunks are relevant to fixing the issue.

Return ONLY valid JSON:
{
  "relevant_chunks": [
    {
      "file": "path/to/file.py",
      "name": "function_name",
      "lines": "12-45",
      "reason": "why this chunk is relevant"
    }
  ]
}

If nothing is relevant, return {"relevant_chunks": []}."""


def build_codebase_researcher_prompt(issue: dict, chunks: list[dict]) -> str:
    title = issue.get("title", "")
    body = issue.get("body", "")
    parts = [f"## Issue\n{title}\n\n{body}\n"]

    parts.append("## Code chunks")
    for c in chunks:
        parts.append(
            f"\n- {c['file']} — {c['type']}:{c['name']} "
            f"(lines {c['start_line']}-{c['end_line']})"
        )
    return "\n".join(parts)