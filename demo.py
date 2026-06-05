from __future__ import annotations

import json

from adaptive_mmd.cli import seed_database
from adaptive_mmd.engine import AdaptiveMultiModelDB
from adaptive_mmd.models import Query


def show(title: str, payload) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2))


def main() -> None:
    db = AdaptiveMultiModelDB(":memory:")
    seed_database(db)

    workloads = [
        Query("users", where={"city": "Tokyo"}),
        Query("users", where={"city": "Tokyo"}),
        Query("users", where={"city": "Tokyo"}),
        Query("users", where={"role": "researcher"}),
        Query("people", start_node="alice", edge_label="follows", depth=2),
        Query("people", start_node="alice", edge_label="follows", depth=3),
        Query(
            "metrics",
            metric="cpu",
            time_from="2026-01-01T00:01:00",
            time_to="2026-01-01T00:04:00",
            aggregate="avg",
        ),
        Query(
            "metrics",
            metric="cpu",
            time_from="2026-01-01T00:00:00",
            time_to="2026-01-01T00:05:00",
        ),
    ]

    for query in workloads:
        result, plan = db.query(query)
        show(
            f"Query {query.kind} on {query.collection}",
            {"plan": plan.__dict__, "result": result},
        )

    show("Stats before adaptation", db.stats())
    decisions = [decision.__dict__ for decision in db.adapt()]
    show("Adaptation decisions", decisions)

    result, plan = db.query(Query("users", where={"city": "Tokyo"}))
    show(
        "Repeated user query after adaptation",
        {"plan": plan.__dict__, "result": result},
    )
    show("Stats after adaptation", db.stats())
    db.close()


if __name__ == "__main__":
    main()

