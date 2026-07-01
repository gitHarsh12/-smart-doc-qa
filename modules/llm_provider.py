"""
=============================================================
UNIVERSAL LLM PROVIDER — NVIDIA / Groq / OpenRouter
=============================================================
Ek hi interface se koi bhi LLM API use karo!

🔥 KEY FEATURE: App works with ANY single API key!
   - Sirf Groq key hai? → Groq LLM + Local Embeddings ✅
   - Sirf NVIDIA key hai? → NVIDIA LLM + NVIDIA Embeddings ✅
   - Sirf OpenRouter key hai? → OpenRouter LLM + Local Embeddings ✅

🧠 SMART AUTO-CONFIG: Provider + Model ke hisab se automatically:
   - Temperature set hota hai
   - Chunk size adjust hota hai
   - Top-K / Top-N set hote hain
   - Max tokens adjust hote hain

💰 FREE TIER PRIORITIZED: Sab models mostly free hain!
=============================================================
"""

import os
import logging
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ============================================================
# 🛡️ FIX F-11 + F-22: Retry config + connection pool constants
# ============================================================
MAX_RETRIES = 3
INITIAL_BACKOFF_SEC = 1.0
BACKOFF_MULTIPLIER = 2.0
MAX_BACKOFF_SEC = 60.0
POOL_CONNECTIONS = 10
POOL_MAXSIZE = 10


# ============================================================
# SMART AUTO-CONFIG REGISTRY
# ============================================================
# Har model ke liye best settings automatically set hote hain.
# Kyunki chhote models kam samajhte hain → chhote chunks + kam tokens
# Bade models zyada samajhte hain → bade chunks + zyada tokens

@dataclass
class ModelConfig:
    """
    Ek model ka smart auto-configuration.

    Yeh settings model ke size aur capability ke hisab se
    automatically adjust hoti hain.
    """
    # Model identity
    model_id: str
    display_name: str
    tags: List[str] = field(default_factory=list)

    # 🧠 LLM Settings
    temperature: float = 0.1        # 0.0=factual, 1.0=creative
    max_tokens: int = 1024          # Max response length
    top_p: float = 0.7             # Sampling focus

    # ✂️ Chunk Settings (smaller model = smaller chunks)
    chunk_size: int = 500          # Words per chunk
    chunk_overlap: int = 100       # Overlap words (20%)

    # 🔍 Retrieval Settings (smaller model = more context chunks)
    top_k_candidates: int = 8      # FAISS broad search
    top_n_results: int = 3         # After re-ranking

    # 🛡️ Cache Settings
    cache_threshold: float = 0.92  # Semantic cache hit %

    # 💰 Cost
    is_free: bool = True
    speed_rating: str = "medium"   # ultra-fast / fast / medium / slow


# ============================================================
# AUTO-CONFIG TABLE — Sab models ke liye optimized settings
# ============================================================

