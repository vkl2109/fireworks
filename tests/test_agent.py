"""Offline checks for security boundaries, repair, history, and result scoring."""
import json
import sqlite3
import unittest
from tempfile import TemporaryDirectory
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.agent import Agent, Result, execute_sql, open_database, schema_context
from src.cli import main
from src.evaluate import matches


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE example (n INTEGER)")
        self.conn.executemany("INSERT INTO example VALUES (?)", [(1,), (2,)])
        self.addCleanup(self.conn.close)

    def test_read_and_truncation(self):
        columns, rows, truncated = execute_sql(self.conn, "WITH x AS (SELECT * FROM example) SELECT * FROM x", limit=1)
        self.assertEqual((columns, rows, truncated), (["n"], [(1,)], True))

    def test_database_uri_is_read_only_and_missing_files_are_not_created(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bank #1?.sqlite"
            with closing(sqlite3.connect(path)) as conn:
                conn.execute("CREATE TABLE example (n INTEGER)")
                conn.execute("INSERT INTO example VALUES (7)")
                conn.commit()
            with closing(open_database(str(path))) as conn:
                self.assertEqual(conn.execute("SELECT n FROM example").fetchall(), [(7,)])
                conn.execute("PRAGMA query_only=OFF")
                with self.assertRaises(sqlite3.OperationalError):
                    conn.execute("INSERT INTO example VALUES (8)")
            missing = Path(directory) / "missing.sqlite"
            with self.assertRaises(sqlite3.OperationalError):
                open_database(str(missing))
            self.assertFalse(missing.exists())

    def test_prohibited_operations(self):
        for sql in ["DELETE FROM example", "DROP TABLE example", "PRAGMA query_only=OFF",
                    "ATTACH ':memory:' AS other", "SELECT load_extension('x')",
                    "SELECT 1; SELECT 2", "WITH x AS (SELECT 1) DELETE FROM example"]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.Error):
                execute_sql(self.conn, sql)
        self.assertEqual(execute_sql(self.conn, "SELECT COUNT(*) FROM example")[1], [(2,)])

    def test_timeout_and_connection_reuse(self):
        with self.assertRaises(sqlite3.OperationalError):
            execute_sql(self.conn, "WITH RECURSIVE x(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM x) SELECT sum(n) FROM x", timeout=0.001)
        self.assertEqual(execute_sql(self.conn, "SELECT 1")[1], [(1,)])

    def test_repair_and_followup(self):
        client = Mock()
        def response(sql):
            return SimpleNamespace(usage=None, choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(content=json.dumps({"sql": sql})))])
        client.chat.completions.create.side_effect = [response("SELECT missing FROM example"),
                                                     response("SELECT sum(n) FROM example"), response("SELECT 2")]
        agent = Agent(self.conn, client, "test", "example(n)")
        result = agent.ask("sum?")
        self.assertEqual((result.rows, result.attempts, result.error), ([(3,)], 2, None))
        agent.ask("What about two?")
        self.assertIn({"role": "user", "content": "sum?"}, client.chat.completions.create.call_args.kwargs["messages"])

    def test_malformed_response_stops_after_one_repair(self):
        client = Mock()
        client.chat.completions.create.return_value = SimpleNamespace(
            usage=None, choices=[SimpleNamespace(finish_reason="stop",
                                                message=SimpleNamespace(content="invalid json"))])
        result = Agent(self.conn, client, "test", "example(n)").ask("count?")
        self.assertEqual(result.attempts, 2)
        self.assertIsNotNone(result.error)

    def test_cli_question_reset_and_exit(self):
        agent = Mock(model="test", history=[{"role": "user", "content": "old"}])
        agent.ask.return_value = Result(sql="SELECT 1", columns=["one"], rows=[(1,)])
        with patch("sys.argv", ["cli"]), patch("src.cli.create_agent", return_value=agent), \
             patch("builtins.input", side_effect=["question", "/reset", "quit"]), \
             patch("builtins.print") as output:
            main()
        agent.ask.assert_called_once_with("question")
        self.assertEqual(agent.history, [])
        self.assertTrue(any("SELECT 1" in str(call) for call in output.call_args_list))

    def test_gold_queries_and_schema(self):
        with closing(open_database("data/financial.sqlite")) as conn:
            self.assertIn("repayment status", schema_context(conn, "data/database_description"))
            for q in json.loads(Path("data/dev_questions_with_answers.json").read_text()):
                with self.subTest(question=q["id"]):
                    _, rows, truncated = execute_sql(conn, q["gold_sql"])
                    self.assertFalse(truncated)
                    self.assertTrue(matches(rows, q["expected_result"], q["id"] in {"q_008", "q_009"}))

    def test_scoring_duplicates_rounding_and_order(self):
        self.assertTrue(matches([(4190.664,)], [{"average": 4190.66}]))
        self.assertFalse(matches([(1,), (1,)], [{"a": 1}, {"a": 2}]))
        self.assertFalse(matches([("a", 1), ("b", 2)], [{"x": "b", "n": 2}, {"x": "a", "n": 1}], True))


if __name__ == "__main__":
    unittest.main()
