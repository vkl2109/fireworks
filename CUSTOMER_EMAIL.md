Subject: Text-to-SQL CLI PoC — 10/10 dev answers correct, 1.83-second median

Hi Raul,

I built an interactive Python CLI using Fireworks with gpt-oss-120b. It grounds SQL in the schema and column documentation, supports follow-up questions, displays SQL and results, and attempts one repair when generation or execution fails. Queries run through read-only SQLite controls with a timeout and a result limit.

On the ten public development questions, the final version returned ten correct results in two consecutive runs on October 14, compared with zero for the October 2 minimal-prompt baseline on the same model. All ten grounded queries executed, with no repair calls and a 1.83-second median query latency. An earlier error grouped account owners by residence rather than branch district. Correcting misleading column documentation and supplying explicit business join definitions resolved it; successful execution alone had not detected that semantic error.

I compared actual rows with the supplied answers, checked ranking and numeric tolerance, ran nine offline tests, and checked four live questions covering branch geography, residence, and follow-ups. The final run consumed 19,153 input and 2,438 output tokens across ten questions. These are development-set measurements after prompt iterations; the latency excludes startup and terminal rendering, and does not establish production performance or cost savings. The repeat run had a 1.37-second median and a 2.88-second slowest query, so tail latency still needs attention. The answer files preserve both runs.

Next I would validate on unseen questions, resolve ambiguous business definitions, compare available models, and measure latency and cost under load at the projected 30,000 queries/day. Production scope also includes database adapters, tenant access controls, and richer clarification behavior.

For post-training, I would collect reviewed question/schema/SQL pairs and corrections, reserve a separate evaluation set, and fine-tune a smaller model if recurring errors remain after grounding improvements. Ten public questions are insufficient training data. A trained model should improve held-out correctness and unit economics before deployment.

I used AI coding assistance for implementation, review, and documentation. The README includes setup, reproducible evaluation commands, measured results, and limitations.

Best,
Vinni
