"""
🛡️ Load Test: Spike Profile (test resilience to viral traffic)

Hold at 100 users, then suddenly jump to 50k. Test if app recovers
or crashes. Useful for simulating viral traffic / Hacker News hug.

Run:
    locust -f load_tests/locustfile_spike.py \\
           --host=http://localhost:8000 \\
           --headless --run-time 5m \\
           --csv=spike_results
"""

import os
import random
from locust import HttpUser, task, between, LoadTestShape

API_TOKEN = os.getenv("RAG_API_TOKEN", "dev-token-change-me")
SAMPLE_QUERIES = [
    "What is the summary?",
    "List key points.",
    "Total amount?",
    "Date?",
    "Parties involved?",
]


class RAGAPIUser(HttpUser):
    wait_time = between(0.5, 2)  # aggressive pacing
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


class SpikeShape(LoadTestShape):
    """
    Spike shape: simulate viral traffic surge.

    Timeline:
        0-60s:   100 users (warmup)
        60-90s:  50,000 users (SPIKE 1 — viral surge)
        90-150s: 100 users (recovery)
        150-180s:50,000 users (SPIKE 2 — second wave)
        180-300s:100 users (cool down)

    Pass criteria: app recovers after each spike (no permanent degradation).
    """
    stages = [
        {"duration": 60,  "users": 100,    "spawn_rate": 10},     # warmup
        {"duration": 90,  "users": 50000,  "spawn_rate": 5000},   # SPIKE 1
        {"duration": 150, "users": 100,    "spawn_rate": 10},     # recovery
        {"duration": 180, "users": 50000,  "spawn_rate": 5000},   # SPIKE 2
        {"duration": 300, "users": 100,    "spawn_rate": 10},     # cool down
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None
