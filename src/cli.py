"""Interactive terminal entry point."""
import argparse
import sqlite3
from contextlib import closing

from src.agent import create_agent, open_database


def arguments(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--db", default="data/financial.sqlite")
    parser.add_argument("--descriptions", default="data/database_description")
    parser.add_argument("--model", help="Fireworks model ID; overrides FIREWORKS_MODEL")
    return parser


def main() -> None:
    parser = arguments("Ask questions about the banking database.")
    args = parser.parse_args()
    try:
        with closing(open_database(args.db)) as conn:
            agent = create_agent(conn, args.model, args.descriptions)
            print(f"Model: {agent.model}\nAsk a question; /reset clears context; exit or quit ends the session.")
            while True:
                try:
                    question = input("\nYou> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye.")
                    break
                if question.lower() in {"exit", "quit"}:
                    break
                if question == "/reset":
                    agent.history.clear()
                    print("Conversation cleared.")
                    continue
                if not question:
                    continue
                try:
                    result = agent.ask(question)
                except KeyboardInterrupt:
                    print("\nQuery cancelled.")
                    continue
                print(f"\nSQL:\n{result.sql or '(none)'}\n\n{result.answer}")
                print(f"{result.seconds:.2f}s | {result.attempts} model call(s)")
    except (ValueError, OSError, sqlite3.Error) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
