"""Opt-in paid API regressions: RUN_LIVE_TESTS=1 python -m unittest discover -s tests."""
import os
import unittest

from src.agent import create_agent, execute_sql, open_database
from src.evaluate import matches


@unittest.skipUnless(os.getenv("RUN_LIVE_TESTS") == "1", "requires an explicit live API run")
class GeographyTests(unittest.TestCase):
    def setUp(self):
        self.conn = open_database("data/financial.sqlite")
        self.addCleanup(self.conn.close)
        self.agent = create_agent(self.conn)
        self.addCleanup(self.agent.client.close)

    def check_answer(self, question, expected_sql):
        result = self.agent.ask(question)
        columns, rows, truncated = execute_sql(self.conn, expected_sql)
        expected = [dict(zip(columns, row)) for row in rows]
        self.assertIsNone(result.error, result.error)
        self.assertFalse(result.truncated or truncated)
        self.assertTrue(matches(result.rows, expected),
                        f"{question}\nSQL: {result.sql}\nActual: {result.rows}\nExpected: {rows}")

    def test_branch_geography_and_followup(self):
        self.check_answer(
            "Count distinct account owners by branch district in SOUTH MORAVIA. Show district name and count.",
            "SELECT d.A2, COUNT(DISTINCT dp.client_id) FROM district d "
            "JOIN account a ON a.district_id=d.district_id JOIN disp dp ON dp.account_id=a.account_id "
            "WHERE dp.type='OWNER' AND d.A3='south Moravia' GROUP BY d.district_id, d.A2")
        self.check_answer(
            "Now do the same for north Bohemia.",
            "SELECT d.A2, COUNT(DISTINCT dp.client_id) FROM district d "
            "JOIN account a ON a.district_id=d.district_id JOIN disp dp ON dp.account_id=a.account_id "
            "WHERE dp.type='OWNER' AND d.A3='north Bohemia' GROUP BY d.district_id, d.A2")

    def test_explicit_residence_and_followup(self):
        self.check_answer(
            "Count distinct account owners by the district where they live in south Moravia. Show district name and count.",
            "SELECT d.A2, COUNT(DISTINCT c.client_id) FROM district d "
            "JOIN client c ON c.district_id=d.district_id JOIN disp dp ON dp.client_id=c.client_id "
            "WHERE dp.type='OWNER' AND d.A3='south Moravia' GROUP BY d.district_id, d.A2")
        self.check_answer(
            "Now do the same for north Bohemia.",
            "SELECT d.A2, COUNT(DISTINCT c.client_id) FROM district d "
            "JOIN client c ON c.district_id=d.district_id JOIN disp dp ON dp.client_id=c.client_id "
            "WHERE dp.type='OWNER' AND d.A3='north Bohemia' GROUP BY d.district_id, d.A2")


if __name__ == "__main__":
    unittest.main()
