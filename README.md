# ADU Copilot AI

California ADU Compliance AI Audit Tool — upload your PDF, get instant code compliance analysis, and receive AI-powered remediation guidance.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, TypeScript, Tailwind CSS, shadcn/ui |
| Charts | recharts (compliance radar) |
| Markdown | react-markdown + remark-gfm |
| PDF (client) | pdf-lib (page extraction for large files) |
| Auth | Supabase Auth (email/password + Google OAuth) |
| Backend | FastAPI (Python), streaming responses |
| PDF (server) | pypdf (text extraction) |
| AI | Gemini (primary) + DeepSeek (fallback) |
| DB | Supabase (user credits) |
| Payments | LemonSqueezy |

## Features

- **Splash Screen** — background image with "Get Started" entry
- **EN/ZH i18n** — full UI + backend audit results + AI prompts in English and Chinese
- **PDF Upload** — drag & drop with >5MB page selector (client-side pdf-lib trimming)
- **AI Parameter Extraction** — Gemini native PDF understanding, falls back to pypdf + DeepSeek
- **Parameter Form** — 24 fields, foldable sections, manual editing
- **Compliance Audit** — deterministic rule engine based on California HCD ADU Handbook (30 credits)
- **Radar Chart** — recharts visualization of compliance dimensions
- **Pass/Fail Checklist** — detailed results per rule with citations
- **AI Advice** — DeepSeek remediation guidance in Markdown with table support (50 credits)
- **Export** — download advice as `.md` file
- **Credits System** — LemonSqueezy recharge flow
- **Toast Notifications** — non-blocking error/success messages
- **Streaming** — Vercel-compatible keepalive responses for long-running AI calls

## Project Structure

```
adu-audit/
├── api/
│   └── index.py            # FastAPI backend (extract, audit, advise, credits, webhook)
├── app/
│   ├── components/         # UI components
│   ├── providers/          # Auth + Language contexts
│   ├── layout.tsx           # Root layout
│   ├── page.tsx             # Main SPA
│   └── globals.css          # Tailwind + shadcn theme + background
├── components/ui/          # shadcn primitives (Button, Card, Dialog, etc.)
├── lib/
│   ├── i18n.ts             # Translation dictionaries (EN/ZH, 80+ keys)
│   ├── api.ts              # Frontend API layer
│   ├── supabase.ts         # Supabase client
│   └── utils.ts            # cn() utility
├── public/
│   └── backgroup.png       # Background image
├── vercel.json             # Vercel hybrid deploy (Next.js + Python API)
├── requirements.txt        # Python dependencies
└── package.json            # Node dependencies
```

## Getting Started

### Prerequisites

- Python 3.10+, Node.js 20+, Supabase project

### Environment Variables

**`.env`** (Python backend):

```env
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
GEMINI_API_KEY=xxx
GEMINI_MODEL=gemini-2.5-flash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=xxx
SUPABASE_JWT_SECRET=xxx
SUPABASE_ANON_KEY=xxx
SIGNUP_CREDITS=100
```

**`.env.local`** (Next.js frontend):

```env
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=xxx
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Run Locally

```bash
# Terminal 1 — Python API
.venv\Scripts\uvicorn api.index:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Next.js
npm install && npm run dev
```

Open **http://localhost:3000**

### Supabase Setup

1. Create `user_credits` table: `id` (uuid), `user_id` (text, unique), `credits` (int4)
2. Auth > URL Configuration: Site URL = `http://localhost:3000`, Redirect URLs = `http://localhost:3000/**`

## API Endpoints

| Method | Path | Auth | Cost | Description |
|--------|------|------|------|-------------|
| POST | /api/extract | No | Free | PDF extraction (streaming, `?lang=en\|zh`) |
| POST | /api/audit | JWT | 30 | Rule compliance audit (`?lang=en\|zh`) |
| POST | /api/advise | JWT | 50 | AI remediation advice (streaming, `lang` in body) |
| GET | /api/credits | JWT | Free | Credit balance |
| POST | /api/webhooks/lemonsqueezy | HMAC | Free | Payment webhook |
| GET | /api/health | No | Free | Health check |
