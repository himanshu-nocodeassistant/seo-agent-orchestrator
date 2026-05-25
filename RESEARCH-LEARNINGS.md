# Research: SEO Agent & Claude Agent Learnings

Research conducted on external repos, blogs, and patterns for building SEO agents.

---

## 1. Claude Agent Architecture Patterns

### Tool-Use Agent Loop
```
User Message → Claude Reasons → Tool Call → Result → Repeat until done
```

- Tools defined with JSON schema for input validation
- Loop exits on `end_turn` stop reason
- Your `allowed_tools` in `AgentConfig` matches this

### Planner/Executor/Synthesizer Pattern
Three specialized roles:
- **Planner** = your `ResearchAgent` (breaks tasks into subtasks)
- **Executor** = your `ContentAgent`/`TechnicalSEOAgent` (completes each step)
- **Synthesizer** = orchestrator combining outputs

**Your `AGENT_PIPELINE` registry IS this pattern with deterministic routing.**

### Memory-Augmented Agent
- Claude writes structured updates to JSON store at end of each turn
- Future turns include store in system prompt
- Pattern: `<memory_update>{...}</memory_update>` blocks

**Your `memory/seo-changes.json` and `memory/seo-learnings.json` implement this.**

---

## 2. SEO Agent Workflows by Value

| Workflow | Frequency | Automation Value |
|----------|-----------|------------------|
| SEO Audits | One-time + quarterly | **High** |
| Content Briefs | Per-article | **High** |
| Schema Markup | Per-page | **High** |
| Feedback Loop / Impact Review | 2-4 weeks post | **High** |
| Programmatic SEO | Scale operations | **High** |
| Title/Meta Optimization | Per-page | Medium |
| Technical fixes (alt text, links) | Per-page | Medium |

---

## 3. Multi-Agent Patterns (LangChain, AutoGen, CrewAI)

### Deterministic Routing Beats Dynamic
From DECISIONS.md: *"Deterministic routing beats dynamic tool selection for production systems. When you can predict what will happen, you can debug it."*

### Specialist Agent Tool Whitelisting (Least Privilege)
```
ResearchAgent:    WebSearch, WebFetch only
ContentAgent:     Read, Write, Edit, Skill, Google Docs
AnalyticsAgent:    Read, WebFetch, Bash (read-only)
TechnicalSEOAgent: WebFetch, Skill, Read, Write
```

### Pipeline Registry Pattern
```python
AGENT_PIPELINE: dict[str, list[str]] = {
    "research":            ["ResearchAgent"],
    "rewrite_title":      ["ResearchAgent", "ContentAgent"],
    "blog_write":         ["ResearchAgent", "ContentAgent"],
    "update_schema":      ["TechnicalSEOAgent"],
    "seo_impact_review":  ["AnalyticsAgent"],
    ...
}
```

---

## 4. External SEO Agent Implementations Found

### Single-Agent (Monolithic)
- `dannwaneri/seo-agent`: Browser Use + Claude API + Playwright
- `calderbuild/SEO_Agent`: Single agent for URL audits
- `serpapi/seo-agent`: SerpApi + OpenAI

### Multi-Agent / Pipeline
- `jadedagher/seo-agent-stack`: Analyze → Rewrite → Publish pipeline

---

## 5. Recommendations for This Project

1. **Your architecture is solid** - 4-specialist model matches industry best practices
2. **Consider adding supervisor logging** - Track which agent handles each step
3. **Implement retry logic** for failed tool calls
4. **Add validation layer** between agents for output quality
5. **Tighten feedback loop integration** - skill exists but could be more automated
6. **Programmatic SEO** - expand templated page generation capabilities

---

## 6. Resources Referenced

- `jasherjoshuachan/claude-agent-patterns` - Official Claude agent patterns
- `dannwaneri/seo-agent` - Single-agent SEO implementation
- `calderbuild/SEO_Agent` - URL audit agent
- `jadedagher/seo-agent-stack` - Multi-agent SEO pipeline
- LangChain/AutoGen/CrewAI multi-agent architectures