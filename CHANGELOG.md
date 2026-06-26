# Changelog — RAG Production Hardening

All fixes applied based on the Production-Readiness Audit report.
Each fix references the finding ID (F-XX) from the audit.

## Critical Fixes (4) — Block deploy if not done

### F-01: Path traversal via user-supplied filename
- **File:** `modules/ocr_scanner.py`
- **Was:** `os.path.join("uploads", uploaded_file.name)` — attacker could send `../../etc/evil`
- **Now:** `_safe_temp_path()` strips directory components, sanitizes name with regex, prefixes with UUID, and verifies final path is inside TEMP_DIR.
- **Status:** ✅ Fixed

### F-02: XSS via incomplete HTML escape in chat rendering
- **File:** `app.py` (chat rendering loop)
- **Was:** `.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")` — quote chars (`"`, `'`) leaked, enabling attribute injection.
- **Now:** `escape_chat_text()` uses `html.escape(text, quote=True)` — escapes all 5 dangerous chars.
- **Status:** ✅ Fixed

### F-03: No authentication layer
- **File:** `app.py` (top-level auth gate), `.streamlit/secrets.toml.example` (config)
- **Was:** Anyone with URL could use API credits.
- **Now:** Documented Tier 1/2/3 auth strategies. `RAG_ALLOWED_EMAILS` env var for whitelist. `modules/rate_limiter.py::get_user_id()` integrates with `st.experimental_user`.
- **Status:** ✅ Documented + scaffolding ready (user must enable SSO in Streamlit Cloud settings)

### F-04: Prompt injection via uploaded documents
- **File:** `app.py` (system prompt)
- **Was:** Context injected directly into system prompt — attacker document could say "ignore previous instructions".
- **Now:** Context wrapped in `<untrusted_context>` tags + explicit security instructions in system prompt.
- **Status:** ✅ Fixed

## High Fixes (7)

### F-05: Cache poisoning (no doc-change invalidation)
- **File:** `modules/semantic_cache.py`, `app.py` (process_document)
- **Was:** Cache survived across document changes — stale answers.
- **Now:** `set_document_hash()` auto-clears cache when document hash changes. Cache key includes doc hash prefix.
- **Status:** ✅ Fixed

### F-06: API key leakage in error messages
- **File:** `modules/llm_provider.py`, `modules/logging_setup.py`
- **Was:** `logger.error(f"... {e}")` could leak keys to logs.
- **Now:** JSON log formatter (`_scrub_secrets()`) strips nvapi-/gsk-/sk-or-/Bearer patterns from every log line.
- **Status:** ✅ Fixed

### F-07: No file size enforcement
- **File:** `modules/ocr_scanner.py`, `app.py` (process_document)
- **Was:** UI claimed 200MB but no check — 5GB file could OOM the app.
- **Now:** Hard limit in both OCR scanner entry point AND `process_document()`. Clear error message to user.
- **Status:** ✅ Fixed

### F-08: ZIP bomb risk in ODT/EPUB/MOBI
- **File:** `modules/ocr_scanner.py`
- **Was:** `zf.read(member)` could decompress 100GB from a 1MB ZIP.
- **Now:** `_safe_zip_extract()` checks `info.file_size` AND verifies actual decompressed size (defense in depth).
- **Status:** ✅ Fixed

### F-09: Global SSL verification disabled
- **File:** `modules/ocr_scanner.py`
- **Was:** `ssl._create_default_https_context = ssl._create_unverified_context` — disabled HTTPS verification app-wide (MITM risk).
- **Now:** Removed global override. `_get_safe_ssl_context()` returns proper context with certifi CA bundle.
- **Status:** ✅ Fixed

### F-10: Rate limiter bypassable (per-session state)
- **File:** `modules/rate_limiter.py` (new), `app.py`
- **Was:** `st.session_state.request_timestamps` — bypassable by clearing cookies / incognito.
- **Now:** `RateLimiter` class uses Redis (shared across workers) with in-memory fallback. Keyed by `get_user_id()` (SSO email or anon ID).
- **Status:** ✅ Fixed

### F-11: Unbounded recursive retry on 429
- **File:** `modules/llm_provider.py`
- **Was:** `return self.chat(messages, ...)` on 429 — recursion could stack overflow on persistent rate limit.
- **Now:** Iterative loop with exponential backoff (`MAX_RETRIES=3`, `INITIAL_BACKOFF=1.0`, multiplier 2.0, cap 60s).
- **Status:** ✅ Fixed

## Medium Fixes (11)

### F-12: secrets.toml migration + .env gitignored
- **Files:** `.streamlit/secrets.toml.example`, `.gitignore`, `app.py` (loading logic)
- **Now:** Template provided with all keys + auth whitelist. `.env` and `secrets.toml` in `.gitignore`.
- **Status:** ✅ Fixed

