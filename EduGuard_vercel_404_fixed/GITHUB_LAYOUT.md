# EduGuard Repository Layout

This repository must preserve the directory structure exactly:

```text
EduGuard/
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.mjs
│   └── src/
├── backend/
│   ├── main.py
│   ├── api.py
│   ├── router.py
│   ├── services.py
│   ├── requirements.txt
│   └── pyproject.toml
├── models/
├── .github/
├── vercel.json
├── package.json
└── main.js
```

Do not move the contents of `frontend/` or `backend/` into the repository root. Vercel Services resolves each service using the `root` paths in `vercel.json`.
