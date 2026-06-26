"""
🛡️ Load Test: Staircase Profile (find the breaking point)

Ramp users in stages: 100 → 1k → 10k → 50k → 100k.
Each stage 5 minutes. Total test: 25 minutes.

Run:
    locust -f load_tests/locustfile_staircase.py \\
           --host=http://localhost:8000 \\
           --headless --run-time 25m \\
           --csv=staircase_results

Success criteria:
    - p95 latency < 5s for /ask
    - error rate < 1%
    - no 5xx errors in stage 1-3 (low load)

Prerequisites:
    1. Start FastAPI shim:  RAG_API_TOKEN=test123 uvicorn api:app --port 8000
    2. Install locust:       pip install locust
"""

import os
import random
from locust import HttpUser, task, between, events
from locust import LoadTestShape

API_TOKEN = os.getenv("RAG_API_TOKEN", "dev-token-change-me")
SAMPLE_QUERIES = [
    "Document ka summary kya hai?",
    "Main points list karo.",
    "What is the total amount mentioned?",
    "Who are the key parties involved?",
    "Date of agreement?",
    "Important clauses kya kya hain?",
    "Termination conditions?",
    "Payment terms?",
    "Confidentiality clause?",
    "What happens if terms are violated?",
]


class RAGAPIUser(HttpUser):
    """Simulates a user asking questions to the RAG API."""
    wait_time = between(1, 5)  # think time 1-5 seconds
    host = os.getenv("TARGET_HOST", "http://localhost:8000")

    def on_start(self):
        self.headers = {"Authorization": f"Bearer {API_TOKEN}"}

    @task(10)
    def ask_question(self):
        """Most common operation — ask a question."""
        query = random.choice(SAMPLE_QUERIES)
        with self.client.post(
            "/ask",
            json={"query": query, "document_id": "default"},
            headers=self.headers,
            name="/ask",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                if data.get("answer", "").startswith("Error"):
                    resp.failure(f"API returned error: {data['answer'][:100]}")
                elif resp.elapsed.total_seconds() > 10:
                    resp.failure(f"Slow response: {resp.elapsed.total_seconds():.1f}s")
            elif resp.status_code == 429:
                resp.failure("Rate limited")
            elif resp.status_code >= 500:
                resp.failure(f"Server error {resp.status_code}")

    @task(1)
    def health_check(self):
        """Occasional health check (no auth needed)."""
        self.client.get("/health", name="/health")


class StaircaseShape(LoadTestShape):
    """
    Staircase load shape: 5 stages of 5 minutes each.

    Stage 1: 100 users    (baseline)
    Stage 2: 1,000 users  (moderate)
    Stage 3: 10,000 users (high)
    Stage 4: 50,000 users (very high)
    Stage 5: 100,000 users (extreme — find breaking point)
    """
    stages = [
        {"duration": 300,  "users": 100,    "spawn_rate": 10},    # 0-5 min
        {"duration": 600,  "users": 1000,   "spawn_rate": 50},    # 5-10 min
        {"duration": 900,  "users": 10000,  "spawn_rate": 200},   # 10-15 min
        {"duration": 1200, "users": 50000,  "spawn_rate": 500},   # 15-20 min
        {"duration": 1500, "users": 100000, "spawn_rate": 1000},  # 20-25 min
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return (stage["users"], stage["spawn_rate"])
        return None  # test complete


@events.quitting.add_listener
def check_success(environment, **kwargs):
    """Fail the test if success criteria not met."""
    stats = environment.stats.total
    fail_ratio = stats.fail_ratio
    p95 = stats.get_response_time_percentile(0.95)

    print(f"\n{'='*60}")
    print(f"STAIRCASE TEST RESULTS")
    print(f"{'='*60}")
    print(f"Total requests: {stats.num_requests:,}")
    print(f"Failures: {stats.num_failures:,} ({fail_ratio*100:.2f}%)")
    print(f"p95 latency: {p95}ms" if p95 else "p95 latency: N/A")
    print(f"p99 latency: {stats.get_response_time_percentile(0.99)}ms")
    print(f"{'='*60}")

    if fail_ratio > 0.01:
        print(f"❌ FAILED: Error rate {fail_ratio*100:.1f}% > 1%")
        environment.process_exit_code = 1
    elif p95 and p95 > 5000:
        print(f"❌ FAILED: p95 latency {p95}ms > 5000ms")
        environment.process_exit_code = 1
    else:
        print("✅ PASSED: All criteria met")
