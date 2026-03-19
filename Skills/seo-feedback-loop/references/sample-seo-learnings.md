# SEO Learnings — NocodeAssistant

*Extracted principles from completed feedback loop reviews. Each learning must be supported by at least one confirmed positive result before being applied to other pages.*

---

## Learning: buyer-intent-qualifier-in-title

- **Discovered:** 2026-02-06
- **Evidence:** WeWeb agency page. Changed generic title ("WeWeb Agency | NocodeAssistant") to include specific use-case qualifier ("for SaaS MVPs & Internal Tools"). Moved #11 → #7, CTR 0.8% → 1.4% over 3 weeks.
- **Principle:** For service pages targeting agency/vendor queries, including a specific deliverable qualifier (what you build, not just who you are) in the title tag improves rankings and CTR. Google interprets this as higher relevance to commercial-intent queries. It also surfaces the page for adjacent long-tail queries containing those deliverable terms.
- **Applicable when:** Service pages targeting "[tool/platform] + agency" or "[tool/platform] + development" queries. Especially strong when current title is just "Brand | Service Category."
- **Not applicable when:** Branded pages where the user is already searching by name. Blog posts — qualifier adds noise. Pages where the deliverable is already the primary keyword.
- **Confidence:** medium (single page, needs replication on 1-2 more pages)

---

## Learning: h1-length-affects-intent-matching

- **Discovered:** 2026-02-06
- **Evidence:** Homepage H1 change. New H1 ("We build internal tools and SaaS MVPs for ops-led teams") ranked for the right audience keywords but underperformed commercially. Analysis of top 3 competitors showed all have 4-7 word H1s with no qualifiers.
- **Principle:** For competitive, high-intent service queries, shorter H1s (4-7 words) that name the exact service outperform descriptive H1s. Google's intent matching appears to weight exact-match alignment over completeness. Qualifiers ("for ops-led teams") belong in H2, not H1.
- **Applicable when:** Homepage and primary service pages targeting "X agency" or "X development" queries with 3+ strong competitors.
- **Not applicable when:** Blog posts and informational pages where descriptive titles improve CTR. Long-tail pages where the full phrase IS the keyword.
- **Confidence:** medium (derived from negative result + competitive analysis, not yet confirmed via positive test)

---

## Learning: google-rewrites-generic-meta

- **Discovered:** 2026-02-06
- **Evidence:** Meta description on WeWeb agency page. Old generic meta was being completely rewritten by Google. New buyer-focused meta was adopted partially (first sentence used, second sentence replaced by pulled case study quote).
- **Principle:** Google rewriting a meta description is a signal that the page's meta doesn't match what users searching that query expect. Partial adoption (first sentence accepted) means the opening hook is working but the close isn't. The solution is to write metas that match what Google would pull anyway — lead with the differentiating claim, end with the CTA. If Google keeps pulling body copy instead, the body copy may be more compelling and should inform a meta rewrite.
- **Applicable when:** Any page where GSC shows low CTR despite reasonable rankings. Any page where you've confirmed via live SERP check that Google is rewriting your snippet.
- **Not applicable when:** Branded/navigational queries — Google often rewrites those regardless of meta quality.
- **Confidence:** low (single page, partial adoption — needs more data)

---

*Template for new learnings:*

```markdown
## Learning: [kebab-case-name]

- **Discovered:** [YYYY-MM-DD]
- **Evidence:** [Page, change, measurable result]
- **Principle:** [The generalizable rule — why, not just what]
- **Applicable when:** [Conditions]
- **Not applicable when:** [Anti-conditions]
- **Confidence:** high | medium | low
```
