"""Reproducible dev evaluation; answer keys never enter model prompts."""
import json
import math
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from statistics import median

from src.agent import create_agent, open_database
from src.cli import arguments


def matches(actual: list, expected: list, ordered: bool = False) -> bool:
    """Ignore aliases, preserve duplicates, tolerate decimal rounding and tied ranks."""
    def equal(a, b):
        if len(a) != len(b):
            return False
        return all(math.isclose(x, y, rel_tol=1e-9, abs_tol=0.005)
                   if isinstance(x, (int, float)) and isinstance(y, (int, float))
                   else x == y for x, y in zip(a, b))

    remaining = [tuple(row.values()) for row in expected]
    if len(actual) != len(remaining):
        return False
    if ordered:
        # Ranked dev questions sort on their final numeric measure; ties may swap.
        if [row[-1] for row in actual] != sorted((row[-1] for row in actual), reverse=True):
            return False
    for row in actual:
        index = next((i for i, other in enumerate(remaining) if equal(row, other)), None)
        if index is None:
            return False
        remaining.pop(index)
    return True


def main() -> None:
    parser = arguments("Evaluate the agent against all ten development questions.")
    parser.add_argument("--baseline", action="store_true", help="Minimal prompt, no schema or repair")
    parser.add_argument("--output", default="dev_answers.json")
    args = parser.parse_args()
    questions = json.loads(Path("data/dev_questions.json").read_text())
    gold = {q["id"]: q for q in json.loads(Path("data/dev_questions_with_answers.json").read_text())}
    answers, details = {}, {}
    setup_error = None
    model = args.model
    with closing(open_database(args.db)) as conn:
        try:
            agent = create_agent(conn, args.model, args.descriptions, args.baseline)
            model = agent.model
        except (ValueError, OSError) as exc:
            setup_error = str(exc)
        for question in questions:
            qid = question["id"]
            if setup_error:
                answers[qid] = {"sql": "", "answer": f"Not run: {setup_error}"}
                details[qid] = {"status": "not_run", "error": setup_error}
                continue
            agent.history.clear()  # Independent benchmark questions, no cross-question hints.
            result = agent.ask(question["question"])
            passed = not result.error and not result.truncated and matches(
                result.rows, gold[qid]["expected_result"], ordered=qid in {"q_008", "q_009"})
            answers[qid] = {"sql": result.sql, "answer": result.answer}
            details[qid] = {**asdict(result), "status": "pass" if passed else "fail"}
            print(f"{qid}: {details[qid]['status']} ({result.seconds:.2f}s)", flush=True)
    attempted = [r for r in details.values() if r["status"] != "not_run"]
    report = {
        "model": model, "baseline": args.baseline, "questions": len(questions),
        "attempted": len(attempted),
        "passed": sum(r["status"] == "pass" for r in attempted),
        "p50_seconds": median(r["seconds"] for r in attempted) if attempted else None,
        "input_tokens": sum(r["input_tokens"] for r in attempted),
        "output_tokens": sum(r["output_tokens"] for r in attempted),
        "results": details,
    }
    output = Path(args.output)
    output.write_text(json.dumps(answers, indent=2) + "\n")
    report_path = output.with_name(output.stem + "_report.json")
    report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(f"Saved {output} and {report_path}. Attempted {len(attempted)}/10; passed {report['passed']}.")
    if setup_error:
        parser.exit(1, setup_error + "\n")
    if report["passed"] != len(questions):
        parser.exit(1)


if __name__ == "__main__":
    main()
