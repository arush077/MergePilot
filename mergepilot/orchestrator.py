from mergepilot.state import AgentState
from mergepilot.agents import (
    analyze_issue,
    research_codebase,
    draft_fix,
    write_tests,
    create_pr,
    review_pr,
)


class Orchestrator:
    """Coordinates the multi-agent pipeline: routes state -> agent -> updates state."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

        # Pipeline: status -> (agent_name, agent_fn).
        #
        # Each agent advances `state.status` on success, which selects the
        # next agent on the following loop iteration.  The ordering here
        # defines the overall workflow.
        #
        # Why each routing decision exists:
        #   pending    -> issue_analyzer     : issue is fresh — understand what's being asked.
        #   researching -> codebase_researcher: intent known — find the relevant code.
        #   drafting   -> fix_drafter        : context gathered — write the actual patch.
        #   testing    -> test_writer        : fix exists — back it with tests.
        #   opening_pr -> pr_creator         : change is ready — open the PR.
        #   reviewing  -> reviewer           : final sanity check before marking done.
        self._pipeline: dict[str, tuple[str, callable]] = {
            "pending": ("issue_analyzer", analyze_issue),
            "researching": ("codebase_researcher", research_codebase),
            "drafting": ("fix_drafter", draft_fix),
            "testing": ("test_writer", write_tests),
            "opening_pr": ("pr_creator", create_pr),
            "reviewing": ("reviewer", review_pr),
        }

    def route(self, state: AgentState) -> str | None:
        """Return the agent name to run next, or None if the pipeline is over."""
        if state.status in ("done", "failed"):
            # Terminal states — nothing left to do.
            return None

        entry = self._pipeline.get(state.status)
        if entry is None:
            # Unknown status means something went wrong — bail out.
            state.status = "failed"
            state.error = f"No agent registered for status '{state.status}'"
            return None

        return entry[0]

    def step(self, state: AgentState) -> None:
        """Run the agent matching the current status, handling errors and retries."""
        agent_name = self.route(state)
        if agent_name is None:
            return

        _, agent_fn = self._pipeline[state.status]
        print(f"\n=== Executing: {agent_name} ===")
        try:
            agent_fn(state)
            state.retry_count = 0
            state.error = None
        except Exception as exc:
            state.error = str(exc)
            state.retry_count += 1
            print(
                f"[{agent_name}] Error (attempt "
                f"{state.retry_count}/{self.max_retries}): {exc}"
            )
            if state.retry_count >= self.max_retries:
                state.status = "failed"

    def run(self, issue: dict) -> AgentState:
        """Initialize state and run the pipeline until completion or failure."""
        state = AgentState(issue=issue)
        while state.status not in ("done", "failed"):
            self.step(state)
        return state
