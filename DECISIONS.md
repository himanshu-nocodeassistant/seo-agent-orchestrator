# Technical Decisions

## Reliability and recovery

### Small self-hosted deployment

SQLite remains the default because the service is designed for one local
process. WAL mode and short transactions support concurrent API requests and
background work. A queue and PostgreSQL are the next scaling steps.

### Database-backed claims and leases

Tasks, campaign phases, and comment actions use database claims. Run leases
and heartbeats allow stale work to be detected. Ownership checks prevent an
old worker from completing a newer run or creating side effects.

### Database tracing

Run lifecycle and tool events use the same database as run state. Each event
stores the request ID and run ID. The API exposes paginated events for
diagnosis without loading an unbounded event list.

### DataForSEO uncertainty

Paid task-creation requests are not retried automatically. If the response is
uncertain, the client writes a recovery manifest with the request, known task
IDs, and partial results. Operators recover with read-only polling instead of
resubmitting paid work.
