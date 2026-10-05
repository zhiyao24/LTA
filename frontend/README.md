# LTA frontend

This directory contains the React, Vite, and TypeScript dashboard. It talks only to the local FastAPI backend configured by `VITE_API_BASE_URL`; never add API keys or Jetson device tokens to a `VITE_` variable.

From the project root:

```sh
npm --prefix frontend install
npm --prefix frontend run dev
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

Pure state logic that needs automated coverage belongs in `src/utils/`. API request code belongs in `src/api/`, shared response types in `src/types/`, screen composition in `src/pages/`, and reusable UI in `src/components/`.

Controls remain disabled when the backend or Jetson is offline, required operator input is absent, or a submission is already running. These browser checks are for safe usability; FastAPI and the Jetson agent remain the actual validation boundaries.
