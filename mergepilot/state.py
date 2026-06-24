from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class AgentState:
    """Shared state that all agents read from and write to."""

    issue: dict
    relevant_files: list[str] = field(default_factory=list)
    code_context: dict[str, str] = field(default_factory=dict)
    proposed_fix: dict[str, str] = field(default_factory=dict)
    test_code: str = ""
    pr_url: str = ""
    status: str = "pending"
    error: str | None = None
    retry_count: int = 0