MODEL_CONFIGS = {
    # =================== NVIDIA MODELS ===================
    "nvidia/nemotron-70b": ModelConfig(
        model_id="nvidia/nemotron-70b",
        display_name="Nemotron 70B",
        tags=["smart", "free", "recommended"],
        temperature=0.1, max_tokens=1024, top_p=0.7,
        chunk_size=500, chunk_overlap=100,
        top_k_candidates=8, top_n_results=3,
        cache_threshold=0.92, is_free=True, speed_rating="medium",
    ),
    "meta/llama-3.1-405b-instruct": ModelConfig(
        model_id="meta/llama-3.1-405b-instruct",
        display_name="Llama 3.1 405B",
        tags=["powerful", "premium"],
        temperature=0.05, max_tokens=2048, top_p=0.8,
        chunk_size=800, chunk_overlap=160,
        top_k_candidates=10, top_n_results=4,
        cache_threshold=0.90, is_free=False, speed_rating="slow",
    ),
    "mistralai/mixtral-8x22b-instruct-v0.1": ModelConfig(
        model_id="mistralai/mixtral-8x22b-instruct-v0.1",
        display_name="Mixtral 8x22B",
        tags=["fast", "balanced"],
        temperature=0.1, max_tokens=1024, top_p=0.7,
        chunk_size=500, chunk_overlap=100,
        top_k_candidates=8, top_n_results=3,
        cache_threshold=0.92, is_free=True, speed_rating="fast",
    ),
    "google/gemma-2-27b-it": ModelConfig(
        model_id="google/gemma-2-27b-it",
        display_name="Gemma 2 27B",
        tags=["balanced", "free"],
        temperature=0.15, max_tokens=1024, top_p=0.75,
        chunk_size=400, chunk_overlap=80,
        top_k_candidates=10, top_n_results=4,
        cache_threshold=0.92, is_free=True, speed_rating="fast",
    ),

    # =================== GROQ MODELS ===================
    "llama-3.3-70b-versatile": ModelConfig(
        model_id="llama-3.3-70b-versatile",
        display_name="Llama 3.3 70B",
        tags=["recommended", "fast", "free"],
        temperature=0.1, max_tokens=1024, top_p=0.7,
        chunk_size=500, chunk_overlap=100,
        top_k_candidates=8, top_n_results=3,
        cache_threshold=0.92, is_free=True, speed_rating="ultra-fast",
    ),
    "llama-3.1-8b-instant": ModelConfig(
        model_id="llama-3.1-8b-instant",
        display_name="Llama 3.1 8B",
        tags=["ultra-fast", "free"],
        temperature=0.2, max_tokens=800, top_p=0.75,
        chunk_size=300, chunk_overlap=60,    # Chhota model → chhote chunks
        top_k_candidates=12, top_n_results=5, # Chhota model → zyada context
        cache_threshold=0.90, is_free=True, speed_rating="ultra-fast",
    ),
    "mixtral-8x7b-32768": ModelConfig(
        model_id="mixtral-8x7b-32768",
        display_name="Mixtral 8x7B",
        tags=["balanced", "free"],
        temperature=0.15, max_tokens=1024, top_p=0.7,
        chunk_size=400, chunk_overlap=80,
        top_k_candidates=10, top_n_results=4,
        cache_threshold=0.92, is_free=True, speed_rating="ultra-fast",
    ),
    "gemma2-9b-it": ModelConfig(
        model_id="gemma2-9b-it",
        display_name="Gemma 2 9B",
        tags=["fast", "free"],
        temperature=0.2, max_tokens=800, top_p=0.75,
        chunk_size=350, chunk_overlap=70,
        top_k_candidates=12, top_n_results=5,
        cache_threshold=0.90, is_free=True, speed_rating="ultra-fast",
    ),

    # =================== OPENROUTER MODELS ===================
    "meta-llama/llama-3.1-70b-instruct": ModelConfig(
        model_id="meta-llama/llama-3.1-70b-instruct",
        display_name="Llama 3.1 70B",
        tags=["free", "popular", "recommended"],
        temperature=0.1, max_tokens=1024, top_p=0.7,
        chunk_size=500, chunk_overlap=100,
        top_k_candidates=8, top_n_results=3,
        cache_threshold=0.92, is_free=True, speed_rating="fast",
    ),
    "google/gemma-2-27b-it:free": ModelConfig(
        model_id="google/gemma-2-27b-it:free",
        display_name="Gemma 2 27B",
        tags=["free"],
        temperature=0.15, max_tokens=1024, top_p=0.75,
        chunk_size=400, chunk_overlap=80,
        top_k_candidates=10, top_n_results=4,
        cache_threshold=0.92, is_free=True, speed_rating="fast",
    ),
    "mistralai/mistral-7b-instruct:free": ModelConfig(
        model_id="mistralai/mistral-7b-instruct:free",
        display_name="Mistral 7B",
        tags=["free", "fast"],
        temperature=0.2, max_tokens=800, top_p=0.75,
        chunk_size=300, chunk_overlap=60,
        top_k_candidates=12, top_n_results=5,
        cache_threshold=0.90, is_free=True, speed_rating="fast",
    ),
    "qwen/qwen-2.5-72b-instruct": ModelConfig(
        model_id="qwen/qwen-2.5-72b-instruct",
        display_name="Qwen 2.5 72B",
        tags=["smart", "free"],
        temperature=0.1, max_tokens=1024, top_p=0.7,
        chunk_size=500, chunk_overlap=100,
        top_k_candidates=8, top_n_results=3,
        cache_threshold=0.92, is_free=True, speed_rating="medium",
    ),
    "deepseek/deepseek-chat": ModelConfig(
        model_id="deepseek/deepseek-chat",
        display_name="DeepSeek V3",
        tags=["free", "smart"],
        temperature=0.1, max_tokens=1024, top_p=0.7,
        chunk_size=500, chunk_overlap=100,
        top_k_candidates=8, top_n_results=3,
        cache_threshold=0.92, is_free=True, speed_rating="medium",
    ),
    "anthropic/claude-3.5-sonnet": ModelConfig(
        model_id="anthropic/claude-3.5-sonnet",
        display_name="Claude 3.5 Sonnet",
        tags=["premium", "smartest"],
        temperature=0.05, max_tokens=2048, top_p=0.8,
        chunk_size=800, chunk_overlap=160,
        top_k_candidates=10, top_n_results=4,
        cache_threshold=0.88, is_free=False, speed_rating="slow",
    ),
    "openai/gpt-4o-mini": ModelConfig(
        model_id="openai/gpt-4o-mini",
        display_name="GPT-4o Mini",
        tags=["premium", "balanced"],
        temperature=0.1, max_tokens=1024, top_p=0.7,
        chunk_size=500, chunk_overlap=100,
        top_k_candidates=8, top_n_results=3,
        cache_threshold=0.92, is_free=False, speed_rating="fast",
    ),
}


