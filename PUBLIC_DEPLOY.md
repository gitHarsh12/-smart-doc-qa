# 🌐 Public Deploy Guide — Resume Portfolio App

Bhai, yeh guide teri situation ke liye exact hai:
- **API keys:** Groq + OpenRouter (NVIDIA baad me add karega)
- **Goal:** Public app, sabke liye open (recruiters dekh sake)
- **Resume me:** Streamlit link daalna hai

## ✅ Haan, App Completely Ready Hai!

Sab kuch ho gaya:
- ✅ All 27 audit fixes applied
- ✅ Public Demo Mode enabled (no auth — sab access kar sakte hain)
- ✅ Quota protection (100 queries/day total, 5 per user per 15 min)
- ✅ Demo banner + branding (recruiter ko professional lagega)
- ✅ Graceful "quota exceeded" message (no ugly API errors)
- ✅ Sidebar me live quota display

---

## 🚀 Tera Action Plan (Step-by-Step)

### **STEP 1: GitHub pe code push karo**

```bash
# Fixed_app folder me ja
cd fixed_app

# Git init + commit
git init
git add .
git commit -m "Public demo mode ready - RAG portfolio app"

# GitHub pe new repo bana (PRIVATE recommended tere code ke liye)
# https://github.com/new → "Private" select kar

# Push karo
git remote add origin https://github.com/YOUR_USERNAME/rag-app.git
git branch -M main
git push -u origin main
```

⚠️ **Push se pehle check kar — secrets leak na ho:**
```bash
git ls-files | grep -E "(secrets.toml|.env)"
# Output EMPTY hona chahiye — warna STOP!
```

### **STEP 2: Streamlit Cloud pe app banao**

1. Jaa: https://share.streamlit.io/
2. **"Create app"** → "From existing repo"
3. Fill karo:
   - **Repository:** `YOUR_USERNAME/rag-app`
   - **Branch:** `main`
   - **Main file path:** `app.py`
   - **App URL (slug):** `harsh-rag-demo` (ya jo tera naam hai)
4. **"Advanced settings"** khol:
   - **Python version:** 3.11
   - **Secrets** box me niche wala content paste kar (STEP 3)

### **STEP 3: Secrets.toml paste karo (Groq + OpenRouter only)**

Streamlit Cloud → Secrets box me yeh paste kar:

```toml
# 🚀 Tere paas jo keys hain, wo daal
GROQ_API_KEY      = "gsk_teri-groq-key-yahan"
OPENROUTER_API_KEY = "sk-or-v1_teri-openrouter-key-yahan"

# NVIDIA baad me add karna ho to uncomment kar:
# NVIDIA_API_KEY    = "nvapi-teri-nvidia-key-yahan"

# ── Branding (resume ke liye) ──
OWNER_NAME        = "Harsh Bokde"
DEFAULT_PROVIDER  = "groq"   # Groq sabse fast hai, demo ke liye perfect

# ── Apne social links add kar (recruiter click kar sake) ──
GITHUB_URL        = "https://github.com/YOUR_USERNAME"
LINKEDIN_URL      = "https://linkedin.com/in/YOUR_PROFILE"

# ── Logging level ──
LOG_LEVEL         = "INFO"
```

> 💡 Groq free tier: 30 req/min, 14400 req/day — demo ke liye PERFECT.
> OpenRouter free tier: 50 req/day (Claude/GPT) + unlimited free models.
> 100 queries/day quota se tera cost ZERO rahega.

### **STEP 4: Deploy!**

1. **"Deploy!"** button click kar
2. 2-5 minute wait — first deploy slow hota hai (dependencies install)
3. App live ho jayega: `https://harsh-rag-demo.streamlit.app`

### **STEP 5: Test karo (deploy ke baad)**

```bash
# Browser me khol
open https://harsh-rag-demo.streamlit.app

# Test 1: Document upload (chhota PDF, <5MB)
# Test 2: Question puch (e.g., "summary batao")
# Test 3: 5 questions puch → quota message aana chahiye
# Test 4: Kal dobara khol → quota reset ho gaya hoga
```

