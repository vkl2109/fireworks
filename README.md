# Fireworks text-to-SQL CLI

A minimal SQLite proof of concept: schema and column documentation → Fireworks SQL generation → read-only execution → terminal results. The CLI and evaluator use the same `Agent.ask()` implementation. Original assessment: [ASSIGNMENT.md](ASSIGNMENT.md).

## Setup and run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). Run from this repository root:

```sh
# Only if data/financial.sqlite is absent:
./setup.sh
uv sync
cp .env.example .env
# Edit .env and supply your FIREWORKS_API_KEY.
uv run cli
# Equivalent:
uv run python -m src.cli
```

`FIREWORKS_API_KEY` is required. `FIREWORKS_MODEL` is optional and defaults to `accounts/fireworks/models/gpt-oss-120b`, verified available through the Fireworks model API on October 2, 2026. The originally suggested 20B model returned HTTP 404. Actual access/availability depends on your Fireworks account. `--model` overrides the environment setting. The API endpoint is `https://api.fireworks.ai/inference/v1`.

```sh
uv run cli --db data/financial.sqlite --descriptions data/database_description
```

Ask “How many bank accounts are located in the Prague region?” and then “What about south Moravia?” SQL, results, elapsed time, and model-call count are displayed. `/reset` clears context; `exit`, `quit`, or EOF ends the session. Ctrl-C cancels input or an active query. Activate `.venv` first if using `python -m src.cli` directly.

## Design choices

- Full schema with foreign keys and compact column descriptions is loaded once. Eight tables fit a simple prompt; retrieval and embeddings add no necessary value at this size.
- JSON Schema output requires one SQL field. SQLite parses and executes a single statement. Its authorizer permits only read operations, with a read-only connection as a second boundary. Extensions, writes, PRAGMAs, and ATTACH are denied.
- Invalid JSON or SQL gets one repair attempt with the error. Network/authentication failures do not trigger SQL repair. SDK retries are disabled; each API call has a 20-second timeout.
- Execution has a two-second deadline checked every 1,000 SQLite VM instructions. Results are capped at 100 rows and truncation is explicit. This bounds normal work but is not a production resource-isolation mechanism.
- Three successful question/SQL pairs support follow-ups. Result rows are never sent to the model. References to prior result values are therefore limited.
- Answers are formatted from actual rows, without a second model call that would add latency, cost, and another source of errors.
- Live schema inspection found ISO dates despite stale CSV hints. The client CSV incorrectly labeled residence as branch location; that description is corrected. Explicit business definitions specify the separate join paths for client residence and account branch geography. These are dataset-specific semantics; another database needs reviewed documentation.

`src/agent.py` owns generation/execution and the shared result object, `src/cli.py` owns terminal interaction, and `src/evaluate.py` owns scoring. Existing `src/utils.py` supplies documentation loading; its unrestricted query helper is not used to execute model SQL.

## Evaluation

```sh
uv run python -m unittest discover -s tests -v
uv run python -m src.evaluate
uv run python -m src.evaluate --baseline --output baseline_answers.json
# Optional: four paid geography/follow-up queries, plus offline checks:
RUN_LIVE_TESTS=1 uv run python -m unittest discover -s tests -v
# Compare another available model using --model accounts/fireworks/models/...
```

Evaluation resets conversation state for each of the ten questions. Only questions, schema, and documentation go to the model; gold SQL and answers are used solely for local scoring. `dev_answers.json` contains generated SQL and readable answers. `dev_answers_report.json` contains individual rows, errors, elapsed seconds, attempts, token usage, model identity, total passes, and median latency. Failures produce a nonzero exit code while preserving all results.

Scoring ignores column aliases, preserves duplicate rows, and allows 0.005 absolute numeric tolerance for rounding. For the two ranked questions it also checks descending order of the final measure, permitting ties in either order. This is a dataset-specific comparator, not a universal SQL-equivalence checker. Truncated results fail scoring.

The baseline uses the customer's minimal question prompt plus the same JSON Schema output constraint, on the same model, with no schema or repair. It can measure the benefit of grounding plus repair without needing a proprietary API key. It does not reproduce the customer's GPT-5.5 deployment.

### Current validation status

Live evaluation on October 2, 2026 used `accounts/fireworks/models/gpt-oss-120b`:

