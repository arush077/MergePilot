SYSTEM_PROMPT = """\
You are a QA engineer writing tests for a code fix.

Given the original issue and the proposed fix:
- Use the appropriate test framework for the language being tested
  (pytest for Python, Vitest/Jest for JS/TS, RSpec for Ruby, etc.)
- The test file path should follow the project's conventions
  (e.g. tests/test_fix.py for Python, src/Component.test.jsx for React)
- Cover: happy path, edge case, regression

Return ONLY valid JSON:
{
  "test_file": "relative/path/to/test/file",
  "test_code": "complete test file content",
  "description": "What each test covers"
}"""


def build_test_writer_prompt(issue: dict, proposed_fix: dict[str, str]) -> str:
    title = issue.get("title", "")
    body = issue.get("body", "")
    parts = [f"## Issue\n{title}\n\n{body}\n"]
    parts.append("## Proposed fix")
    for filepath, content in proposed_fix.items():
        parts.append(f"\n--- {filepath} ---\n```python\n{content}\n```")
    return "\n".join(parts)