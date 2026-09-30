# EduGuard: student support and early-warning desktop app

An Electron desktop app (React + Tailwind) with a Python FastAPI backend, built from your
`AI_Project_Setup_Architecture.md`, `Dropout_Risk_Prediction_Frontend.md` and the
`Dropout_Risk_Prediction.md` research. It estimates which students may need support next
term, explains why in plain language, and helps advisors act respectfully and track results.

## Start (Windows)

1. Install **Node.js LTS** and **Python 3.10+** (tick "Add to PATH").
2. Double-click **`setup.bat`** once. It checks Node and Python, runs `npm install`, creates
   `backend\venv`, installs the Python packages, verifies imports, generates demo data and trains
   the model, optionally sets up Ollama, and builds the interface.
3. Double-click **`run_project.bat`** to open the app.

The first launch shows synthetic demo data (no real students). Import your own from **Settings**.


## Vercel deployment

## Vercel 404 recovery

The Vercel project must deploy from the repository root so that `vercel.json`, `frontend/`, and `backend/` are visible together. The live GitHub repository previously had these files flattened into one directory; that layout does not match the Vercel Services configuration. Keep the directories intact. A `VERCEL_DEPLOY.bat` helper is included.

This repository uses Vercel Services with two sibling services: `frontend/` (Vite) and `backend/` (FastAPI). The root `vercel.json` routes `/api/*` to FastAPI and everything else to the frontend. Vercel currently supports this multi-service setup and FastAPI as a framework-defined backend.

For Vercel web sessions, set these environment variables in the Vercel project:

```text
EDUGUARD_SESSION_SECRET=<long-random-secret>
EDUGUARD_DEFAULT_ADVISOR_USERNAME=cheerwin
EDUGUARD_DEFAULT_ADVISOR_PASSWORD=cheer6598
EDUGUARD_DEFAULT_ADVISOR_NAME=Cheerwin (default advisor)
```

The GitHub repository should be connected at the repository root, where `vercel.json`, `frontend/`, and `backend/` are siblings. Do not set Vercel's project root directory to `frontend/` because that would hide the backend service from the deployment.

## How it maps to your architecture file

```text
setup.bat / run_project.bat     setup flow and launcher
package.json, main.js,
preload.js, index.html          Electron shell + React entry
frontend/src/                   components/ pages/ App.jsx main.jsx (your frontend file)
backend/api.py, router.py       FastAPI app and routes
backend/llm.py, agent.py         Gemini / Ollama providers, drafts, briefs, group Q&A
backend/utilities/              data, model, governance, import, bootstrap
models/ai-model/                trained model + model card (created by setup)
logs/app.log                    backend and shell logs
```
Not used: `models/speech-model`, speech recognition, text-to-speech, automation and system-command layers. They don't fit this product.

## What it does (from the research)

* **Estimate, don't label.** Bands are Low / Moderate / Elevated, never "dropout student".
* **No future information.** Features use only weeks 1-8 of a term; evaluation is time-based
  (train on early terms, calibrate on the next, test on the latest).
* **Imbalance-aware and honest.** Class weights, calibrated probabilities, PR-AUC, recall,
  precision, top-10% recall, and comparison against a simple advising rule.
* **Explainable.** Per-student signals in plain language, recent changes, confidence, and data
  freshness. Signals are shown as associations, never causes.
* **Governance gate.** Stale data blocks a score; alerts pause after contact, while a case is
  open, or when dismissed; weekly capacity caps the queue; every action is logged.
* **Responsible ML fairness check.** Gender, first-generation, aid, program and mode are never model inputs. Each tested model is audited on subgroup calibration, flag-rate disparity, false-positive-rate gap and false-negative-rate gap against the overall population; small groups are withheld. Material gaps activate a human-review mitigation gate and are recorded in the model card before the next retraining cycle. The synthetic demo intentionally injects a test-period measurement-bias stress case so this responsible-ML path is visible and repeatable.
  They are used only to audit error rates and whether flagged groups get comparable support.
  IDs are pseudonymous. Small groups are hidden.
* **Human in the loop.** Log support, dismiss with a reason, add notes, prepare a conversation brief, draft a
  message (always reviewed by you, never sent automatically).
* **Screens.** Dashboard, Students, Student details, Ask EduGuard, Interventions, Risk analysis (attendance,
  academic, model card, fairness, drift), Reports (CSV and PDF), Settings, Accounts (advisor only), a sign-in page per role, dark mode, responsive.

## Signing in and accounts

There is a sign-in page for each role: **Academic advisor, Administrator, Faculty, Equity reviewer**. Faculty now have a dedicated **Student review** page with pseudonymous, course-facing evidence; demographic attributes and advisor-only case data remain hidden from that view. An account
only works on the page for its own role.

1. **First launch:** a default academic advisor login is created: username `cheerwin`, password `cheer6598`. Sign in on the
   **Academic advisor** page, then use the key icon in the top bar to set your own password. (The create-first-account
   screen only appears if the default was removed before any account existed.)
2. **The academic advisor creates everyone else** under **Accounts** (sidebar): name, username, role and a temporary
   password (leave it blank to generate one). Give it to the person privately; they must choose their own password at
   first sign-in. The advisor can also change a role, reset a password, switch an account off or on, and delete it.
3. **Settings stays visible to the academic advisor** (and administrators): alert rules, data import, the AI
   assistant and the access log. Only advisors see **Accounts**.
4. The access log records who did what (for example `advisor (a.rao)`), including sign-ins and failed attempts.
5. Five wrong passwords lock that username for 5 minutes. At least one active advisor always remains, and nobody can
   delete, demote or switch off their own account.

