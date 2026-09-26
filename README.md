# LabForge Participant UI

Browser-based participant runner for the existing FastAPI Experiment API.

## Run locally

```powershell
npm install
npm run dev -- --port 5174
```

Open either:

- http://localhost:5174/?slug=your-published-slug
- http://localhost:5174/your-published-slug

The app consumes the existing public endpoints:

- `GET /api/v1/public/experiments/{slug}`
- `POST /api/v1/public/experiments/{slug}/sessions`
- `POST /api/v1/public/sessions/{session_id}/responses`
- `POST /api/v1/public/sessions/{session_id}/complete`

## Current supported blocks

- instruction
- fixation
- stimulus: text, image, audio, video, html, color
- response
- delay

Reaction time is measured on the participant device with `performance.now()` and sent alongside server receipt timestamps. This is designed to preserve client timing; it does not claim laboratory-hardware equivalence.
