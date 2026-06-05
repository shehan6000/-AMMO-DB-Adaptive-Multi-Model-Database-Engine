from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ModelKind = Literal["row", "document", "graph", "timeseries", "hybrid"]
OperatorKind = Literal[
    "record_scan",
    "indexed_record_lookup",
    "document_predicate_scan",
    "graph_traversal",
    "timeseries_range_scan",
]


@dataclass(frozen=True)
class Query:
    collection: str
    where: dict[str, Any] = field(default_factory=dict)
    project: list[str] | None = None
    aggregate: str | None = None
    time_from: str | None = None
    time_to: str | None = None
    metric: str | None = None
    start_node: str | None = None
    edge_label: str | None = None
    depth: int = 1

    @property
    def kind(self) -> str:
        if self.start_node is not None:
            return "graph"
        if self.time_from is not None or self.time_to is not None or self.metric is not None:
            return "timeseries"
        if self.where:
            return "selection"
        return "scan"


@dataclass(frozen=True)
class PhysicalPlan:
    operator: OperatorKind
    collection: str
    estimated_cost: float
    reason: str
    index_field: str | None = None


@dataclass
class AdaptationDecision:
    collection: str
    previous_layout: ModelKind
    next_layout: ModelKind
    created_indexes: list[str] = field(default_factory=list)
    dropped_indexes: list[str] = field(default_factory=list)
    reason: str = ""

