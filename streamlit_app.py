from __future__ import annotations

import json
import time
from statistics import mean
from typing import Any

import streamlit as st

from adaptive_mmd.cli import seed_database
from adaptive_mmd.engine import AdaptiveMultiModelDB
from adaptive_mmd.models import Query


st.set_page_config(
    page_title="AMMO-DB Adaptive Multi-Model Database",
    page_icon="DB",
    layout="wide",
)


def init_state() -> None:
    if "db" not in st.session_state:
        db = AdaptiveMultiModelDB(":memory:")
        seed_database(db)
        st.session_state.db = db
        st.session_state.history = []
        st.session_state.benchmark = None
        st.session_state.db_generation = 1


def recover_database() -> None:
    try:
        st.session_state.db.stats()
    except Exception as exc:
        if "SQLite objects created in a thread" not in str(exc):
            raise
        db = AdaptiveMultiModelDB(":memory:")
        seed_database(db)
        st.session_state.db = db
        st.session_state.history = []
        st.session_state.benchmark = None
        st.session_state.db_generation = st.session_state.get("db_generation", 0) + 1
        st.warning("Recreated the demo database after a Streamlit thread refresh.")


def run_query(query: Query) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    result, plan = st.session_state.db.query(query)
    event = {
        "collection": query.collection,
        "kind": query.kind,
        "operator": plan.operator,
        "reason": plan.reason,
        "rows": len(result),
    }
    st.session_state.history.append(event)
    return result, plan.__dict__


def reset_database() -> None:
    old_db = st.session_state.get("db")
    if old_db is not None:
        try:
            old_db.close()
        except Exception:
            pass
    db = AdaptiveMultiModelDB(":memory:")
    seed_database(db)
    st.session_state.db = db
    st.session_state.history = []
    st.session_state.benchmark = None
    st.session_state.db_generation = st.session_state.get("db_generation", 0) + 1


def metric_card(label: str, value: Any, help_text: str | None = None) -> None:
    st.metric(label, value, help=help_text)