# ============================================================
# Provider Configuration Registry
# ============================================================

@dataclass
class ProviderConfig:
    """Ek API provider ka configuration."""
    name: str
    display_name: str
    base_url: str
    api_key_env: str
    default_model: str
    available_models: List[str]  # model IDs from MODEL_CONFIGS
    icon: str
    color: str
    speed_label: str


PROVIDERS = {
    "nvidia": ProviderConfig(
        name="nvidia",
        display_name="NVIDIA AI",
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="NVIDIA_API_KEY",
        default_model="nvidia/nemotron-70b",
        available_models=[
            "nvidia/nemotron-70b",
            "meta/llama-3.1-405b-instruct",
            "mistralai/mixtral-8x22b-instruct-v0.1",
            "google/gemma-2-27b-it",
        ],
        icon="🟢",
        color="#76B900",
        speed_label="Medium Speed",
    ),
    "groq": ProviderConfig(
        name="groq",
        display_name="Groq ⚡ Fastest!",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        default_model="llama-3.3-70b-versatile",
        available_models=[
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
        icon="⚡",
        color="#F55036",
        speed_label="Ultra Fast!",
    ),
    "openrouter": ProviderConfig(
        name="openrouter",
        display_name="OpenRouter (500+)",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        default_model="meta-llama/llama-3.1-70b-instruct",
        available_models=[
            "meta-llama/llama-3.1-70b-instruct",
            "qwen/qwen-2.5-72b-instruct",
            "deepseek/deepseek-chat",
            "mistralai/mistral-7b-instruct:free",
            "anthropic/claude-3.5-sonnet",
            "openai/gpt-4o-mini",
        ],
        icon="🌐",
        color="#6D28D9",
        speed_label="Variable",
    ),
}


# ============================================================
# DETECT AVAILABLE API KEYS
# ============================================================

def detect_available_keys() -> Dict[str, bool]:
    """
    Check karo user ke paas kaun kaun se API keys hain.

    Checks: .env file + os.environ + UI input

    Returns:
        {"nvidia": True, "groq": False, "openrouter": True}
    """
    result = {}
    for name, config in PROVIDERS.items():
        key = os.getenv(config.api_key_env, "").strip()
        # Valid key: must be longer than 10 chars AND not a placeholder
        is_placeholder = (
            "xxxxxxx" in key.lower() or
            key in ["nvapi-", "gsk_", "sk-or-"] or
            key.startswith("nvapi-xxx") or
            key.startswith("gsk_xxx") or
            key.startswith("sk-or-xxx") or
            len(key) < 15  # Real API keys are always 15+ chars
        )
        result[name] = not is_placeholder

    return result


def get_best_available_provider() -> str:
    """
    User ke paas jo key hai uske hisab se best provider suggest karo.

    Priority: groq (fastest) > nvidia (embeddings) > openrouter (variety)
    """
    keys = detect_available_keys()

    # Groq first — fastest + free
    if keys.get("groq"):
        return "groq"
    # NVIDIA second — has embeddings built-in
    if keys.get("nvidia"):
        return "nvidia"
    # OpenRouter last — most variety
    if keys.get("openrouter"):
        return "openrouter"

    return "none"


def get_embedding_strategy() -> Dict:
    """
    Embedding ke liye best strategy decide karo.

    🧠 v3.0.3: LOCAL EMBEDDINGS FIRST (user preference)!
    User ne kaha ki local embeddings chahiye (no API key needed).

    Strategy Priority:
    1. EMBEDDING_PROVIDER=local → Force local (if sentence-transformers installed)
    2. EMBEDDING_PROVIDER=nvidia → Force NVIDIA cloud
    3. EMBEDDING_PROVIDER=auto (default) → Prefer local if available, else NVIDIA

    Local embeddings (all-MiniLM-L6-v2):
    - 384-dimensional vectors
    - ~80MB model (downloaded once, cached forever)
    - Runs on CPU (no GPU needed)
    - NO API key needed!
    - Works offline after first download

    NVIDIA cloud embeddings:
    - 1024-dimensional vectors
    - Needs NVIDIA_API_KEY
    - Better quality but requires internet
    """
    keys = detect_available_keys()

    # Check what's available
    local_available = False
    local_import_error = None
    try:
        import sentence_transformers  # noqa: F401
        local_available = True
        logger.info("✅ sentence-transformers is importable!")
    except ImportError as e:
        local_import_error = f"ImportError: {e}"
        logger.warning(f"⚠️ sentence-transformers NOT installed! Error: {e}")
    except Exception as e:
        local_import_error = f"{type(e).__name__}: {e}"
        logger.warning(f"⚠️ sentence-transformers import failed! Error: {local_import_error}")

    nvidia_available = keys.get("nvidia", False)

    # Read user preference from env (default: auto)
    preference = os.getenv("EMBEDDING_PROVIDER", "auto").lower().strip()

    # Strategy 1: User forced local
    if preference == "local":
        if local_available:
            logger.info("🧠 Embedding strategy: LOCAL (forced by EMBEDDING_PROVIDER=local)")
            return {
                "method": "local_sentence_transformer",
                "display": "Local Embeddings (Free!)",
                "model": "all-MiniLM-L6-v2",
                "dimension": 384,
                "icon": "💻",
                "needs_key": "None — Runs locally!",
                "cost": "FREE — No API needed!",
            }
        else:
            logger.warning("⚠️ EMBEDDING_PROVIDER=local but sentence-transformers not installed!")

    # Strategy 2: User forced NVIDIA
    if preference == "nvidia":
        if nvidia_available:
            logger.info("🟢 Embedding strategy: NVIDIA CLOUD (forced by EMBEDDING_PROVIDER=nvidia)")
            return {
                "method": "nvidia_cloud",
                "display": "NVIDIA Cloud Embeddings",
                "model": "nvidia/nv-embedqa-e5-v5",
                "dimension": 1024,
                "icon": "🟢",
                "needs_key": "NVIDIA_API_KEY",
                "cost": "FREE",
            }
        else:
            logger.warning("⚠️ EMBEDDING_PROVIDER=nvidia but NVIDIA_API_KEY not set!")

    # Strategy 3: Auto mode — PREFER LOCAL (v3.0.3 change)
    if local_available:
        logger.info("🧠 Embedding strategy: LOCAL (auto — no API key needed!)")
        return {
            "method": "local_sentence_transformer",
            "display": "Local Embeddings (Free!)",
            "model": "all-MiniLM-L6-v2",
            "dimension": 384,
            "icon": "💻",
            "needs_key": "None — Runs locally!",
            "cost": "FREE — No API needed!",
        }

    # Strategy 4: Fall back to NVIDIA cloud
    if nvidia_available:
        logger.info("🟢 Embedding strategy: NVIDIA CLOUD (sentence-transformers not installed)")
        return {
            "method": "nvidia_cloud",
            "display": "NVIDIA Cloud Embeddings",
            "model": "nvidia/nv-embedqa-e5-v5",
            "dimension": 1024,
            "icon": "🟢",
            "needs_key": "NVIDIA_API_KEY",
            "cost": "FREE",
        }

    # Strategy 5: Neither available — error
    logger.error("❌ No embedding strategy available!")
    error_detail = local_import_error if local_import_error else "sentence-transformers not installed"
    return {
        "method": "unavailable",
        "display": "❌ No Embeddings Available",
        "model": "None",
        "dimension": 0,
        "icon": "❌",
        "needs_key": "Install sentence-transformers OR add NVIDIA_API_KEY",
        "cost": f"Error: {error_detail}",
    }


# ============================================================
# LLM PROVIDER CLASS
# ============================================================

class LLMProvider:
    """
    Universal LLM Provider — Ek class se sab API use karo!

    Supports: NVIDIA | Groq | OpenRouter
    Auto-Config: Model ke hisab se settings auto-adjust!

    🛡️ Hardened with:
    - F-11: Iterative retry with exponential backoff (no more recursion on 429)
    - F-22: requests.Session with connection pool (persistent TCP+TLS)
    - F-16: Specific exception handling (no bare except)
    """

    def __init__(
        self,
        provider: str = None,
        model: Optional[str] = None,
    ):
        # Auto-detect provider if not specified
        if provider is None:
            provider = get_best_available_provider()

        provider = provider.lower().strip()
        if provider not in PROVIDERS:
            raise ValueError(
                f"❌ Unknown provider: '{provider}'. "
                f"Choose from: {list(PROVIDERS.keys())}"
            )

        self.config = PROVIDERS[provider]
        self.provider_name = provider
        self.model = model or self.config.default_model
        self.api_key = os.getenv(self.config.api_key_env, "")

        # 🧠 AUTO-CONFIG: Model ke hisab se settings load karo
        self.model_config = self._load_model_config()

        if not self.api_key:
            logger.warning(
                f"⚠️ API key not set for {self.config.display_name}! "
                f"Set {self.config.api_key_env} in .env"
            )

        self.stats = {
            "total_calls": 0,
            "total_tokens": 0,
            "total_errors": 0,
        }

        # 🛡️ F-22: Build connection-pooled session
        self._session = self._build_session()

        logger.info(
            f"🤖 LLM: {self.config.display_name} | Model: {self.model} | "
            f"Temp: {self.model_config.temperature} | "
            f"Chunk: {self.model_config.chunk_size}w"
        )

    def _build_session(self) -> requests.Session:
        """Build a connection-pooled session with retry strategy."""
        s = requests.Session()
        # 🛡️ F-11: Use urllib3's Retry for connection-level retries
        retry = Retry(
            total=MAX_RETRIES,
            backoff_factor=INITIAL_BACKOFF_SEC,
            status_forcelist=[502, 503, 504],  # 429 handled in chat()
            allowed_methods=["POST", "GET"],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(
            max_retries=retry,
            pool_connections=POOL_CONNECTIONS,
            pool_maxsize=POOL_MAXSIZE,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
        s.headers.update(self._build_headers())
        return s

    def _load_model_config(self) -> ModelConfig:
        """Model ke liye auto-config load karo."""
        if self.model in MODEL_CONFIGS:
            return MODEL_CONFIGS[self.model]

        # Fallback: Default config based on provider
        logger.warning(f"⚠️ No config for model '{self.model}', using defaults")
        return ModelConfig(model_id=self.model, display_name=self.model)

    def chat(
        self,
        messages: List[Dict],
        temperature: float = None,
        max_tokens: int = None,
    ) -> Dict:
        """
        Chat completion with AUTO-CONFIG!

        🛡️ F-11: Iterative retry with exponential backoff (replaces recursion).
        🛡️ F-22: Uses self._session (connection pool).
        🛡️ F-16: Specific exception types (no bare except).
        """
        # 🧠 Auto-config: Use model-specific settings if not overridden
        if temperature is None:
            temperature = self.model_config.temperature
        if max_tokens is None:
            max_tokens = self.model_config.max_tokens

        if not self.api_key:
            return {
                "answer": f"❌ API key not set! Add {self.config.api_key_env} to .env file",
                "tokens_used": 0,
                "response_time": 0,
            }

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": self.model_config.top_p,
        }

        start_time = time.time()
        last_error = None

        # 🛡️ F-11: Iterative retry loop (no recursion!)
        for attempt in range(MAX_RETRIES + 1):
            try:
                logger.info(f"🌐 API Call attempt {attempt+1}/{MAX_RETRIES+1}: {self.model}")
                # 🛡️ F-22: Use pooled session
                response = self._session.post(
                    f"{self.config.base_url}/chat/completions",
                    json=payload,
                    timeout=120,
                )
                elapsed = time.time() - start_time

                if response.status_code == 200:
                    data = response.json()
                    answer = data["choices"][0]["message"]["content"]
                    tokens = data.get("usage", {}).get("total_tokens", 0)

                    self.stats["total_calls"] += 1
                    self.stats["total_tokens"] += tokens

                    logger.info(f"✅ LLM Answer: {len(answer)} chars | {tokens} tokens | {elapsed:.1f}s")
                    return {
                        "answer": answer,
                        "tokens_used": tokens,
                        "response_time": elapsed,
                    }

                elif response.status_code == 429:
                    # Rate limited — retry with backoff
                    if attempt == MAX_RETRIES:
                        self.stats["total_errors"] += 1
                        logger.error(f"❌ Rate limited after {MAX_RETRIES} retries")
                        return {
                            "answer": f"❌ Rate limited (429) after {MAX_RETRIES} retries. Try again later.",
                            "tokens_used": 0,
                            "response_time": elapsed,
                        }
                    backoff = min(
                        INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** attempt),
                        MAX_BACKOFF_SEC
                    )
                    logger.warning(f"⚠️ 429 rate limited. Retry {attempt+1}/{MAX_RETRIES} after {backoff:.1f}s")
                    time.sleep(backoff)
                    continue  # 🛡️ NOT recursion — iterative continue

                else:
                    error_text = response.text[:500]
                    logger.error(f"❌ API Error {response.status_code}: {error_text}")
                    self.stats["total_errors"] += 1
                    return {
                        "answer": f"❌ API Error ({response.status_code}): {error_text}",
                        "tokens_used": 0,
                        "response_time": elapsed,
                    }

            except requests.exceptions.Timeout:
                elapsed = time.time() - start_time
                last_error = "Timeout"
                if attempt == MAX_RETRIES:
                    self.stats["total_errors"] += 1
                    logger.error(f"❌ Timeout after {MAX_RETRIES} retries")
                    return {
                        "answer": f"❌ Request timeout after {MAX_RETRIES} retries.",
                        "tokens_used": 0,
                        "response_time": elapsed,
                    }
                backoff = min(INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** attempt), MAX_BACKOFF_SEC)
                logger.warning(f"⚠️ Timeout. Retry {attempt+1}/{MAX_RETRIES} after {backoff:.1f}s")
                time.sleep(backoff)

            except requests.exceptions.ConnectionError as e:
                elapsed = time.time() - start_time
                last_error = f"ConnectionError: {e}"
                if attempt == MAX_RETRIES:
                    self.stats["total_errors"] += 1
                    return {
                        "answer": f"❌ Connection error: {type(e).__name__}",
                        "tokens_used": 0,
                        "response_time": elapsed,
                    }
                time.sleep(INITIAL_BACKOFF_SEC * (BACKOFF_MULTIPLIER ** attempt))

            except (ValueError, KeyError) as e:
                elapsed = time.time() - start_time
                self.stats["total_errors"] += 1
                logger.exception(f"❌ Parse error: {e}")
                return {
                    "answer": f"❌ Response parse error: {type(e).__name__}",
                    "tokens_used": 0,
                    "response_time": elapsed,
                }

        # Should not reach here, but fallback
        self.stats["total_errors"] += 1
        return {
            "answer": f"❌ Max retries exceeded. Last error: {last_error}",
            "tokens_used": 0,
            "response_time": time.time() - start_time,
        }

    def _build_headers(self) -> Dict:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.provider_name == "openrouter":
            headers["HTTP-Referer"] = "https://smart-doc-qa.app"
            headers["X-Title"] = "Smart Document Q&A"
        return headers

    def test_connection(self) -> bool:
        """Test API connection with a minimal request.

        🛡️ F-16: Specific exception handling (no bare except).
        """
        try:
            result = self.chat(
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=10,
            )
            return not result["answer"].startswith("❌")
        except (requests.RequestException, ValueError, KeyError, ConnectionError) as e:
            logger.warning(f"Connection test failed: {e}")
            return False
        except Exception as e:
            # Last resort — but LOG it (no silent swallow)
            logger.exception(f"Unexpected error in test_connection: {e}")
            return False

    def get_auto_config(self) -> Dict:
        """Current auto-config settings return karo (UI display ke liye)."""
        mc = self.model_config
        return {
            "model": mc.model_id,
            "display_name": mc.display_name,
            "tags": mc.tags,
            "temperature": mc.temperature,
            "max_tokens": mc.max_tokens,
            "top_p": mc.top_p,
            "chunk_size": mc.chunk_size,
            "chunk_overlap": mc.chunk_overlap,
            "top_k_candidates": mc.top_k_candidates,
            "top_n_results": mc.top_n_results,
            "cache_threshold": mc.cache_threshold,
            "is_free": mc.is_free,
            "speed_rating": mc.speed_rating,
        }

    def get_info(self) -> Dict:
        return {
            "provider": self.provider_name,
            "display_name": self.config.display_name,
            "model": self.model,
            "icon": self.config.icon,
            "color": self.config.color,
            "has_api_key": bool(self.api_key),
            "stats": self.stats.copy(),
            "auto_config": self.get_auto_config(),
        }


