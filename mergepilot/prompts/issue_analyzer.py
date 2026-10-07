# ── Issue Analyzer System Prompt ────────────────────────────────────────────
#
# Why we put "Return ONLY valid JSON" at the very top:
#   LLMs weight early tokens most heavily.  Stating the constraint first
#   dramatically reduces fence-wrapping or extra commentary.
#
# Why we embed the schema inline:
#   Giving the exact key names (`issue_type`, `affected_areas`, ...) means the
#   model mirrors them rather than inventing synonyms.
#
# Why temperature=0:
#   Deterministic output is essential for json.loads() to succeed reliably.
#
# Why max_tokens=512:
#   The response is ~200 tokens at most — no point allocating more.
#
SYSTEM_PROMPT = """\
Return ONLY valid JSON. No markdown, no explanation.

{
  "issue_type": "bug" | "feature" | "refactor" | "docs",
  "affected_areas": ["list", "of", "affected", "modules"],
  "suggested_files": ["file/paths", "that", "might", "need", "changes"],
  "complexity": "low" | "medium" | "high",
  "summary": "One-sentence summary of what needs to be done."
}"""


def build_issue_analyzer_prompt(issue: dict) -> str:
    title = issue.get("title", "")
    body = issue.get("body", "")
    return f"## Title\n{title}\n\n## Body\n{body}"