from __future__ import annotations

from adaptive_mmd.models import PhysicalPlan, Query
from adaptive_mmd.storage import SQLiteStorage


class QueryPlanner:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def plan(self, query: Query) -> PhysicalPlan:
        if query.kind == "graph":
            edges = self.storage.edge_count(query.collection)
            return PhysicalPlan(
                operator="graph_traversal",
                collection=query.collection,
                estimated_cost=max(1.0, min(edges, query.depth * 5)),
                reason="query asks for adjacency expansion",
            )
        if query.kind == "timeseries":
            events = self.storage.event_count(query.collection)
            return PhysicalPlan(
                operator="timeseries_range_scan",
                collection=query.collection,
                estimated_cost=max(1.0, events * 0.25),
                reason="query constrains metric/time dimensions",
            )
        indexed = self.storage.indexed_fields(query.collection)
        for field in query.where:
            if field in indexed:
                return PhysicalPlan(
                    operator="indexed_record_lookup",
                    collection=query.collection,
                    estimated_cost=2.0,
                    reason=f"field `{field}` has an adaptive secondary index",
                    index_field=field,
                )
        count = self.storage.record_count(query.collection)
        if query.where:
            return PhysicalPlan(
                operator="document_predicate_scan",
                collection=query.collection,
                estimated_cost=max(1.0, count),
                reason="predicate has no adaptive index yet",
            )
        return PhysicalPlan(
            operator="record_scan",
            collection=query.collection,
            estimated_cost=max(1.0, count),
            reason="full logical collection scan",
        )