# ============================================================
# UNIVERSAL EMBEDDING PROVIDER
# ============================================================

class EmbeddingProvider:
    """
    Universal Embedding Provider — KAAM CHALEGA KISI BHI KEY SE!

    Strategy:
    1. NVIDIA key hai → NVIDIA cloud embeddings (1024-dim, best quality)
    2. Koi bhi doosri key → Local sentence-transformers (384-dim, FREE!)

    sentence-transformers model (all-MiniLM-L6-v2) chalta hai:
    - Bina kisi API key ke
    - Local computer pe (no internet needed!)
    - 384-dimensional vectors
    - Fast + lightweight (~80MB download once)
    """

    def __init__(self, strategy: Optional[Dict] = None):
        # Auto-detect best embedding strategy
        if strategy is None:
            strategy = get_embedding_strategy()

        self.strategy = strategy
        self.method = strategy["method"]
        self.model_name = strategy["model"]
        self.dimension = strategy["dimension"]

        # Lazy-loaded model instances
        self._local_model = None

        logger.info(
            f"🧮 Embeddings: {strategy['display']} "
            f"({self.dimension}-dim, {strategy['cost']})"
        )

    @property
    def local_model(self):
        """Lazy-load sentence-transformers model."""
        if self._local_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info(f"📦 Loading local model: {self.model_name}")
                self._local_model = SentenceTransformer(self.model_name)
                logger.info("✅ Local embedding model loaded!")
            except ImportError as e:
                logger.error(
                    f"❌ sentence-transformers not installed! Error: {e}\n"
                    f"Fix: pip install sentence-transformers torch"
                )
                raise ImportError(
                    f"sentence-transformers not installed! Error: {e}\n"
                    f"Fix: Check Streamlit Cloud logs — package may have failed to install.\n"
                    f"Local install: pip install sentence-transformers torch"
                ) from e
            except Exception as e:
                logger.error(f"❌ sentence-transformers model load failed: {e}")
                raise RuntimeError(
                    f"Failed to load sentence-transformers model: {e}\n"
                    f"This might be a numpy/torch version conflict.\n"
                    f"Try: pip install --upgrade sentence-transformers torch numpy"
                ) from e
        return self._local_model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Document chunks ko vectors me badlo."""
        if self.method == "nvidia_cloud":
            return self._embed_nvidia(texts, prefix="passage")
        elif self.method == "local_sentence_transformer":
            return self._embed_local(texts)
        else:
            # 🛡️ v3.0.4: Better error message with actual import error
            error_detail = self.strategy.get("cost", "Unknown error")
            raise RuntimeError(
                f"❌ No embeddings available!\n\n"
                f"Reason: {error_detail}\n\n"
                f"To fix:\n"
                f"1. Check Streamlit Cloud logs — sentence-transformers may have failed to install\n"
                f"2. OR add NVIDIA_API_KEY to secrets.toml (cloud embeddings, no torch needed)\n"
                f"3. OR locally: pip install sentence-transformers torch"
            )

    def embed_query(self, query: str) -> List[float]:
        """User query ko vector me badlo."""
        if self.method == "nvidia_cloud":
            results = self._embed_nvidia([f"query: {query}"])
            return results[0] if results else [0.0] * self.dimension
        elif self.method == "local_sentence_transformer":
            results = self._embed_local([query])
            return results[0] if results else [0.0] * self.dimension
        else:
            # 🛡️ v3.0.2: Graceful error for unavailable embeddings
            raise RuntimeError(
                "❌ No embeddings available! Either:\n"
                "1. Add NVIDIA_API_KEY to secrets.toml (recommended)\n"
                "2. OR install: pip install sentence-transformers torch"
            )

    def _embed_nvidia(self, texts: List[str], prefix: str = "passage") -> List[List[float]]:
        """NVIDIA cloud embedding API call karo."""
        api_key = os.getenv("NVIDIA_API_KEY", "")
        if not api_key:
            logger.warning("⚠️ NVIDIA key missing, falling back to local embeddings!")
            return self._embed_local(texts)

        prefixed = [f"{prefix}: {t}" for t in texts]

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        all_embeddings = []
        batch_size = 20

        for i in range(0, len(prefixed), batch_size):
            batch = prefixed[i:i + batch_size]
            payload = {
                "model": "nvidia/nv-embedqa-e5-v5",
                "input": batch,
                "encoding_format": "float",
                "truncate": "END",
            }

            try:
                response = requests.post(
                    "https://integrate.api.nvidia.com/v1/embeddings",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )

                if response.status_code == 200:
                    data = response.json()
                    sorted_data = sorted(data["data"], key=lambda x: x["index"])
                    embeddings = [item["embedding"] for item in sorted_data]
                    all_embeddings.extend(embeddings)
                else:
                    logger.error(f"❌ NVIDIA embed error: {response.status_code}")
                    # Fallback to local
                    return self._embed_local(texts)

            except Exception as e:
                logger.error(f"❌ NVIDIA embed failed: {e}")
                return self._embed_local(texts)

        return all_embeddings

    def _embed_local(self, texts: List[str]) -> List[List[float]]:
        """
        Local sentence-transformers se embeddings generate karo.

        🔥 Yeh BINA kisi API key ke kaam karta hai!
        Model sirf ek baar download hota hai (~80MB),
        phir hamesha local se chalta hai.
        """
        try:
            import numpy as np
            embeddings = self.local_model.encode(
                texts,
                show_progress_bar=False,
                batch_size=32,
            )
            return embeddings.tolist()
        except Exception as e:
            logger.error(f"❌ Local embedding failed: {e}")
            return [[0.0] * self.dimension for _ in texts]

    def get_info(self) -> Dict:
        return {
            "method": self.method,
            "display": self.strategy["display"],
            "model": self.model_name,
            "dimension": self.dimension,
            "icon": self.strategy["icon"],
            "needs_key": self.strategy["needs_key"],
            "cost": self.strategy["cost"],
        }
