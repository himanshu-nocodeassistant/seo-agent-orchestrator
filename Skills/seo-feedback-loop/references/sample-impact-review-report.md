# SEO Impact Review — 2026-02-06

**Site:** nocodeassistant.agency
**Review window:** Jan 14 – Feb 6, 2026 (23 days post-implementation)

## Summary
- **Changes reviewed:** 4
- **Positive:** 1 | **Negative:** 1 | **Neutral:** 1 | **Pending:** 1
- **New learnings extracted:** 3
- **Propagation opportunities found:** 4 pages

---

## Change-by-Change Results

### ✅ Title tag — WeWeb agency page — POSITIVE

- **Page:** /weweb-agency
- **Change:** Added deliverable qualifier to title tag ("WeWeb Agency" → "WeWeb Agency for SaaS MVPs & Internal Tools | NocodeAssistant")
- **Evidence:** Moved #11 → #7 for "weweb agency" (confirmed via manual SERP check). CTR improved from 0.8% → 1.4% (approximate, based on GSC data shared). Google adopted the new title fully — visible in the SERP snippet. Also now appearing for "weweb saas development" (#14) where previously unranked.
- **Learning extracted:** buyer-intent-qualifier-in-title — see seo-learnings.md
- **Propagation:** 4 pages identified — see propagation plan below

---

### ❌ H1 change — Homepage — NEGATIVE (recommend: iterate, not rollback)

- **Page:** / (homepage)
- **Change:** H1 "No-code development agency" → "We build internal tools and SaaS MVPs for ops-led teams"
- **Evidence:** Dropped from #4 → #19 for "no-code development agency" (confirmed via manual SERP check — page now on page 2). Now ranking #14 for "internal tool development agency" where previously unranked. Net traffic impact is negative — "no-code development agency" has ~10x the search volume of "internal tool development agency." Session quality metrics appear improved (based on user report) but traffic volume is down.
- **Diagnosis:**

  **Root cause:** The new H1 is 9 words with a niche qualifier ("ops-led teams") that introduces ambiguity. Google's current #1-3 for "internal tool development agency" all use direct 4-6 word H1s: "Custom Internal Tool Builders," "Internal Tools, Built Fast," "Internal Tool Development Agency."

  **What the top 3 are doing differently:**
  - Shorter H1s with zero qualifiers
  - Service name appears first (not "We build...")
  - No audience qualifier in H1 — that lives in subheadings

  **Is this a SERP landscape shift?** Partially yes — the "internal tool development" SERP leans heavily toward "speed" and "custom" signals. Our new H1 doesn't communicate speed.

- **Recommendation:** **Iterate** (do not rollback — direction is right, execution needs refinement)
- **Specific next step:** Change H1 to "Internal Tools & SaaS MVPs, Built Without the Dev Timeline" (7 words, keeps speed signal, drops "ops-led teams" to H2 where it can live as a qualifier without confusing Google's intent matching)

---

### ➖ Meta description — WeWeb agency page — NEUTRAL

- **Page:** /weweb-agency
- **Change:** Rewrote meta from generic brand copy to buyer-focused description with specifics ("4-person team, 50+ builds")
- **Assessment:** Google is partially adopting the new meta — using the first sentence verbatim but replacing the second sentence with a pulled quote from the case studies section. This is an improvement over the previous state (where Google was rewriting the entire meta) but not a full adoption. The pulled quote from case studies ("Blomma went from manual order tracking to fully automated ops in 6 weeks") may actually be a stronger closer than our written CTA. Unclear whether partial adoption is meaningfully helping or hurting CTR.
- **Next check:** 2026-02-28 — check if adoption has stabilized, consider rewriting the second sentence to match what Google is pulling from case studies

---

### ⏳ Schema markup — Case study pages — PENDING (too early)

- **Pages:** /case-studies/blomma, /major, /preplatder
- **Change:** Added Article schema + breadcrumb markup
- **Assessment:** Changes were made Jan 22 — only 15 days ago. Google typically takes 2-4 weeks to process schema changes and surface rich results. Manual SERP check shows no rich results yet. Not enough time to evaluate.
- **Next check:** 2026-02-28

---

## Learnings Banked

Three new learnings added to `.claude/seo-learnings.md`:

1. **buyer-intent-qualifier-in-title** (confidence: medium) — Adding deliverable qualifiers to service page title tags improves rankings and surfaces adjacent long-tail queries
2. **h1-length-affects-intent-matching** (confidence: medium) — Shorter H1s (4-7 words) outperform descriptive ones for competitive service queries; qualifiers belong in H2
3. **google-rewrites-generic-meta** (confidence: low) — Partial meta adoption is a diagnostic signal; what Google pulls from body copy is often a better meta candidate than what we write

---

## Propagation Plans

### Applying: buyer-intent-qualifier-in-title

Pages where the title is currently generic and would benefit from a deliverable qualifier:

1. **/retool-agency** — Currently: "Retool Agency | NocodeAssistant" → Recommended: "Retool Agency for Internal Tools & Dashboards | NocodeAssistant"
2. **/supabase-development** — Currently: "Supabase Development | NocodeAssistant" → Recommended: "Supabase Development for SaaS MVPs & Backends | NocodeAssistant"
3. **/xano-development** — Currently: "Xano Development | NocodeAssistant" → Recommended: "Xano API & Backend Development for No-Code SaaS | NocodeAssistant"
4. **/workflow-automation** — Currently: "Workflow Automation Agency | NocodeAssistant" → Recommended: "Workflow Automation for Ops Teams | NocodeAssistant" *(lower confidence — "ops teams" qualifier may narrow intent too much; test separately)*

Pages where this pattern does NOT apply:
- Homepage — different structural issue (H1 problem, not title problem)
- Blog posts — qualifiers add noise on informational content
- About page — not targeting a service keyword

---

## Recommended Next Actions

1. **This week:** Implement revised H1 on homepage ("Internal Tools & SaaS MVPs, Built Without the Dev Timeline") — the current H1 is actively losing traffic
2. **This week:** Apply title tag pattern to /retool-agency and /supabase-development (highest-traffic service pages)
3. **Feb 28:** Re-check meta description adoption on WeWeb page and schema rich results on case study pages
4. **Ongoing:** Log all changes in seo-changes-log.md before implementing — the H1 change had no baseline snapshot captured, which made impact assessment harder
