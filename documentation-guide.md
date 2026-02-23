### Core files
CLAUDE.md (or AGENTS.md) — architecture decisions, coding conventions, what tools/stack is used, and any patterns the AI should follow consistently
README.md — project overview, setup instructions, how to run locally
CHANGELOG.md — what changed and when (especially useful across multiple AI sessions)

### Code-level docs
Inline comments for non-obvious logic, especially in complex queries or business rules
JSDoc/docstrings for all functions — parameters, return types, purpose
Type definitions (or at least a types file if using TypeScript)

### Architecture
ARCHITECTURE.md or a docs/ folder with a system diagram — data flow, how services connect, auth flow
Database schema with column-level comments explaining why certain decisions were made, not just what they are
API documentation (endpoint, method, expected payload, response shape)

### Operational
.env.example — all required environment variables with descriptions
DECISIONS.md — a log of significant technical decisions and the reasoning behind them