**Lost every advisor password?** From the project folder run
`backend\venv\Scripts\python -m backend.utilities.accounts reset-advisor`.

## Registering students

Advisors and administrators open **Register student** (sidebar, or the button on the Students page). Enter a
pseudonymous ID, program and mode, plus this term's GPA, attendance % and assignment completion. Everything else is
optional; anything left blank is estimated and the estimate is marked less certain. The student is saved, scored
immediately with the current model (no retraining) and appears in Students. Gender, first-generation and aid are
optional and used only for the fairness audit. The same range checks as a CSV import apply, duplicate IDs are refused,
and each registration is written to the access log. **Reload demo data** in Settings removes registered students.

## Using your own data

Settings > Data > download the CSV template. One row per student per term. Required columns:
`student_id, term (e.g. 2025-1), gpa, attendance_rate, assignment_completion`. Add `outcome`
(`continued, dropout, transferred, approved_leave, graduated`) for past terms and leave it blank
for the latest term. At least 3 terms of outcomes are needed. Invalid rows are set aside with a
reason and shown after import.

## AI assistant (Google Gemini and/or local Ollama)

The **risk score always comes from the calibrated statistical model**, which is tested against a simple
rule baseline. Language models are not used to score students: they give uncalibrated, hard-to-reproduce
numbers on tabular data. AI is used where it is strong:

| Feature | Where | What the AI sees |
|---|---|---|
| Ask EduGuard (Q&A, leadership summaries) | Ask EduGuard page | Group-level statistics only |
| Conversation brief | Student page | De-identified plain statements ("attendance has been falling"); no ID, name, program, term, dates or numbers |
| Message drafts | Student page | Broad support areas only |

**Turn on Gemini:** create a key at aistudio.google.com/apikey, then open Settings > AI assistant, paste it,
press *Test connection* (lists the models your key can use; the default is `gemini-3.8-flash`), choose what may
be shared, and save. You can also set the `GEMINI_API_KEY` environment variable instead.

**Data-sharing levels** (Settings): *Off*, *Group statistics only*, or *Group statistics and de-identified case
summaries*. The last one needs you to confirm the key belongs to a **paid, billing-enabled** project. Under
Google's terms, unpaid AI Studio content may be used to improve Google products and reviewed by humans, so
do not use a free key for student information. The app enforces the level in code, shows exactly what was sent,
and records every AI call in the access log.

Safety: output is validated (stigmatising words, health or personal guesses and ID-like text are rejected) and
replaced by a template or rule-based brief; nothing is ever sent to a student automatically; the key is stored only in the runtime secrets location (`backend/data` on desktop, `/tmp/eduguard/data` on Vercel) (never returned by the API, in logs or in errors). Ollama
(`ollama pull llama3.2:1b`) remains an option that keeps everything on the machine.

## Please read

* **Demo data is synthetic.** The accuracy shown on it says nothing about your institution.
  Validate on your own historical, time-split data before relying on any score.
* **Sign-in uses local app accounts.** Each person has a username and password, kept as salted scrypt hashes in the
  app's own database. Desktop sessions end when the window closes; Vercel web sessions use a signed token and
  the `EDUGUARD_SESSION_SECRET` environment variable. For a shared institutional deployment, use your identity
  provider (SSO) and a durable database.
* The Electron desktop backend also requires a random per-session header created by Electron.
* Use estimates to offer help, never to deny aid, grades, admission or services.
* Development mode: `npm run dev` (needs the venv from setup).



## Deploying to GitHub + Vercel

EduGuard is organized as a small monorepo: `frontend/` contains the Vite/React web application, `backend/` contains the FastAPI and responsible-ML system, and the repository root keeps the Electron desktop shell plus Vercel configuration. Vercel supports FastAPI and Vite/React deployment patterns.

### GitHub

Push the repository normally. Generated files such as `node_modules`, Python virtual environments, SQLite runtime data, logs, generated model binaries, and Vercel metadata are ignored. GitHub Actions builds the frontend and runs the responsible-ML regression tests on pushes and pull requests.

### Vercel

Connect this repository to a Vercel project and deploy from the repository root. `vercel.json` defines two services: `frontend/` serves the Vite app and the repository-level FastAPI service serves `/api/*`. The rewrite order sends API requests to FastAPI before the frontend catch-all. The browser API client uses same-origin `/api` automatically when the Electron preload bridge is unavailable.

For local Vercel-shaped development, use the current Vercel CLI with `vercel dev -L` from the repository root.

### Demo credentials

Academic Adviser demo account: `cheerwin` / `cheer6598`. For a deployed demo, set `EDUGUARD_DEFAULT_ADVISOR_PASSWORD` as a Vercel environment variable to replace the source default. Optional Gemini support uses `GEMINI_API_KEY`; keep real keys only in environment variables.

### Runtime persistence

The desktop application uses SQLite and local generated model files. In Vercel mode, writable runtime state is redirected to `/tmp/eduguard` because deployment files are immutable. This is suitable for a demonstration or evaluation deployment, but it is not durable shared database storage across serverless instances. For institutional production use, move accounts, students, interventions, audit logs, and other durable state to a managed database.

### Checks after deployment

Open `/api/health` to verify the API is reachable. The frontend also waits for the backend health state before loading the authenticated application.

### Local commands

Desktop: `setup.bat` then `run_project.bat`.

Web frontend: `npm install --prefix frontend` then `npm run dev --prefix frontend`.

Vercel-style combined routing: `vercel dev -L`.
