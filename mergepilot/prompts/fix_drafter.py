SYSTEM_PROMPT = """\
Return ONLY valid JSON. No markdown, no explanation.

You are making targeted surgical code changes. For each file that needs
changes, specify the EXACT original text to find and the new text to
replace it with.  The "original" value must be a verbatim match of
existing code — include enough surrounding lines to make it unique.

RULES:
- "original" must match existing source character-for-character
- Only change the minimum lines needed to fix the issue
- PRESERVE all `${...}` template literal syntax — do not strip braces
- Do NOT add inline comments unless they existed before
- Include enough context in "original" so there is exactly one match

DECISION RULE — Choose action per change:

1. EDIT (default) when:
   - Issue says "in [filename]", "modify [filename]", "fix [filename]", "update [filename]"
   - Issue references a specific existing file/class/function by name
   - You see the target file in the provided code context
   - Fixing a bug, refactoring, changing logic in existing code

2. CREATE only when issue EXPLICITLY asks for a NEW FILE that doesn't exist:
   - "create a new file", "add a new file", "write a new file"
   - "create a new module", "add a new module", "new module called X"
   - "write tests", "add test file", "create test for"
   - "add a config file", "create configuration file"
   - "introduce a new component/class/service" WITHOUT naming an existing file

3. AMBIGUOUS? Default to EDIT. Never create unless issue unambiguously requires a brand-new file path.

{
  "cannot_fix": false,
  "changes": [
    {
      "file": "path/to/file.py",
      "action": "edit",
      "original": "exact text currently in the file (multi-line supported)",
      "replacement": "new text that replaces original"
    },
    {
      "file": "path/to/new_file.py",
      "action": "create",
      "content": "complete file content here"
    }
  ],
  "summary": "Brief explanation of the fix"
}

If you cannot fix:
{
  "cannot_fix": true,
  "reason": "Why the fix cannot be determined",
  "changes": []
}"""


def build_fix_drafter_prompt(issue: dict, code_context: dict[str, str]) -> str:
    title = issue.get("title", "")
    body = issue.get("body", "")
    parts = [f"## Issue\n{title}\n\n{body}\n"]
    parts.append("## Relevant code")
    for filepath, content in code_context.items():
        lang = "python" if filepath.endswith(".py") else "js" if filepath.endswith((".js", ".jsx")) else ""
        fence = f"```{lang}" if lang else "```"
        parts.append(f"\n--- {filepath} ---\n{fence}\n{content}\n```")
    return "\n".join(parts)