---

## 📝 Resume Me Kaise Add Kare

**Resume bullet (suggested):**

> **Smart Document Q&A — AI/ML Portfolio Project** | [Live Demo](https://harsh-rag-demo.streamlit.app) | [GitHub](https://github.com/YOUR_USERNAME/rag-app)
>
> Built a production-grade RAG application with Streamlit supporting 30+ document formats (PDF, DOCX, XLSX, images, EPUB) using NVIDIA/Groq/OpenRouter LLMs, FAISS vector search, semantic caching, and OCR fallback chain. Implemented multi-layer security hardening (XSS protection, prompt injection defense, rate limiting, ZIP bomb prevention) based on a 27-finding code audit. Public demo deployed with quota-protected free-tier APIs.

**LinkedIn me:**
- "Projects" section me add kar
- Thumbnail: app ka screenshot
- Description me live link + GitHub link

---

## 🆘 Troubleshooting

### **"No API keys configured"**
Secrets box me check kar:
- `GROQ_API_KEY` value `"gsk_..."` se start hona chahiye
- Quotes me daala hai? (`"gsk_xxx"` sahi, `gsk_xxx` galat)
- App restart kar (Streamlit Cloud → "Reboot app")

### **"Rate limited" bahut jaldi aata hai**
Groq free tier = 30 req/min. Quota settings adjust kar:
- File: `modules/config.py`
- Line: `DEMO_PER_USER_QUOTA: int = 5` → change to `10` ya `15`

### **"Daily quota reached" — recruiter ko dikha**
Yeh EXPECTED behavior hai. Daily 100 queries cap hai.
Options:
1. **Wait kal ke liye** (quota auto-reset at midnight UTC)
2. **Increase limit:** `modules/config.py` → `DEMO_DAILY_GLOBAL_QUOTA: int = 100` → `300`
3. **Reset manually:** Streamlit Cloud → "Reboot app" (clears `.quota_state.json`)

### **App sleep ho gaya (7 days inactive)**
Streamlit Cloud free tier pe apps 7 din baad sleep hote hain.
Fix: Kisi bhi visitor ka request app ko "wake" karega (~30s delay).
Resume link share karne se pehle khud ek baar khol lena.

### **NVIDIA key baad me add karna ho**
1. https://build.nvidia.com/ pe account banao (1000 free credits)
2. Streamlit Cloud → app settings → Secrets → edit
3. Add line: `NVIDIA_API_KEY = "nvapi_xxx"`
4. Save → app auto-restart

---

## 💡 Pro Tips for Recruiters

1. **Sample docs ready rakh** — kuch chhote PDFs (1-2 pages) apne Google Drive pe rakh. Recruiter se bol "yeh sample upload karo". Easy testing.

2. **App "always warm" rakh** — free tier pe 7 days baad sleep. Cron-job.org pe daily 1 request schedule kar (app ko ping karega).

3. **README.md GitHub pe achha rakh** — recruiter GitHub link bhi khol sakta hai. Screenshots + setup instructions daal.

4. **Don't commit secrets** — `.gitignore` already set hai. Still, double-check:
   ```bash
   git log --all --diff-filter=D -- "*.env" "*.toml"
   ```

5. **Streamlit Cloud app URL short** — `harsh-rag-demo.streamlit.app` better than random hash. Custom slug set kar.

---

## 🎯 Final Checklist

Before sharing resume link publicly:

- [ ] GitHub repo created (private)
- [ ] Code pushed (secrets NOT in repo)
- [ ] Streamlit Cloud app deployed
- [ ] Secrets.toml configured (Groq + OpenRouter keys)
- [ ] OWNER_NAME set to tera naam
- [ ] GITHUB_URL + LINKEDIN_URL set in secrets
- [ ] App URL tested (document upload + question works)
- [ ] Quota display visible in sidebar
- [ ] Daily quota reset working (test tomorrow)
- [ ] Resume + LinkedIn updated with live link

Bhai, ab tu production-ready hai. App deploy kar, link share kar, recruiter ko impress kar! 🚀💪
