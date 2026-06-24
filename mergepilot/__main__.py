from mergepilot.orchestrator import Orchestrator


def main() -> None:
    sample_issue = {
        "title": "Fix greeting message",
        "body": "The main function prints 'hello' but should print 'hello world'",
        "number": 42,
        "repo": "owner/repo",
    }

    orchestrator = Orchestrator(max_retries=3)
    final_state = orchestrator.run(sample_issue)

    print("\n=== Pipeline finished ===")
    print(f"  Status:        {final_state.status}")
    print(f"  Error:         {final_state.error}")
    print(f"  Retries:       {final_state.retry_count}")
    print(f"  PR URL:        {final_state.pr_url}")
    print(f"  Relevant files:{final_state.relevant_files}")
    print(f"  Test written:  {bool(final_state.test_code)}")


if __name__ == "__main__":
    main()
