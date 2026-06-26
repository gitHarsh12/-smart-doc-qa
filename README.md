# 🛡️ Smart Document Q&A — Production-Hardened RAG App

Streamlit-based RAG application with multi-provider LLM support (NVIDIA / Groq / OpenRouter),
FAISS vector store, semantic cache, and 30+ document format support.

**This version has been hardened based on a 27-finding production-readiness audit.**
See `CHANGELOG.md` for the complete fix list, and `RAG_Production_Readiness_Audit.pdf`
(in the parent directory) for the full audit report.

## 🚀 Quick Start

### 1. Clone + install dependencies

```bash
git clone <your-repo-url>
cd fixed_app

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure secrets

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml — add at least ONE API key
```

Get free API keys:
- **NVIDIA AI**: https://build.nvidia.com/ (free credits)
- **Groq**: https://console.groq.com/ (free, fastest)
- **OpenRouter**: https://openrouter.ai/ (500+ models, free tier)

### 3. Run the Streamlit app

```bash
streamlit run app.py
```

App will be available at http://localhost:8501

## 🛡️ Security Hardening Applied

All 4 Critical and 7 High findings from the audit have been fixed:

| Finding | Severity | Fix |
|---------|----------|-----|
| F-01 Path traversal | CRITICAL | `_safe_temp_path()` with UUID + regex sanitization |
| F-02 XSS in chat | CRITICAL | `html.escape(text, quote=True)` |
| F-03 No auth | CRITICAL | SSO scaffolding + email whitelist |
| F-04 Prompt injection | HIGH | `<untrusted_context>` tags in system prompt |
| F-05 Cache poisoning | HIGH | Document hash in cache key |
| F-07 No file size limit | HIGH | 200MB enforcement in OCR + process_document |
| F-08 ZIP bomb | HIGH | `_safe_zip_extract()` with size cap |
| F-09 SSL bypass | HIGH | Removed global `ssl._create_unverified_context` |
| F-10 Rate limiter bypass | HIGH | Redis-backed `RateLimiter` |
| F-11 Recursive retry | HIGH | Iterative loop with exponential backoff |

See `CHANGELOG.md` for the complete list (27 findings).

## 🧪 Load Testing

The app includes a FastAPI shim (`api.py`) for proper load testing.
Streamlit's WebSocket protocol can't be load-tested directly.

### Start the API server

```bash
RAG_API_TOKEN=my-secret-token uvicorn api:app --host 0.0.0.0 --port 8000 --workers 4
```

### Run Locust load tests

```bash
# Staircase (find breaking point: 100 → 100k users)
RAG_API_TOKEN=my-secret-token \
locust -f load_tests/locustfile_staircase.py \
       --host=http://localhost:8000 \
       --headless --run-time 25m \
       --csv=staircase_results

# Spike (viral traffic simulation)
RAG_API_TOKEN=my-secret-token \
locust -f load_tests/locustfile_spike.py \
       --host=http://localhost:8000 \
       --headless --run-time 5m

# Constant (memory leak detection — 1k users × 1hr)
RAG_API_TOKEN=my-secret-token \
locust -f load_tests/locustfile_constant.py \
       --host=http://localhost:8000 \
       --headless --run-time 1h
```

### Run pytest load tests (CI/CD)

```bash
# Start API in background
RAG_API_TOKEN=ci-test uvicorn api:app --port 8000 &
sleep 5

# Run tests
pytest tests/test_load.py -v --tb=short
```

## 📊 Observability

### Structured JSON logs

All logs are emitted as JSON for easy parsing:

```json
{"timestamp":"2026-06-21T12:34:56Z","level":"INFO","logger":"app","message":"API call completed","user_id":"harsh@x.com","tokens":432,"latency_ms":1230}
```

### Sentry integration (optional)

1. Get a DSN from https://sentry.io/
2. Add to `.streamlit/secrets.toml`:
   ```toml
   SENTRY_DSN = "https://xxxx@sentry.io/xxxx"
   SENTRY_ENV = "production"
   ```
3. Errors will automatically be reported.

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│  Streamlit UI (app.py)                  │
│  - File upload, chat UI                 │
│  - st.cache_resource for singletons     │
└────────────────┬────────────────────────┘
                 │ (also exposed via)
┌────────────────▼────────────────────────┐
│  FastAPI Shim (api.py) — for load test  │
│  - /ask, /upload, /health, /stats       │
└────────────────┬────────────────────────┘
                 │
┌────────────────▼────────────────────────┐
│  Modules:                               │
│  ├─ ocr_scanner.py (30+ formats, F-01)  │
│  ├─ chunker.py    (F-26 overlap fix)    │
│  ├─ llm_provider.py (F-11 retry, F-22)  │
│  ├─ embedder.py   (NVIDIA + local)      │
│  ├─ vector_store.py (HNSW, F-19 persist)│
│  ├─ semantic_cache.py (F-20 vectorized) │
│  ├─ retriever.py  (NVIDIA re-ranker)    │
│  ├─ rate_limiter.py (F-10 Redis)        │
│  ├─ logging_setup.py (F-16 JSON+Sentry) │
│  └─ config.py     (F-12 centralized)    │
└─────────────────────────────────────────┘
```

## 📝 Production Deployment Checklist

Before deploying to Streamlit Cloud:

- [ ] `.streamlit/secrets.toml` configured with real API keys (NOT committed to git)
- [ ] `RAG_ALLOWED_EMAILS` set in secrets.toml (whitelist of user emails)
- [ ] Streamlit Cloud app set to **Private** (Settings → Access → Private)
- [ ] `requirements.txt` installed (versions pinned)
- [ ] Tested locally with `streamlit run app.py`
- [ ] Tested load with `locust -f load_tests/locustfile_staircase.py`
- [ ] Sentry DSN configured (optional but recommended)
- [ ] Redis URL configured (optional, for shared rate limiting)

## 🐛 Troubleshooting

### "No API keys configured"
- Check `.streamlit/secrets.toml` exists and has at least one valid key
- Run `python -c "from modules.llm_provider import detect_available_keys; print(detect_available_keys())"`

### "EasyOCR model download failed"
- Install certifi: `pip install certifi`
- On Windows, set `SSL_CERT_FILE` env var to certifi's cacert.pem path

### "Rate limit exceeded" too aggressive
- Edit `modules/config.py`: increase `RATE_LIMIT_MAX_REQUESTS`
- Or set up Redis for shared rate limiting: `REDIS_URL=redis://localhost:6379/0`

### Load test shows 5xx errors
- Check API token matches: `RAG_API_TOKEN` in env must match `Authorization: Bearer` header
- Check API logs for the actual error
- Run `curl http://localhost:8000/health` to verify API is up

## 📚 Documentation

- `CHANGELOG.md` — Complete fix list (27 findings)
- `RAG_Production_Readiness_Audit.pdf` — Full audit report (in parent dir)
- Inline code comments — Each fix tagged with `🛡️ FIX F-XX`
