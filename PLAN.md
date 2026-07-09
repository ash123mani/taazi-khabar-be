# Taazi Khabar — MVP Implementation Plan

> **AI-powered UPSC current affairs platform**  
> Scrape → Summarize → Quiz → Fine-tune custom LLM

---

## File Inventory

### Create (22 files)

| File | Sprint |
|------|--------|
| `backend/.gitignore` | S1 |
| `.gitignore` (root) | S1 |
| `backend/app/ai/config/models.yaml` → move to `backend/config/models.yaml` | S1 |
| `frontend/src/stores/authStore.ts` | S2 |
| `frontend/src/stores/uiStore.ts` | S2 |
| `frontend/src/hooks/useArticles.ts` | S2 |
| `frontend/src/hooks/useQuizzes.ts` | S2 |
| `frontend/src/hooks/useHistory.ts` | S2 |
| `frontend/src/hooks/useAdmin.ts` | S2 |
| `frontend/src/hooks/useAuth.ts` | S2 |
| `frontend/src/components/ThemeProvider.tsx` | S2 |
| `frontend/src/components/Navbar.tsx` | S2 |
| `frontend/src/app/layout.tsx` (replace) | S2 |
| `frontend/src/app/globals.css` (replace) | S2 |
| `frontend/src/app/page.tsx` (replace) | S3 |
| `frontend/src/app/quiz/page.tsx` (replace) | S3 |
| `frontend/src/app/quiz/[id]/page.tsx` | S3 |
| `frontend/src/app/history/page.tsx` (replace) | S3 |
| `frontend/src/app/history/[id]/page.tsx` | S3 |
| `frontend/src/app/auth/login/page.tsx` (replace) | S3 |
| `frontend/src/app/auth/register/page.tsx` (replace) | S3 |
| `frontend/src/app/admin/layout.tsx` | S4 |
| `frontend/src/app/admin/page.tsx` | S4 |
| `frontend/src/app/admin/training-data/page.tsx` | S4 |
| `frontend/src/app/admin/datasets/page.tsx` | S4 |
| `frontend/src/app/admin/models/page.tsx` | S4 |

### Delete (11 files)

| File | Reason |
|------|--------|
| `frontend/tailwind.config.ts` | No Tailwind |
| `frontend/postcss.config.js` | No Tailwind |
| `frontend/src/app/globals.css` (old) | Replaced with Ant Design |
| `frontend/src/app/layout.tsx` (old) | Replaced |
| `frontend/src/app/page.tsx` (old) | Replaced |
| All old page files under `frontend/src/app/` (6 files) | Replaced |

### Modify (16 files)

| File | Change |
|------|--------|
| `backend/pyproject.toml` | Add `requests` dep |
| `backend/Dockerfile` | Fix build order |
| `backend/app/main.py` | Add lifespan, remove engine from deps |
| `backend/app/deps.py` | Remove engine creation, accept from lifespan |
| `backend/app/scrapers/base.py` | Make async |
| `backend/app/scrapers/the_hindu.py` | Use httpx instead of requests |
| `backend/app/scrapers/indian_express.py` | Use httpx instead of requests |
| `backend/app/ai/model_registry.py` | Read-only, configurable path |
| `frontend/package.json` | Add Ant Design, Zustand, React Query; remove Tailwind |
| `frontend/next.config.js` | Add Ant Design config if needed |
| `frontend/src/lib/api.ts` | Add React Query integration |
| `frontend/src/lib/auth.ts` | Review for Ant Design forms |
| `docker-compose.yml` | Update volumes if needed (already correct) |
| `Makefile` | Add frontend setup commands |
| `.env.example` | Already correct, no change needed |

---

## Sprint 1: Backend Fixes (Days 1-3)

### B1 — Add `requests` to deps
**File**: `backend/pyproject.toml`  
**Change**: Add `"requests>=2.31.0"` to dependencies array

