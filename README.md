# AMMO-DB: Adaptive Multi-Model Database Engine


> Can a database adapt its physical storage layout based on workload evolution across relational, document, graph, and time-series workloads?

The prototype implements a unified logical query model on top of SQLite, then tracks workload behavior and adapts physical indexes and collection layout metadata over time.

## What It Demonstrates

- Unified logical records for relational rows, JSON documents, graph nodes, graph edges, and time-series events.
- A small cost-based planner that selects physical operators from logical query intent.
- Workload monitoring with query-shape statistics.
- Adaptive indexing for frequently filtered fields.
- Adaptive collection layout classification: `row`, `document`, `graph`, `timeseries`, or `hybrid`.
- Online reorganization metadata and index migration.
- CLI demo and automated tests.

This is intentionally a research prototype, not a production DBMS. It gives you a complete base that can be expanded into a thesis-grade system.

## Project Structure

```text
adaptive_mmd/
  __init__.py
  adaptive.py       adaptive layout/index controller
  cli.py            command-line interface
  engine.py         public database engine API
  models.py         query and plan data structures
  planner.py        logical-to-physical planner
  storage.py        SQLite storage manager
  workload.py       workload statistics
demo.py             end-to-end demonstration
tests/              unit tests
```

## Quick Start

```powershell
python demo.py
```

Run tests:

```powershell
python -m unittest discover -s tests
```

Run the Streamlit demo:

```powershell
.\.streamlit_venv\Scripts\streamlit.exe run streamlit_app.py --server.port 8501
```

Or use the included launcher:

```powershell
.\run_streamlit.ps1
```

Try the CLI:

```powershell
python -m adaptive_mmd.cli init ammo.db
python -m adaptive_mmd.cli seed ammo.db
python -m adaptive_mmd.cli query ammo.db users --where city=Tokyo
python -m adaptive_mmd.cli timeseries ammo.db metrics cpu --from 2026-01-01T00:00:00 --to 2026-01-01T00:05:00
python -m adaptive_mmd.cli graph ammo.db people alice follows --depth 2
python -m adaptive_mmd.cli adapt ammo.db
python -m adaptive_mmd.cli stats ammo.db
```

## Research Framing

### Problem

Modern applications often mix relational entities, JSON-like documents, graph relationships, and time-series measurements. Existing multi-model systems usually expose several data models, but their physical design tends to remain static or manually tuned.

AMMO-DB explores whether a DBMS can:

1. Observe workload behavior.
2. Infer which physical layout best matches each collection.
3. Create or remove indexes based on actual query shapes.
4. Preserve a single logical query interface while changing internals.

### Research Questions

1. How accurately can workload traces classify dominant data-model behavior?
2. When does adaptive indexing improve latency enough to justify maintenance cost?
3. Can a single planner make reasonable operator choices across relational, document, graph, and time-series queries?
4. How should a system detect hybrid collections that resist a single layout?

### Baseline Extensions

Good thesis extensions from this prototype:

- Add cardinality estimation and a richer cost model.
- Implement actual columnar segments for row-heavy analytical collections.
- Add LSM-style time-series partitions.
- Add graph-specific adjacency compression.
- Evaluate against PostgreSQL JSONB, Neo4j, MongoDB, and InfluxDB on mixed workloads.
- Add reinforcement learning or bandit-based adaptation.

## Example Output

The demo seeds four workloads, executes mixed queries, adapts the database, and prints:

- query results,
- selected physical plans,
- workload statistics,
- adaptive index/layout decisions.
