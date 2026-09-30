# EduGuard Vercel 404 Fix

This package is structured as a Vercel Services monorepo:

- `frontend/` — React + Vite web service
- `backend/` — FastAPI service exposed through `/api/*`
- `vercel.json` — root service routing

Important: the Vercel project must be linked at the repository root so that the root `vercel.json`, `frontend/`, and `backend/` are part of the deployment. The root route is explicitly rewritten to the frontend service and `/api/*` is routed to FastAPI.

The frontend API client also normalizes `/api` paths so calls such as `/api/health` do not become `/api/api/health` in web deployments.