### B2 — Fix Dockerfile build order
**File**: `backend/Dockerfile`  
**Bug**: `pip install .` runs before `COPY . .`, so `app/` doesn't exist yet  
**Fix**: 
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
Remove `--reload` for production; dev uses mounted volume anyway

### B3 — Move engine to FastAPI lifespan
**Files**: `backend/app/main.py`, `backend/app/deps.py`  
**Problem**: Engine created at module import time in `deps.py` (line 17)  
**Fix**: 
- `deps.py`: Remove engine creation, accept `async_session_factory` as parameter
- `main.py`: Add lifespan context manager that creates engine, sets it in app.state
- `deps.py`: Read engine from `request.app.state`

### B4 — Model registry read-only
**File**: `backend/app/ai/model_registry.py`  
**Problem**: `set_active_model()` writes to source YAML file  
**Fix**: Remove `_save()` method. `set_active_model()` raises `NotImplementedError`. Config changes go through admin API → DB. Model config path configurable via `SETTINGS`.

### B5 — Async scrapers
**Files**: `backend/app/scrapers/base.py`, `the_hindu.py`, `indian_express.py`  
**Problem**: Sync `requests` + `time.sleep()` block event loop  
**Fix**: 
- `base.py`: Make `fetch_rss()` and `extract_body()` async, use async feedparser (sync is fine wrapped in run_in_executor). Use `httpx.AsyncClient` for HTTP.
- `the_hindu.py`, `indian_express.py`: Use `httpx.AsyncClient` instead of `requests`

### B6 — `.gitignore`
**Files**: `backend/.gitignore` (create), root `.gitignore` (create)  
**Content**:
```
__pycache__/
*.egg-info/
.env
.venv/
```

### B7 — Remove `--reload` from Dockerfile CMD
**File**: `backend/Dockerfile`  
**Reason**: `--reload` is for dev; in Docker Compose, the volume mount handles hot reload. The CMD should be clean for production.

---

## Sprint 2: Repo Split (Day 4)

### Repo Creation
```bash
mkdir -p ../taazi-khabar-backend ../taazi-khabar-frontend
cp -r backend/* ../taazi-khabar-backend/
cp -r frontend/* ../taazi-khabar-frontend/
```

### Root `docker-compose.yml` stays in `taazi-khabar` (orchestration repo)
### Each sub-repo gets its own `docker-compose.yml` for standalone dev

---

## Sprint 3: Frontend Foundation (Days 5-7)

### Install deps
```bash
cd frontend
npm install antd @ant-design/icons zustand @tanstack/react-query
npm uninstall tailwindcss autoprefixer postcss
```

### Create stores (`frontend/src/stores/`)
- `authStore.ts` — user state, login/logout, loading
- `uiStore.ts` — sidebar collapsed, dark mode toggle, theme

### Create hooks (`frontend/src/hooks/`)
- `useArticles.ts` — React Query: list articles, get single
- `useQuizzes.ts` — React Query: generate, fetch, submit
- `useHistory.ts` — React Query: list history, get detail
- `useAdmin.ts` — React Query: training data, datasets, models
- `useAuth.ts` — React Query: login, register, logout

### Create components
- `ThemeProvider.tsx` — Ant Design ConfigProvider with dark/light
- `Navbar.tsx` — Ant Design Layout.Header with menu, user avatar

### Migrate layout
- `layout.tsx` — Ant Design Layout (Header, Sider, Content)
- `globals.css` — minimal Ant Design overrides only

---

## Sprint 4: Core Pages Migration (Days 8-11)

### Pages to migrate (in order)
1. **Home/Feed** (`page.tsx`) — Article list with Ant Design Card, Row, Col, DatePicker filter
2. **Quiz** (`quiz/page.tsx`) — Quiz configuration (select categories, num questions), Button to generate
3. **Quiz Taking** (`quiz/[id]/page.tsx`) — Radio/Checkbox questions, Progress, Timer
4. **History** (`history/page.tsx`) — Table with columns: date, score, topics
5. **History Detail** (`history/[id]/page.tsx`) — Review answers with correct/incorrect indicators
6. **Login** (`auth/login/page.tsx`) — Ant Design Form with Input, Button
7. **Register** (`auth/register/page.tsx`) — Ant Design Form with validation

