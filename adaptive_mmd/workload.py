from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from adaptive_mmd.models import Query
from adaptive_mmd.storage import SQLiteStorage


@dataclass
class CollectionWorkload:
    kind_counts: Counter[str] = field(default_factory=Counter)
    field_counts: Counter[str] = field(default_factory=Counter)

    @property
    def total(self) -> int:
        return sum(self.kind_counts.values())


class WorkloadMonitor:
    def __init__(self, storage: SQLiteStorage) -> None:
        self.storage = storage

    def record(self, query: Query) -> None:
        fields = list(query.where.keys()) or [None]
        for field in fields:
            self.storage.conn.execute(
                """
                INSERT INTO workload_log(collection, kind, field)
                VALUES (?, ?, ?)
                """,
                (query.collection, query.kind, field),
            )
        self.storage.conn.commit()

    def summarize(self) -> dict[str, CollectionWorkload]:
        rows = self.storage.conn.execute(
            "SELECT collection, kind, field FROM workload_log"
        ).fetchall()
        stats: dict[str, CollectionWorkload] = defaultdict(CollectionWorkload)
        for row in rows:
            item = stats[row["collection"]]
            item.kind_counts[row["kind"]] += 1
            if row["field"] is not None:
                item.field_counts[row["field"]] += 1
        return dict(stats)

    def clear(self) -> None:
        self.storage.conn.execute("DELETE FROM workload_log")
        self.storage.conn.commit()

