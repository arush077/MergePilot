SYSTEM_PROMPT = """\
You are writing a pull request description.

Given the original issue, the proposed fix, and the tests, write a clear
PR description in markdown explaining what was changed and why.

Return ONLY valid JSON:
{
  "body": "PR description in markdown"
}"""


def build_pr_creator_prompt(issue: dict, proposed_fix: dict[str, str],
                          test_code: str) -> str:
    title = issue.get("title", "")
    body = issue.get("body", "")
    parts = [f"## Issue\n{title}\n\n{body}\n"]
    parts.append("## Proposed fix")
    for filepath, content in proposed_fix.items():
        parts.append(f"\n--- {filepath} ---\n```python\n{content}\n```")
    parts.append(f"\n## Tests\n```python\n{test_code}\n```")
    return "\n".join(parts)