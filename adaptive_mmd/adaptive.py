from __future__ import annotations

from adaptive_mmd.models import AdaptationDecision, ModelKind
from adaptive_mmd.storage import SQLiteStorage
from adaptive_mmd.workload import WorkloadMonitor


class AdaptiveController:
    def __init__(
        self,
        storage: SQLiteStorage,
        workload: WorkloadMonitor,
        index_threshold: int = 3,
    ) -> None:
        self.storage = storage
        self.workload = workload
        self.index_threshold = index_threshold

    def adapt(self) -> list[AdaptationDecision]:
        stats = self.workload.summarize()
        decisions: list[AdaptationDecision] = []
        for collection in self.storage.list_collections():
            workload = stats.get(collection)
            previous = self.storage.get_layout(collection)
            next_layout = self._choose_layout(collection, workload)
            created: list[str] = []
            dropped: list[str] = []
            if workload is not None:
                for field, count in workload.field_counts.items():
                    if count >= self.index_threshold:
                        if self.storage.create_field_index(collection, field):
                            created.append(field)
                for field in sorted(self.storage.indexed_fields(collection)):
                    if workload.field_counts.get(field, 0) == 0:
                        if self.storage.drop_field_index(collection, field):
                            dropped.append(field)
            if next_layout != previous:
                self.storage.set_layout(collection, next_layout)
            if created or dropped or next_layout != previous:
                decisions.append(
                    AdaptationDecision(
                        collection=collection,
                        previous_layout=previous,
                        next_layout=next_layout,
                        created_indexes=created,
                        dropped_indexes=dropped,
                        reason=self._reason(collection, workload, next_layout),
                    )
                )
        return decisions

    def _choose_layout(self, collection: str, workload) -> ModelKind:
        records = self.storage.record_count(collection)
        edges = self.storage.edge_count(collection)
        events = self.storage.event_count(collection)
        physical_counts = {
            "document": records,
            "graph": edges,
            "timeseries": events,
        }
        dominant_physical = max(physical_counts, key=physical_counts.get)
        if workload is None or workload.total == 0:
            if physical_counts[dominant_physical] == 0:
                return "document"
            return dominant_physical  # type: ignore[return-value]
        top_kind, top_count = workload.kind_counts.most_common(1)[0]
        if top_count / max(1, workload.total) < 0.55:
            return "hybrid"
        if top_kind == "graph":
            return "graph"
        if top_kind == "timeseries":
            return "timeseries"
        if top_kind == "selection" and records:
            return "row"
        return "document"

    def _reason(self, collection: str, workload, layout: ModelKind) -> str:
        if workload is None:
            return f"selected `{layout}` from stored physical data counts"
        return (
            f"selected `{layout}` from workload shape "
            f"{dict(workload.kind_counts)} and fields {dict(workload.field_counts)}"
        )

