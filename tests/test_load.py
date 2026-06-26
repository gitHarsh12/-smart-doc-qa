"""
🛡️ Pytest Load Test (CI/CD integration)

Run from CI pipeline to catch performance regressions.

Usage:
    # Start API first:
    RAG_API_TOKEN=test123 uvicorn api:app --port 8000 &

    # Run tests:
    pytest tests/test_load.py -v --tb=short

Install:
    pip install pytest pytest-asyncio httpx
"""

import os
import asyncio
import time
import statistics
import pytest
import httpx

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
API_TOKEN = os.getenv("RAG_API_TOKEN", "dev-token-change-me")
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

SAMPLE_QUERIES = ["Summary?", "Key points?", "Amount?", "Date?", "Parties?"]


@pytest.fixture(scope="session")
def client():
    """Async HTTP client fixture."""
    with httpx.AsyncClient(base_url=API_BASE, timeout=30, headers=HEADERS) as c:
        # Verify API is up
        try:
            resp = asyncio.run(c.get("/health"))
            assert resp.status_code == 200, f"API not ready: {resp.status_code}"
        except Exception as e:
            pytest.skip(f"API not available at {API_BASE}: {e}")
        yield c


def test_health(client):
    """Smoke test: API responds to /health."""
    loop = asyncio.new_event_loop()
    try:
        resp = loop.run_until_complete(client.get("/health"))
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_concurrent_100_users(client):
    """100 concurrent /ask requests — all should succeed (>= 99%)."""
    async def ask_one():
        resp = await client.post("/ask", json={"query": "Summary?"})
        return resp.status_code == 200

    results = await asyncio.gather(*[ask_one() for _ in range(100)])
    success_rate = sum(results) / len(results)
    assert success_rate >= 0.99, f"Success rate too low: {success_rate*100:.1f}%"


@pytest.mark.asyncio
async def test_p95_latency_under_2s(client):
    """p95 latency should be under 2 seconds at moderate load (50 sequential reqs)."""
    latencies = []
    for _ in range(50):
        start = time.monotonic()
        resp = await client.post("/ask", json={"query": "Summary?"})
        latencies.append(time.monotonic() - start)
        assert resp.status_code == 200

    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    assert p95 < 2.0, f"p95 latency {p95:.2f}s exceeds 2s"


@pytest.mark.asyncio
async def test_sustained_load_5min(client):
    """5 minutes of sustained load — measure throughput + error rate.

    50 concurrent workers, 5 min duration.
    Pass: error rate < 1%, throughput > 5 req/s.
    """
    end_time = time.monotonic() + 300  # 5 min
    requests = 0
    errors = 0

    async def worker():
        nonlocal requests, errors
        while time.monotonic() < end_time:
            try:
                resp = await client.post("/ask", json={"query": "Summary?"}, timeout=10)
                requests += 1
                if resp.status_code != 200:
                    errors += 1
            except Exception:
                errors += 1
                requests += 1

    await asyncio.gather(*[worker() for _ in range(50)])

    error_rate = errors / requests if requests else 1
    throughput = requests / 300
    print(f"\n5min sustained: {requests} requests, {errors} errors "
          f"({error_rate*100:.1f}%), {throughput:.1f} req/s")
    assert error_rate < 0.01, f"Error rate {error_rate*100:.1f}% > 1%"
    assert throughput > 5, f"Throughput {throughput:.1f} req/s too low"


@pytest.mark.asyncio
async def test_cache_hit_returns_instantly(client):
    """Same query twice — second should be much faster (cache hit)."""
    # First request (cache miss)
    start1 = time.monotonic()
    resp1 = await client.post("/ask", json={"query": "Cache test query unique 12345"})
    elapsed1 = time.monotonic() - start1
    assert resp1.status_code == 200

    # Second request (should be cache hit)
    start2 = time.monotonic()
    resp2 = await client.post("/ask", json={"query": "Cache test query unique 12345"})
    elapsed2 = time.monotonic() - start2
    assert resp2.status_code == 200
    assert resp2.json()["cached"] is True, "Second request should be cached"

    # Cache hit should be at least 5x faster
    assert elapsed2 < elapsed1 * 0.2, \
        f"Cache hit ({elapsed2:.2f}s) should be 5x faster than miss ({elapsed1:.2f}s)"


# ============================================================
# CI/CD integration example (GitHub Actions)
# ============================================================
# .github/workflows/load-test.yml:
#
# name: Load Test
# on: [push, pull_request]
# jobs:
#   load-test:
#     runs-on: ubuntu-latest
#     steps:
#       - uses: actions/checkout@v3
#       - uses: actions/setup-python@v4
#         with:
#           python-version: '3.11'
#       - run: pip install -r requirements.txt
#       - run: pip install fastapi uvicorn httpx pytest pytest-asyncio
#       - run: RAG_API_TOKEN=ci-test uvicorn api:app --host 0.0.0.0 --port 8000 &
#       - run: sleep 5  # wait for API to start
#       - run: pytest tests/test_load.py -v --tb=short
#         env:
#           API_BASE: http://localhost:8000
#           RAG_API_TOKEN: ci-test
