from __future__ import annotations

import argparse
import json
from pathlib import Path

from adaptive_mmd.engine import AdaptiveMultiModelDB
from adaptive_mmd.models import Query


def main() -> None:
    parser = argparse.ArgumentParser(description="AMMO-DB adaptive multi-model engine")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("db")

    seed = sub.add_parser("seed")
    seed.add_argument("db")

    query = sub.add_parser("query")
    query.add_argument("db")
    query.add_argument("collection")
    query.add_argument("--where", action="append", default=[])

    graph = sub.add_parser("graph")
    graph.add_argument("db")
    graph.add_argument("collection")
    graph.add_argument("start_node")
    graph.add_argument("edge_label")
    graph.add_argument("--depth", type=int, default=1)

    ts = sub.add_parser("timeseries")
    ts.add_argument("db")
    ts.add_argument("collection")
    ts.add_argument("metric")
    ts.add_argument("--from", dest="time_from")
    ts.add_argument("--to", dest="time_to")
    ts.add_argument("--aggregate", choices=["count", "avg", "min", "max"])

    adapt = sub.add_parser("adapt")
    adapt.add_argument("db")

    stats = sub.add_parser("stats")
    stats.add_argument("db")

    args = parser.parse_args()
    db = AdaptiveMultiModelDB(Path(args.db))
    try:
        if args.command == "init":
            print("initialized", args.db)
        elif args.command == "seed":
            seed_database(db)
            print("seeded", args.db)
        elif args.command == "query":
            result, plan = db.query(Query(args.collection, where=parse_where(args.where)))
            print(json.dumps({"plan": plan.__dict__, "result": result}, indent=2))
        elif args.command == "graph":
            result, plan = db.query(
                Query(
                    args.collection,
                    start_node=args.start_node,
                    edge_label=args.edge_label,
                    depth=args.depth,
                )
            )
            print(json.dumps({"plan": plan.__dict__, "result": result}, indent=2))
        elif args.command == "timeseries":
            result, plan = db.query(
                Query(
                    args.collection,
                    metric=args.metric,
                    time_from=args.time_from,
                    time_to=args.time_to,
                    aggregate=args.aggregate,
                )
            )
            print(json.dumps({"plan": plan.__dict__, "result": result}, indent=2))
        elif args.command == "adapt":
            decisions = [decision.__dict__ for decision in db.adapt()]
            print(json.dumps(decisions, indent=2))
        elif args.command == "stats":
            print(json.dumps(db.stats(), indent=2))
    finally:
        db.close()


def parse_where(items: list[str]) -> dict[str, str]:
    where = {}
    for item in items:
        if "=" not in item:
            raise ValueError("--where values must look like field=value")
        field, value = item.split("=", 1)
        where[field] = value
    return where


def seed_database(db: AdaptiveMultiModelDB) -> None:
    users = [
        ("alice", {"name": "Alice", "city": "Tokyo", "role": "researcher"}),
        ("bob", {"name": "Bob", "city": "Tokyo", "role": "engineer"}),
        ("carol", {"name": "Carol", "city": "Berlin", "role": "researcher"}),
        ("dana", {"name": "Dana", "city": "Cairo", "role": "designer"}),
    ]
    for record_id, body in users:
        db.put("users", record_id, body)
    db.put(
        "articles",
        "paper-1",
        {
            "title": "Adaptive Multi-Model Storage",
            "authors": ["Alice", "Carol"],
            "metadata": {"venue": "VLDB", "year": 2026},
        },
    )
    db.add_edge("people", "alice", "follows", "bob")
    db.add_edge("people", "bob", "follows", "carol")
    db.add_edge("people", "carol", "follows", "dana")
    for minute, value in enumerate([0.20, 0.30, 0.50, 0.40, 0.35, 0.60]):
        db.add_event(
            "metrics",
            "cpu",
            f"2026-01-01T00:0{minute}:00",
            value,
            {"host": "db-node-1"},
        )


if __name__ == "__main__":
    main()

