# What changed in the research-grade upgrade

| Previously missing area | Implemented upgrade |
|---|---|
| Production-grade security | Scrypt password hashes, short-lived JWTs, participant session tokens, token hashing, expiry, request limits, rate limiting, ownership checks, audit events, security headers, production secret validation |
| Complex experiment logic | Trial Groups, repetitions, per-session execution plans, Variables, Set/Increment/Decrement Variable blocks, Branch blocks, counterbalance assignment |
| Real randomization | Cryptographic session seed + deterministic RNG; stored execution plan makes the exact trial order reproducible |
| Conditional branching | Restricted comparison/boolean expression format in participant runner, branch targets validated by backend |
| Lab-grade timing validation | `performance.now()`, double-`requestAnimationFrame` onset anchoring, refresh-rate/jitter diagnostics, visibility flags, stored timing timestamps |
| Production-scale SaaS infrastructure | PostgreSQL, Redis, connection pooling, Alembic migrations, Docker health checks, multiple Uvicorn workers, separate frontend containers |
| Consent / ethics workflow | Configurable consent version/text, server-recorded acceptance timestamp, required consent gate, debrief message, consent metadata in exports |
| Full research-oriented platform | Researcher builder + participant runner + published versions + session plan + timing data + results JSON/CSV + audit trail |

This remains a sophisticated prototype rather than a validated scientific instrument. The timing layer needs empirical validation on the exact browsers, operating systems, displays, and input hardware used by a real study.
