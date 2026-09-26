# WebLab API Contract
Backend: Python + FastAPI. Persistence: SQLite via SQLAlchemy (simple, file-based, no external DB server needed for a hackathon).
Base URL (dev): http://localhost:8000

## Data Shapes

### Experiment
{
  "id": "string (uuid)",
  "name": "string",
  "instructions": "string",
  "status": "draft" | "active",
  "createdAt": "ISO datetime string",
  "trials": [Trial],
  "settings": {
    "randomizeOrder": boolean,
    "conditionalRules": [ConditionalRule]
  }
}

### Trial
{
  "id": "string",
  "stimulus": { "type": "text" | "image", "content": "string", "style": {} },
  "durationMs": number,
  "responseType": "keypress" | "click",
  "validResponses": ["string"],
  "correctAnswer": "string",
  "condition": ConditionalRule | null
}

### ConditionalRule
{ "ifTrialId": "string", "ifResponseEquals": "string", "thenAction": "skipTo", "targetTrialId": "string" }

### Participant
{ "participantId": "string", "experimentId": "string", "startedAt": "ISO datetime string" }

### ResultEntry
{
  "participantId": "string",
  "experimentId": "string",
  "trialId": "string",
  "stimulusShownAt": number,   // client performance.now() timestamp, informational
  "responseAt": number,        // client performance.now() timestamp, informational
  "reactionTimeMs": number,    // computed client-side, sent as-is
  "response": "string",
  "correct": boolean,
  "timestamp": "ISO datetime string"
}

## Endpoints

### POST /experiments
Create a new experiment (draft, empty trials).
Request body: { "name": "string", "instructions": "string" }
Response 201: Experiment

### GET /experiments
List all experiments (summary view for dashboard).
Response 200: [Experiment]

### GET /experiments/{id}
Get one full experiment (for builder/preview).
Response 200: Experiment | 404

### PUT /experiments/{id}
Update an experiment (trials, settings, instructions, name). Full replace of trials/settings.
Request body: Partial<Experiment> (any subset of: name, instructions, trials, settings)
Response 200: updated Experiment | 404

### POST /experiments/{id}/launch
Set status to "active". No body.
Response 200: updated Experiment | 404

### GET /experiments/{id}/public
Participant-facing experiment view. MUST strip "correctAnswer" from every trial 
before returning (so participants can't inspect it via devtools/network tab).
Response 200: Experiment (with correctAnswer omitted from each trial) | 404 
  | 400 if status != "active"

### POST /experiments/{id}/participants
Create a new anonymous participant/session for this experiment.
Request body: {} (empty)
Response 201: Participant  (backend generates participantId, e.g. "P-4821")

### POST /experiments/{id}/results
Submit one result entry (called once per trial, or batched as an array at the end 
— backend accepts either a single ResultEntry object OR an array of ResultEntry).
Request body: ResultEntry | [ResultEntry]
Response 201: { "saved": true }

### GET /experiments/{id}/results
Get all results for an experiment (for the researcher's Results Dashboard).
Response 200: [ResultEntry]

## Error format (all errors)
{ "detail": "human-readable message" }

## CORS
Backend must enable CORS for the frontend's dev origin (e.g. http://localhost:5173) 
so fetch() calls from React work in local dev.

## Change process
Do not edit existing entries above without flagging it to the team first. 
Add new entries under a "## Proposed additions" section at the bottom if you need 
something not yet defined, and note it in your PR description.