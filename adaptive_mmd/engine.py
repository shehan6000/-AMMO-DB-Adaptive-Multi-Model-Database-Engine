from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any

from adaptive_mmd.adaptive import AdaptiveController
from adaptive_mmd.models import AdaptationDecision, PhysicalPlan, Query
from adaptive_mmd.planner import QueryPlanner
from adaptive_mmd.storage import SQLiteStorage
from adaptive_mmd.workload import WorkloadMonitor


class AdaptiveMultiModelDB:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.storage = SQLiteStorage(path)
        self.workload = WorkloadMonitor(self.storage)
        self.planner = QueryPlanner(self.storage)
        self.controller = AdaptiveController(self.storage, self.workload)

    def close(self) -> None:
        self.storage.close()

    def put(self, collection: str, record_id: str, body: dict[str, Any]) -> None:
        model = "row" if self._is_flat(body) else "document"
        self.storage.upsert_record(collection, record_id, body, model)

    def add_edge(
        self,
        collection: str,
        src: str,
        label: str,
        dst: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.storage.add_edge(collection, src, label, dst, properties)

    def add_event(
        self,
        collection: str,
        metric: str,
        ts: str,
        value: float,
        tags: dict[str, Any] | None = None,
    ) -> None:
        self.storage.insert_event(collection, metric, ts, value, tags)

    def query(self, query: Query) -> tuple[list[dict[str, Any]], PhysicalPlan]:
        plan = self.planner.plan(query)
        result = self._execute(query, plan)
        self.workload.record(query)
        return result, plan

    def adapt(self) -> list[AdaptationDecision]:
        return self.controller.adapt()

    def stats(self) -> dict[str, Any]:
        workload = self.workload.summarize()
        collections = {}
        for name in self.storage.list_collections():
            collections[name] = {
                "layout": self.storage.get_layout(name),
                "records": self.storage.record_count(name),
                "edges": self.storage.edge_count(name),
                "events": self.storage.event_count(name),
                "indexes": sorted(self.storage.indexed_fields(name)),
                "workload": {
                    "kinds": dict(workload.get(name).kind_counts) if name in workload else {},
                    "fields": dict(workload.get(name).field_counts) if name in workload else {},
                },
            }
        return {"collections": collections}

    def _execute(self, query: Query, plan: PhysicalPlan) -> list[dict[str, Any]]:
        if plan.operator == "graph_traversal":
            return self._traverse(query)
        if plan.operator == "timeseries_range_scan":
            rows = self.storage.range_events(
                query.collection, query.metric, query.time_from, query.time_to
            )
            return self._aggregate(rows, query.aggregate)
        if plan.operator == "indexed_record_lookup" and plan.index_field is not None:
            candidates = self.storage.lookup_by_index(
                query.collection, plan.index_field, query.where[plan.index_field]
            )
        else:
            candidates = self.storage.scan_records(query.collection)
        filtered = [row for row in candidates if self._matches(row, query.where)]
        if query.project is not None:
            filtered = [
                {field: row.get(field) for field in query.project if field in row}
                for row in filtered
            ]
        return filtered

    def _traverse(self, query: Query) -> list[dict[str, Any]]:
        assert query.start_node is not None
        frontier = [query.start_node]
        visited = {query.start_node}
        paths = [{"node": query.start_node, "depth": 0}]
        for depth in range(1, query.depth + 1):
            next_frontier: list[str] = []
            for node in frontier:
                for neighbor in self.storage.neighbors(
                    query.collection, node, query.edge_label
                ):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        next_frontier.append(neighbor)
                        paths.append({"node": neighbor, "depth": depth})
            frontier = next_frontier
            if not frontier:
                break
        return paths

    def _aggregate(
        self, rows: list[dict[str, Any]], aggregate: str | None
    ) -> list[dict[str, Any]]:
        if aggregate is None:
            return rows
        values = [row["value"] for row in rows]
        if aggregate == "count":
            return [{"count": len(values)}]
        if not values:
            return [{aggregate: None}]
        if aggregate == "avg":
            return [{"avg": mean(values)}]
        if aggregate == "min":
            return [{"min": min(values)}]
        if aggregate == "max":
            return [{"max": max(values)}]
        raise ValueError(f"unsupported aggregate: {aggregate}")

    def _matches(self, row: dict[str, Any], where: dict[str, Any]) -> bool:
        return all(row.get(field) == value for field, value in where.items())

    def _is_flat(self, body: dict[str, Any]) -> bool:
        return all(not isinstance(value, (dict, list)) for value in body.values())

