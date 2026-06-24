from mergepilot.state import AgentState


def analyze_issue(state: AgentState) -> None:
    """Extract intent and guess which files need changing."""
    print(
        f"[Issue Analyzer] Parsing issue #{state.issue.get('number')}:"
        f" {state.issue.get('title')}"
    )
    state.relevant_files = ["src/main.py", "src/utils.py"]
    state.status = "researching"


def research_codebase(state: AgentState) -> None:
    """Find relevant code snippets for the files identified above."""
    print(
        f"[Codebase Researcher] Searching {len(state.relevant_files)} file(s)..."
    )
    state.code_context = {
        "src/main.py": "def main():\n    print('hello')",
        "src/utils.py": "def helper():\n    return 42",
    }
    state.status = "drafting"


def draft_fix(state: AgentState) -> None:
    """Write the actual code change based on research findings."""
    print(
        f"[Fix Drafter] Writing changes for {len(state.code_context)} file(s)..."
    )
    state.proposed_fix = {
        "src/main.py": "def main():\n    print('hello world')",
    }
    state.status = "testing"


def write_tests(state: AgentState) -> None:
    """Author tests that validate the proposed fix."""
    print("[Test Writer] Writing tests for proposed fix...")
    state.test_code = (
        "def test_main():\n"
        "    from src.main import main\n"
        "    assert main() is None\n"
    )
    state.status = "opening_pr"


def create_pr(state: AgentState) -> None:
    """Package everything into a pull request."""
    print("[PR Creator] Opening pull request...")
    state.pr_url = "https://github.com/owner/repo/pull/1"
    state.status = "reviewing"


def review_pr(state: AgentState) -> None:
    """Sanity-check the PR before marking the pipeline complete."""
    print(f"[Reviewer] Reviewing PR {state.pr_url}...")
    state.status = "done"
