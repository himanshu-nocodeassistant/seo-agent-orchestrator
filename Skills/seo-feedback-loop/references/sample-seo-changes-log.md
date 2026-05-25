# SEO Changes Log — Template

> This is a sample file showing the correct format for the changes log.
> Copy this format when creating your own `seo-changes-log.md` file.

<!-- CHANGE_LOG {"version": 1, "created": "2024-01-01", "site": "yoursite.com"} -->

## Change Entry Template

- **Page:** [URL]
- **Change type:** [title tag | meta description | heading | content | schema | etc.]
- **Before:** [Previous value]
- **After:** [New value]
- **What was changed:** [Specific description]
- **Source:** [Which audit or conversation recommended this]
- **Baseline snapshot:** [Metrics captured at time of change]
- **Review status:** [pending | reviewed]
- **Impact:** [positive | negative | neutral | pending]

## Example Entry

```markdown
- **Page:** https://example.com/service-page
- **Change type:** title tag
- **Before:** "Service Page | Example Inc"
- **After:** "Custom Software Development for Small Business | Example Inc"
- **What was changed:** "Service Page" → "Custom Software Development for Small Business"
- **Source:** SEO audit conversation (Jan 12 2024)
- **Baseline snapshot:** Position #15 for "custom software development", CTR 1.2%
- **Review status:** pending
- **Impact:** pending
```

## Review Status Types

- **pending** — Change implemented, waiting for impact window (2-4 weeks)
- **positive** — Metrics improved after the change
- **negative** — Metrics declined after the change
- **neutral** — No measurable impact
- **insufficient_data** — Not enough data to determine impact

## Impact Documentation

When updating a change with review status:

```markdown
- **Review status:** positive
- **Impact:** 
  - Ranking: #15 → #8 for "custom software development"
  - CTR: 1.2% → 2.1%
  - Traffic: +45% over 4 weeks
- **Review date:** 2024-02-15