| Run | Result matches | Median query latency | Input tokens, total | Output tokens, total | Repair calls |
| --- | --- | --- | --- | --- | --- |
| Grounded agent | 10/10 | 1.35 s | 19,153 | 2,915 | 0 |
| Grounded agent, repeat | 10/10 | 1.39 s | 19,153 | 2,915 | 0 |
| Minimal-prompt baseline | 0/10 | 1.17 s | 1,373 | 2,558 | 0 |

Both consecutive grounded runs passed all ten questions. Four additional live questions covering explicit branch geography, residence, and follow-ups also matched independently executed reference queries. Repeat outputs are saved in `dev_answers_repeat.json` and `dev_answers_repeat_report.json`. The earlier q_008 failure used client residence instead of account branch geography. Correcting the misleading client documentation and supplying explicit join paths fixed it: the query now counts 128 owners in Brno - mesto through account branches. These definitions are general dataset semantics, not stored answers or per-question SQL. All baseline queries failed execution due to invented table names.

The live CLI returned 554 Prague accounts, then correctly handled “What about south Moravia?” with 778 accounts. `/reset` and `quit` also worked. These counts were checked against the local database.

The committed `dev_answers.json` and report contain actual outputs, for all ten passing queries. The baseline outputs are in `baseline_answers.json` and `baseline_answers_report.json`. An earlier JSON-mode run passed 10/10 but needed eight repairs; inspection found wrong JSON field names. An explicit output schema eliminated those repairs. A later run exposed case-sensitive region matching, fixed with a case-insensitive comparison instruction. The residence/branch error was then resolved through documentation and explicit business join definitions. These are development-set iterations, not an unseen accuracy estimate; no claim of repeatable 100% accuracy is made.

Eight offline tests and two opt-in live tests (four model queries) passed, including execution of all ten supplied gold queries. Checks cover denied SQL operations, CTE reads, truncation, timeout recovery, mocked model repair and conversation context, and scoring behavior. Executing supplied gold SQL against the database checks the fixtures and execution layer; it is not evidence of model accuracy.

## Latency, cost, and next steps

Next, repeat these measurements on unseen questions and compare another available model for semantic reliability. Repeated runs should record P50/P95, failures, cold-start behavior, repairs, and tokens. The current median covers `Agent.ask()` (API, parsing, repair, and SQL; formatting excluded); it excludes startup/schema loading and terminal rendering. The slowest query took 6.88 seconds in the repeat run, so tail latency still needs work. Ten dev questions cannot establish the customer's <3-second production P50 target.

For pricing rates P_in/P_out in dollars per million tokens, cost per query is `(mean_input_tokens * P_in + mean_output_tokens * P_out) / 1_000_000`. Multiply by 30,000 for projected daily model cost. Include repair calls (already accumulated by the evaluator). Use current account/model rates from Fireworks; no unverified price or cost savings are claimed. Open-weight models offer cost/control options but must earn selection through measured accuracy and latency; proprietary models are useful comparison points if budget permits.

Production work should add an unseen evaluation set, ambiguous and adversarial questions, richer conversation handling, user clarification, database adapters, least-privilege credentials, tenant authorization, audit logs, resource isolation, and concurrency/load measurements. Successful SQL execution cannot detect a semantically wrong join or filter. The MVP supports the provided SQLite dataset, not arbitrary connection strings.

For post-training, collect consented, reviewed question/schema/SQL pairs, corrections, follow-ups, and execution outcomes. Split by query family and database before training to prevent leakage. First address documentation and prompt gaps; fine-tune a smaller model when repeated semantic errors persist and enough diverse reviewed examples exist. Compare against the prompted baseline on held-out accuracy, safety, latency, and cost. Ten public questions are insufficient training evidence; executable SQL alone is not a correctness label.

Live geography regression tests are opt-in to avoid accidental API charges during ordinary unit tests.

See [CUSTOMER_EMAIL.md](CUSTOMER_EMAIL.md) for the draft response. AI assistance was used to implement, review, and document this proof of concept. Dataset terms remain in [BIRD_LICENSE.md](BIRD_LICENSE.md).

API integration follows the [Fireworks quickstart](https://docs.fireworks.ai/getting-started/quickstart); consult the [model catalog](https://fireworks.ai/models) for current availability.