### F-13: No startup health-check for providers
- **Status:** 🟡 Partially addressed via `llm_provider.test_connection()` (improved). Full UI sidebar health dashboard TODO.

### F-14: Magic-byte verification (polyglot attack)
- **File:** `modules/ocr_scanner.py`
- **Now:** `_verify_magic_bytes()` uses `python-magic` to verify claimed extension matches actual MIME type.
- **Status:** ✅ Fixed

### F-15: PII retention in /uploads/ temp dir
- **File:** `modules/ocr_scanner.py`
- **Was:** Hardcoded `uploads/` directory, files deleted only on success path.
- **Now:** `tempfile.mkdtemp()` + `atexit` cleanup. `_secure_cleanup()` overwrites with zeros before delete.
- **Status:** ✅ Fixed

### F-16: Bare except clauses + no structured logging
- **Files:** `modules/logging_setup.py` (new), `modules/llm_provider.py`, `modules/ocr_scanner.py`
- **Now:** `setup_logging()` installs JSON formatter. Bare `except:` replaced with specific exceptions throughout.
- **Status:** ✅ Fixed

### F-17: Unpinned dependencies
- **File:** `requirements.txt`
- **Now:** All packages pinned to specific versions. (Hash-pinning via pip-tools documented in README.)
- **Status:** ✅ Fixed

### F-18: IndexFlatIP won't scale past 100k vectors
- **File:** `modules/vector_store.py`
- **Now:** `use_hnsw=True` flag enables `IndexHNSWFlat` (~10x faster search, ~1.5x more memory).
- **Status:** ✅ Fixed

### F-19: Vector store save/load never used
- **Files:** `modules/vector_store.py`, `app.py`
- **Now:** `save_to_disk()` + `load_from_disk()` methods. `process_document()` saves after every upload. App startup restores from disk.
- **Status:** ✅ Fixed

### F-20: Cache O(N) linear scan
- **File:** `modules/semantic_cache.py`
- **Was:** `cosine_similarity()` called per-entry in a loop — 5s for 10k entries.
- **Now:** Vectors stacked into (N, D) matrix, single matmul for all similarities. Matrix cached, rebuilt on add/expire.
- **Status:** ✅ Fixed

### F-21: Cache process-local (no cross-user)
- **Status:** 🟡 Partially addressed. `RedisSemanticCache` documented in audit. Full implementation requires Redis deployment.

### F-22: No connection pooling
- **File:** `modules/llm_provider.py`
- **Was:** `requests.post()` per call — new TCP+TLS each time.
- **Now:** `requests.Session` with `HTTPAdapter` pool (10 connections, urllib3 Retry for 5xx).
- **Status:** ✅ Fixed

### F-23: EasyOCR lazy-loaded per session
- **File:** `app.py`
- **Was:** OCRScanner instance in `st.session_state` — every new session reloaded the 30s model.
- **Now:** `@st.cache_resource` decorator — process-wide singleton, loaded once, shared across sessions.
- **Status:** ✅ Fixed

### F-24: Fixed 500-word chunking ignores structure
- **Status:** 🟡 Documented. Langchain `RecursiveCharacterTextSplitter` recommended but requires langchain dependency. Marked as future enhancement.

## Low Fixes (3)

### F-25: RetrievalEngine + NVIDIAEmbedder dead code
- **Status:** 🟡 Kept as-is (no behavioral impact). Recommend deleting `modules/retriever.py` and `modules/embedder.py` if not used.

### F-26: Overlap calculation buggy
- **File:** `modules/chunker.py`
- **Was:** `if chunk_id > 0 and start < self.chunk_overlap` — condition never true after first chunk.
- **Now:** Simplified to `overlap = self.chunk_overlap if chunk_id > 0 else 0`.
- **Status:** ✅ Fixed

### F-27: Hinglish comments limit contributors
- **Status:** 🟡 Documented. Comments retained for original-author context. Future: prefix Hinglish comments with `# NOTE:` for easier translation.

## New Files Created

| File | Purpose |
|------|---------|
| `modules/config.py` | Centralized `AppConfig` dataclass (F-12, F-17) |
| `modules/rate_limiter.py` | Redis-backed rate limiter (F-10) |
| `modules/logging_setup.py` | JSON logging + Sentry (F-16) |
| `api.py` | FastAPI shim for load testing (F-13 + load test prep) |
| `load_tests/locustfile_staircase.py` | 100→100k users staircase profile |
| `load_tests/locustfile_spike.py` | Viral traffic spike simulation |
| `load_tests/locustfile_constant.py` | 1k users × 1hr memory leak test |
| `tests/test_load.py` | pytest CI/CD integration |
| `.streamlit/secrets.toml.example` | Template for secrets |
| `.gitignore` | Prevents secret commits |
| `requirements.txt` | Pinned dependencies |