def render_stats() -> None:
    stats = st.session_state.db.stats()["collections"]
    cols = st.columns(4)
    totals = {
        "collections": len(stats),
        "records": sum(item["records"] for item in stats.values()),
        "edges": sum(item["edges"] for item in stats.values()),
        "events": sum(item["events"] for item in stats.values()),
    }
    with cols[0]:
        metric_card("Collections", totals["collections"])
    with cols[1]:
        metric_card("Records", totals["records"])
    with cols[2]:
        metric_card("Graph edges", totals["edges"])
    with cols[3]:
        metric_card("Time-series events", totals["events"])

    rows = []
    for name, item in stats.items():
        rows.append(
            {
                "collection": name,
                "layout": item["layout"],
                "records": item["records"],
                "edges": item["edges"],
                "events": item["events"],
                "indexes": ", ".join(item["indexes"]) or "-",
                "workload": json.dumps(item["workload"]["kinds"]),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)


def render_query_lab() -> None:
    st.subheader("Query Lab")
    query_type = st.segmented_control(
        "Query type",
        ["Selection", "Graph", "Time-series"],
        default="Selection",
    )

    if query_type == "Selection":
        col1, col2, col3 = st.columns([1.2, 1, 1])
        with col1:
            collection = st.selectbox("Collection", ["users", "articles"], index=0)
        with col2:
            field = st.selectbox("Field", ["city", "role", "name", "title"], index=0)
        with col3:
            value = st.text_input("Value", "Tokyo")
        if st.button("Run selection query", type="primary"):
            result, plan = run_query(Query(collection, where={field: value}))
            show_result(plan, result)

    elif query_type == "Graph":
        col1, col2, col3 = st.columns(3)
        with col1:
            start_node = st.selectbox("Start node", ["alice", "bob", "carol", "dana"])
        with col2:
            edge_label = st.text_input("Edge label", "follows")
        with col3:
            depth = st.slider("Depth", 1, 5, 2)
        if st.button("Run graph traversal", type="primary"):
            result, plan = run_query(
                Query(
                    "people",
                    start_node=start_node,
                    edge_label=edge_label,
                    depth=depth,
                )
            )
            show_result(plan, result)

    else:
        col1, col2, col3, col4 = st.columns([1, 1.3, 1.3, 1])
        with col1:
            metric = st.text_input("Metric", "cpu")
        with col2:
            time_from = st.text_input("From", "2026-01-01T00:01:00")
        with col3:
            time_to = st.text_input("To", "2026-01-01T00:04:00")
        with col4:
            aggregate = st.selectbox("Aggregate", ["none", "avg", "min", "max", "count"])
        if st.button("Run time-series query", type="primary"):
            result, plan = run_query(
                Query(
                    "metrics",
                    metric=metric,
                    time_from=time_from or None,
                    time_to=time_to or None,
                    aggregate=None if aggregate == "none" else aggregate,
                )
            )
            show_result(plan, result)


def show_result(plan: dict[str, Any], result: list[dict[str, Any]]) -> None:
    left, right = st.columns([1, 1.4])
    with left:
        st.caption("Physical plan")
        st.json(plan)
    with right:
        st.caption("Result")
        st.dataframe(result, width="stretch", hide_index=True)


def render_adaptation() -> None:
    st.subheader("Adaptive Physical Design")
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Run adaptation", type="primary"):
            decisions = st.session_state.db.adapt()
            if decisions:
                st.success(f"Applied {len(decisions)} adaptation decision(s).")
                st.json([decision.__dict__ for decision in decisions])
            else:
                st.info("No changes needed for the current workload.")
    with col2:
        if st.button("Generate city-heavy workload"):
            for _ in range(5):
                run_query(Query("users", where={"city": "Tokyo"}))
            st.success("Generated repeated city predicates. Run adaptation next.")

    st.caption("Recent query history")
    st.dataframe(
        st.session_state.history[-12:],
        width="stretch",
        hide_index=True,
    )


def render_benchmark() -> None:
    st.subheader("Before/After Microbenchmark")
    records = st.slider("Synthetic records", 1000, 15000, 5000, step=1000)
    repeats = st.slider("Repeated queries", 10, 100, 40, step=10)
    if st.button("Run benchmark"):
        bench_db = AdaptiveMultiModelDB(":memory:")
        for i in range(records):
            bench_db.put(
                "users",
                f"user-{i}",
                {
                    "name": f"User {i}",
                    "city": "Tokyo" if i % 5 == 0 else "Berlin",
                    "role": "researcher" if i % 7 == 0 else "engineer",
                },
            )
        query = Query("users", where={"city": "Tokyo"})

        before_samples = []
        before_plan = None
        result = []
        for _ in range(repeats):
            start = time.perf_counter()
            result, before_plan = bench_db.query(query)
            before_samples.append(time.perf_counter() - start)

        decisions = bench_db.adapt()

        after_samples = []
        after_plan = None
        for _ in range(repeats):
            start = time.perf_counter()
            result, after_plan = bench_db.query(query)
            after_samples.append(time.perf_counter() - start)

        st.session_state.benchmark = {
            "records": records,
            "matches": len(result),
            "before_operator": before_plan.operator if before_plan else None,
            "after_operator": after_plan.operator if after_plan else None,
            "before_ms": mean(before_samples) * 1000,
            "after_ms": mean(after_samples) * 1000,
            "speedup": mean(before_samples) / mean(after_samples),
            "decisions": [decision.__dict__ for decision in decisions],
        }
        bench_db.close()

    if st.session_state.benchmark:
        data = st.session_state.benchmark
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Before", f"{data['before_ms']:.2f} ms", data["before_operator"])
        c2.metric("After", f"{data['after_ms']:.2f} ms", data["after_operator"])
        c3.metric("Speedup", f"{data['speedup']:.2f}x")
        c4.metric("Matches", data["matches"])
        st.json(data["decisions"])


def main() -> None:
    init_state()
    recover_database()

    st.title("AMMO-DB")
    st.caption("Adaptive Multi-Model Database Engine")

    with st.sidebar:
        st.header("Controls")
        if st.button("Reset seeded database"):
            reset_database()
            st.success("Database reset.")
        st.divider()
        st.write("Seeded collections")
        st.code("users, articles, people, metrics")

    render_stats()

    tab_query, tab_adapt, tab_benchmark, tab_raw = st.tabs(
        ["Query", "Adapt", "Benchmark", "Raw Stats"]
    )
    with tab_query:
        render_query_lab()
    with tab_adapt:
        render_adaptation()
    with tab_benchmark:
        render_benchmark()
    with tab_raw:
        st.json(st.session_state.db.stats())


if __name__ == "__main__":
    main()
