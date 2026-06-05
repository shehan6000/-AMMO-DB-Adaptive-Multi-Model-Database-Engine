from __future__ import annotations

import statistics
import time

from adaptive_mmd.engine import AdaptiveMultiModelDB
from adaptive_mmd.models import Query


def timed(fn, repeats: int = 50) -> tuple[float, object]:
    samples = []
    last = None
    for _ in range(repeats):
        start = time.perf_counter()
        last = fn()
        samples.append(time.perf_counter() - start)
    return statistics.mean(samples), last


def main() -> None:
    db = AdaptiveMultiModelDB(":memory:")
    for i in range(5000):
        db.put(
            "users",
            f"user-{i}",
            {
                "name": f"User {i}",
                "city": "Tokyo" if i % 5 == 0 else "Berlin",
                "role": "researcher" if i % 7 == 0 else "engineer",
            },
        )

    query = Query("users", where={"city": "Tokyo"})
    before, (before_result, before_plan) = timed(lambda: db.query(query))

    decisions = db.adapt()
    after, (after_result, after_plan) = timed(lambda: db.query(query))

    print("AMMO-DB adaptive indexing experiment")
    print(f"records: 5000")
    print(f"matches: {len(before_result)}")
    print(f"before operator: {before_plan.operator}")
    print(f"after operator:  {after_plan.operator}")
    print(f"before mean latency: {before * 1000:.3f} ms")
    print(f"after mean latency:  {after * 1000:.3f} ms")
    print(f"speedup: {before / after:.2f}x")
    print("decisions:")
    for decision in decisions:
        print(f"  {decision}")
    db.close()


if __name__ == "__main__":
    main()

