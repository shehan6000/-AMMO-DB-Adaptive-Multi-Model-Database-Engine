from __future__ import annotations

import unittest

from adaptive_mmd.engine import AdaptiveMultiModelDB
from adaptive_mmd.models import Query


class EngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = AdaptiveMultiModelDB(":memory:")
        self.db.put("users", "u1", {"name": "Ada", "city": "Tokyo", "role": "db"})
        self.db.put("users", "u2", {"name": "Grace", "city": "Paris", "role": "os"})
        self.db.put("users", "u3", {"name": "Edsger", "city": "Tokyo", "role": "theory"})
        self.db.add_edge("people", "u1", "knows", "u2")
        self.db.add_edge("people", "u2", "knows", "u3")
        self.db.add_event("metrics", "latency", "2026-01-01T00:00:00", 10)
        self.db.add_event("metrics", "latency", "2026-01-01T00:01:00", 20)

    def tearDown(self) -> None:
        self.db.close()

    def test_selection_query(self) -> None:
        result, plan = self.db.query(Query("users", where={"city": "Tokyo"}))
        self.assertEqual(plan.operator, "document_predicate_scan")
        self.assertEqual([row["name"] for row in result], ["Ada", "Edsger"])

    def test_adaptive_index(self) -> None:
        for _ in range(3):
            self.db.query(Query("users", where={"city": "Tokyo"}))
        decisions = self.db.adapt()
        self.assertTrue(any("city" in item.created_indexes for item in decisions))
        _, plan = self.db.query(Query("users", where={"city": "Tokyo"}))
        self.assertEqual(plan.operator, "indexed_record_lookup")

    def test_graph_traversal(self) -> None:
        result, plan = self.db.query(
            Query("people", start_node="u1", edge_label="knows", depth=2)
        )
        self.assertEqual(plan.operator, "graph_traversal")
        self.assertEqual([row["node"] for row in result], ["u1", "u2", "u3"])

    def test_timeseries_average(self) -> None:
        result, plan = self.db.query(
            Query(
                "metrics",
                metric="latency",
                time_from="2026-01-01T00:00:00",
                time_to="2026-01-01T00:01:00",
                aggregate="avg",
            )
        )
        self.assertEqual(plan.operator, "timeseries_range_scan")
        self.assertEqual(result, [{"avg": 15}])


if __name__ == "__main__":
    unittest.main()

