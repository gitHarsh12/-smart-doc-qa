"""
🛡️ Load Test: Constant Profile (sustained load for memory leak detection)

1000 concurrent users for 1 hour. Detects:
- Memory leaks (RAM usage climbs over time)
- Connection leaks (file descriptors exhausted)
- Cache degradation (hit rate drops over time)
- Slow degradation (latency increases over time)

Run:
    locust -f load_tests/locustfile_constant.py \\
           --host=http://localhost:8000 \\
           --headless --run-time 1h \\
           --csv=constant_results

Pair with monitoring:
    docker stats
    watch -n 5 'curl -s http://localhost:8000/health | jq'
"""

import os
import random
from locust import HttpUser, task, between, LoadTestShape

API_TOKEN = os.getenv("RAG_API_TOKEN", "dev-token-change-me")
SAMPLE_QUERIES = [
    "Summary?",
    "Key points?",
    "Amount?",
    "Date?",
    "Parties?",
    "Clauses?",
    "Termination?",
    "Payment?",
]


class RAGAPIUser(HttpUser):
    wait_time = between(2, 5)  # realistic user pacing
    host = os.getenv("TARGET_HOST", "http://localhost:8000")

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {API_TOKEN}"}

    @task
    def ask(self):
        self.client.post(
            "/ask",
            json={"query": random.choice(SAMPLE_QUERIES)},
            headers=self.headers,
            name="/ask",
        )


class ConstantShape(LoadTestShape):
    """
    Constant 1000 users for 1 hour.

    Pass criteria:
    - p95 latency stays under 5s throughout (no degradation)
    - error rate stays under 1% throughout
    - memory usage stable (check via docker stats / /health endpoint)
    """
    def tick(self):
        run_time = self.get_run_time()
        if run_time < 3600:  # 1 hour
            return (1000, 50)  # 1000 users, spawn 50/sec
        return None