---

## Sprint 5: Admin Pages Migration (Days 12-14)

### Admin layout
- Ant Design Layout with Sider (vertical menu) + Content area
- Admin guard check on mount

### Pages
1. **Dashboard** (`admin/page.tsx`) — Statistic cards (users, articles, quizzes, interactions)
2. **Training Data** (`admin/training-data/page.tsx`) — Table with search, filter by source/persona
3. **Datasets** (`admin/datasets/page.tsx`) — Dataset builder UI with article selection
4. **Models** (`admin/models/page.tsx`) — Model registry viewer/editor

---

## Sprint 6: Testing + Polish (Days 15-16)

### Testing
- `backend/tests/` — pytest with async tests
- `frontend/` — manual testing pages
- Quiz caching test: generate same article set twice → second returns cached

### Polish
- Responsive design (mobile-friendly Ant Design layouts)
- Dark mode toggle in Navbar
- Loading states (Skeleton, Spin) on all pages
- Error boundaries

---

## Sprint 7: Deployment (Days 17-18)

### Backend → Render
- Web Service from `taazi-khabar-backend` repo
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Env vars from Render dashboard

### Frontend → Vercel
- Import `taazi-khabar-frontend` repo
- Framework preset: Next.js
- Env vars: `NEXT_PUBLIC_API_URL`, `NEXTAUTH_SECRET`, etc.

### Database → Supabase
- Create Supabase project
- Enable pgvector extension
- Run migrations

### AI → NVIDIA NIM
- Get free API key
- Add to Render env vars

### CI → GitHub Actions
- Backend: lint → test → build
- Frontend: lint → build

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| NVIDIA NIM free tier rate limits | Queue requests, cache aggressively |
| pgvector not available on Render | Use Supabase (has pgvector) |
| Scrapers blocked by websites | Respect robots.txt, rotate user agents, cache aggressively |
| LLM generates poor quality quizzes | Prompt engineering iteration, human review in admin panel |
| Quiz caching hash collisions | MD5 of JSON-sorted article IDs + num_questions — collision probability is effectively zero |
| MongoDB not needed | PostgreSQL with pgvector handles both relational data and embeddings |

---

## Architecture Diagram

```
┌─────────────┐     ┌─────────────────────┐     ┌──────────────────┐
│   Browser   │────▶│  Vercel (Next.js)   │────▶│  Render (FastAPI)│
│ (Ant Design)│     │  Zustand + ReactQuery│     │  Async scrapers  │
└─────────────┘     └─────────────────────┘     └────────┬─────────┘
                                                         │
                                            ┌────────────┼────────────┐
                                            ▼            ▼            ▼
                                     ┌──────────┐ ┌──────────┐ ┌──────────┐
                                     │Supabase  │ │  Redis   │ │NVIDIA NIM│
                                     │(PostgreSQL│ │ (Upstash)│ │(Llama 3) │
                                     │+pgvector)│ │          │ │          │
                                     └──────────┘ └──────────┘ └──────────┘
```

---

## Zero-Cost Guarantee

| Component | Free Tier | Limits |
|-----------|-----------|--------|
| Frontend | Vercel | 100 GB bandwidth, 6000 build mins/mo |
| Backend | Render | 750 hours/mo (sleeps after 15 min idle) |
| Database | Supabase | 500 MB, 2 concurrent connections |
| Cache | Upstash Redis | 256 MB, 1000 commands/sec |
| AI | NVIDIA NIM | 1000 reqs/day per API key |
| Fine-tuning | Google Colab | T4 GPU 12h/session |
| Model hosting | HuggingFace Hub | Unlimited public models |
| CI | GitHub Actions | 2000 min/mo |

**Total: $0/mo**
