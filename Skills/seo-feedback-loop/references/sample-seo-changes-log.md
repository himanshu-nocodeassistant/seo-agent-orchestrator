# SEO Changes Log

---

## Entry: 2026-01-14 — Title tag rewrite on WeWeb agency page

- **Page:** https://nocodeassistant.agency/weweb-agency
- **Change type:** title tag
- **What was changed:** "WeWeb Agency | NocodeAssistant" → "WeWeb Agency for SaaS MVPs & Internal Tools | NocodeAssistant"
- **Source:** seo-audit conversation (Jan 12 2026) — audit flagged title as generic, not matching commercial intent of "weweb agency" queries
- **Baseline snapshot:** Ranking ~#11 for "weweb agency", CTR 0.8% (GSC), 0 branded SERP snippet
- **Status:** reviewed-positive

**Review notes 2026-02-06:**
Google adopted the new title within ~10 days. Moved from #11 → #7 for "weweb agency". CTR improved to 1.4%. The keyword "SaaS MVPs" in the title appears to be pulling in adjacent queries ("weweb saas development") where we weren't ranking before. Learning extracted: freshness-anchor-in-title.

---

## Entry: 2026-01-14 — Meta description rewrite on WeWeb agency page

- **Page:** https://nocodeassistant.agency/weweb-agency
- **Change type:** meta description
- **What was changed:** Generic brand description → "We build WeWeb apps for COOs and ops leads who need an internal tool or SaaS MVP without a 6-month dev timeline. 4-person team, 50+ builds."
- **Source:** seo-audit conversation (Jan 12 2026) — old meta wasn't being used by Google at all (rewriting it entirely)
- **Baseline snapshot:** Google was rewriting the snippet to pull from body copy
- **Status:** reviewed-neutral

**Review notes 2026-02-06:**
Google is still partially rewriting the snippet — using our opening sentence but replacing the second half with a pulled quote from the case studies section. Not a regression, but the description hasn't been fully adopted. Not enough signal yet. Next check: 2026-02-28.

---

## Entry: 2026-01-20 — H1 change on homepage

- **Page:** https://nocodeassistant.agency/
- **Change type:** heading structure
- **What was changed:** H1 "No-code development agency" → "We build internal tools and SaaS MVPs for ops-led teams"
- **Source:** seo-audit conversation (Jan 12 2026) — H1 was ranking for dev-intent queries, not buyer-intent queries; audience mismatch
- **Baseline snapshot:** Ranking #4 for "no-code development agency" (high volume, wrong audience), not ranking for "internal tool development agency" (correct audience)
- **Status:** reviewed-negative

**Review notes 2026-02-06:**
Dropped from #4 → #19 for "no-code development agency" within 3 weeks. Now ranking #14 for "internal tool development agency" (was unranked). Net traffic impact: negative — the lost traffic from the no-code query is higher volume than the new internal tool query. However, the quality of sessions from "internal tool" queries is significantly higher (longer time on page, more demo requests). Diagnosis: correct directional move but needs iteration — the new H1 is too long and not being fully interpreted by Google. Recommendation: iterate (not rollback). See diagnosis below.

**Diagnosis:**
- Top 3 for "internal tool development agency": H1s are all 4-7 words, very direct ("Custom Internal Tools Built Fast", "Internal Tool Development Agency")
- Our H1 at 9 words with "ops-led teams" qualifier is confusing Google's intent matching
- Recommendation: shorten H1 to "Internal Tools & SaaS MVPs Built Without the Dev Timeline" and move qualifier to H2

---

## Entry: 2026-01-22 — Schema markup added to case study pages

- **Page:** https://nocodeassistant.agency/case-studies/blomma, /major, /preplatder
- **Change type:** schema
- **What was changed:** Added Article schema with author, datePublished, and breadcrumb markup to 3 case study pages
- **Source:** seo-audit conversation (Jan 12 2026) — no structured data on case study pages, missing rich result opportunities
- **Baseline snapshot:** No rich results showing in SERPs for any case study page
- **Status:** pending-review

---
