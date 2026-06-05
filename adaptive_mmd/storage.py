from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from adaptive_mmd.models import ModelKind


class SQLiteStorage:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.initialize()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS collections (
                name TEXT PRIMARY KEY,
                layout TEXT NOT NULL DEFAULT 'document'
            );

            CREATE TABLE IF NOT EXISTS records (
                collection TEXT NOT NULL,
                id TEXT NOT NULL,
                model TEXT NOT NULL,
                body TEXT NOT NULL,
                PRIMARY KEY (collection, id),
                FOREIGN KEY (collection) REFERENCES collections(name)
            );

            CREATE TABLE IF NOT EXISTS field_index (
                collection TEXT NOT NULL,
                field TEXT NOT NULL,
                value TEXT NOT NULL,
                record_id TEXT NOT NULL,
                PRIMARY KEY (collection, field, value, record_id)
            );

            CREATE TABLE IF NOT EXISTS graph_edges (
                collection TEXT NOT NULL,
                src TEXT NOT NULL,
                label TEXT NOT NULL,
                dst TEXT NOT NULL,
                properties TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (collection, src, label, dst)
            );

            CREATE TABLE IF NOT EXISTS timeseries_events (
                collection TEXT NOT NULL,
                metric TEXT NOT NULL,
                ts TEXT NOT NULL,
                value REAL NOT NULL,
                tags TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (collection, metric, ts, tags)
            );

            CREATE TABLE IF NOT EXISTS index_catalog (
                collection TEXT NOT NULL,
                field TEXT NOT NULL,
                PRIMARY KEY (collection, field)
            );

            CREATE TABLE IF NOT EXISTS workload_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT NOT NULL,
                kind TEXT NOT NULL,
                field TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def ensure_collection(self, name: str, layout: ModelKind = "document") -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO collections(name, layout) VALUES (?, ?)",
            (name, layout),
        )
        self.conn.commit()

    def set_layout(self, collection: str, layout: ModelKind) -> None:
        self.ensure_collection(collection, layout)
        self.conn.execute(
            "UPDATE collections SET layout = ? WHERE name = ?",
            (layout, collection),
        )
        self.conn.commit()

    def get_layout(self, collection: str) -> ModelKind:
        self.ensure_collection(collection)
        row = self.conn.execute(
            "SELECT layout FROM collections WHERE name = ?",
            (collection,),
        ).fetchone()
        return row["layout"]

    def list_collections(self) -> list[str]:
        rows = self.conn.execute("SELECT name FROM collections ORDER BY name").fetchall()
        return [row["name"] for row in rows]

    def upsert_record(
        self,
        collection: str,
        record_id: str,
        body: dict[str, Any],
        model: ModelKind = "document",
    ) -> None:
        self.ensure_collection(collection, model)
        self.conn.execute(
            """
            INSERT INTO records(collection, id, model, body)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(collection, id)
            DO UPDATE SET model = excluded.model, body = excluded.body
            """,
            (collection, record_id, model, json.dumps(body, sort_keys=True)),
        )
        self._refresh_record_indexes(collection, record_id, body)
        self.conn.commit()

    def _refresh_record_indexes(
        self, collection: str, record_id: str, body: dict[str, Any]
    ) -> None:
        self.conn.execute(
            "DELETE FROM field_index WHERE collection = ? AND record_id = ?",
            (collection, record_id),
        )
        fields = self.indexed_fields(collection)
        rows = []
        for field in fields:
            if field in body:
                rows.append((collection, field, self._normalize_value(body[field]), record_id))
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO field_index(collection, field, value, record_id)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )

    def scan_records(self, collection: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT id, model, body FROM records WHERE collection = ? ORDER BY id",
            (collection,),
        ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def lookup_by_index(
        self, collection: str, field: str, value: Any
    ) -> list[dict[str, Any]]:
        ids = self.conn.execute(
            """
            SELECT record_id FROM field_index
            WHERE collection = ? AND field = ? AND value = ?
            ORDER BY record_id
            """,
            (collection, field, self._normalize_value(value)),
        ).fetchall()
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        params = [collection, *[row["record_id"] for row in ids]]
        rows = self.conn.execute(
            f"""
            SELECT id, model, body FROM records
            WHERE collection = ? AND id IN ({placeholders})
            ORDER BY id
            """,
            params,
        ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def add_edge(
        self,
        collection: str,
        src: str,
        label: str,
        dst: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        self.ensure_collection(collection, "graph")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO graph_edges(collection, src, label, dst, properties)
            VALUES (?, ?, ?, ?, ?)
            """,
            (collection, src, label, dst, json.dumps(properties or {}, sort_keys=True)),
        )
        self.conn.commit()

    def neighbors(self, collection: str, src: str, label: str | None = None) -> list[str]:
        if label is None:
            rows = self.conn.execute(
                "SELECT dst FROM graph_edges WHERE collection = ? AND src = ? ORDER BY dst",
                (collection, src),
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT dst FROM graph_edges
                WHERE collection = ? AND src = ? AND label = ?
                ORDER BY dst
                """,
                (collection, src, label),
            ).fetchall()
        return [row["dst"] for row in rows]

    def insert_event(
        self,
        collection: str,
        metric: str,
        ts: str,
        value: float,
        tags: dict[str, Any] | None = None,
    ) -> None:
        self.ensure_collection(collection, "timeseries")
        self.conn.execute(
            """
            INSERT OR REPLACE INTO timeseries_events(collection, metric, ts, value, tags)
            VALUES (?, ?, ?, ?, ?)
            """,
            (collection, metric, ts, value, json.dumps(tags or {}, sort_keys=True)),
        )
        self.conn.commit()

    def range_events(
        self,
        collection: str,
        metric: str | None,
        start: str | None,
        end: str | None,
    ) -> list[dict[str, Any]]:
        predicates = ["collection = ?"]
        params: list[Any] = [collection]
        if metric is not None:
            predicates.append("metric = ?")
            params.append(metric)
        if start is not None:
            predicates.append("ts >= ?")
            params.append(start)
        if end is not None:
            predicates.append("ts <= ?")
            params.append(end)
        sql = (
            "SELECT metric, ts, value, tags FROM timeseries_events WHERE "
            + " AND ".join(predicates)
            + " ORDER BY ts"
        )
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "metric": row["metric"],
                "ts": row["ts"],
                "value": row["value"],
                "tags": json.loads(row["tags"]),
            }
            for row in rows
        ]

    def create_field_index(self, collection: str, field: str) -> bool:
        self.ensure_collection(collection)
        existing = self.conn.execute(
            "SELECT 1 FROM index_catalog WHERE collection = ? AND field = ?",
            (collection, field),
        ).fetchone()
        if existing:
            return False
        self.conn.execute(
            "INSERT INTO index_catalog(collection, field) VALUES (?, ?)",
            (collection, field),
        )
        rows = self.conn.execute(
            "SELECT id, body FROM records WHERE collection = ?",
            (collection,),
        ).fetchall()
        index_rows = []
        for row in rows:
            body = json.loads(row["body"])
            if field in body:
                index_rows.append(
                    (collection, field, self._normalize_value(body[field]), row["id"])
                )
        self.conn.executemany(
            """
            INSERT OR REPLACE INTO field_index(collection, field, value, record_id)
            VALUES (?, ?, ?, ?)
            """,
            index_rows,
        )
        self.conn.commit()
        return True

    def drop_field_index(self, collection: str, field: str) -> bool:
        removed = self.conn.execute(
            "DELETE FROM index_catalog WHERE collection = ? AND field = ?",
            (collection, field),
        ).rowcount
        self.conn.execute(
            "DELETE FROM field_index WHERE collection = ? AND field = ?",
            (collection, field),
        )
        self.conn.commit()
        return removed > 0

    def indexed_fields(self, collection: str) -> set[str]:
        rows = self.conn.execute(
            "SELECT field FROM index_catalog WHERE collection = ?",
            (collection,),
        ).fetchall()
        return {row["field"] for row in rows}

    def record_count(self, collection: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM records WHERE collection = ?",
            (collection,),
        ).fetchone()
        return int(row["n"])

    def edge_count(self, collection: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM graph_edges WHERE collection = ?",
            (collection,),
        ).fetchone()
        return int(row["n"])

    def event_count(self, collection: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM timeseries_events WHERE collection = ?",
            (collection,),
        ).fetchone()
        return int(row["n"])

    def _record_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        body = json.loads(row["body"])
        body["_id"] = row["id"]
        body["_model"] = row["model"]
        return body

    def _normalize_value(self, value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return str(value)
