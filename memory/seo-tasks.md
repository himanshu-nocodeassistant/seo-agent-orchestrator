# SEO Task Backlog

## Audit: example.com
- **Audit Date:** 2026-03-03
- **Pages Audited:** https://example.com (homepage)
- **Total Tasks:** 24 (11 simple, 4 parent tasks with 13 subtasks)

---

## 🔴 Critical Tasks

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| EX-001 | 🔴 Critical | On-Page | Small | Write and add meta description to homepage | Missing entirely — direct CTR loss in SERPs | |
| EX-002 | 🔴 Critical | Technical | Small | Create /robots.txt file | Currently 404 — crawlers have no direction; risk of crawl waste | |
| EX-003 | 🔴 Critical | Technical | Small | Generate and submit XML sitemap at /sitemap.xml | Missing 404 — Google must discover pages on its own | |
| EX-004 | 🔴 Critical | Technical | Small | Add canonical tag to homepage `<link rel="canonical">` | No canonical = duplicate content risk (www vs non-www, http vs https) | |
| EX-005 | 🔴 Critical | Technical | Small | Add twitter:card meta tag to homepage | Twitter previews render blank without it | |
| EX-006 | 🔴 Critical | Technical | Small | Create and serve favicon.ico at /favicon.ico | Currently 404 — console error logged on every page load | |
| EX-010 | 🔴 Critical | On-Page | Medium | Add all Open Graph tags to homepage | Social shares look broken — no preview image, title, or description | |
| EX-011 | 🔴 Critical | On-Page | Small | Add og:title to homepage | Required for Facebook/LinkedIn previews | EX-010 |
| EX-012 | 🔴 Critical | On-Page | Small | Add og:description to homepage | Controls social snippet text | EX-010 |
| EX-013 | 🔴 Critical | On-Page | Medium | Source/design OG image (1200×630px) for homepage | og:image is the most clicked element in social previews | EX-010 |
| EX-014 | 🔴 Critical | On-Page | Small | Add og:image and og:url to homepage | Completes Open Graph implementation | EX-010 |

---

## 🟠 High Priority Tasks

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| EX-020 | 🟠 High | On-Page | Small | Rewrite homepage title tag (50–60 chars, keyword-first) | Current title "Example Domain" is 14 chars with zero keyword signal | |
| EX-021 | 🟠 High | Technical | Small | Update page charset from windows-1252 to UTF-8 | Outdated encoding — can break special characters and international content | |
| EX-022 | 🟠 High | On-Page | Small | Add internal navigation links to homepage | Zero internal links = no PageRank distribution, flat crawl depth | |
| EX-030 | 🟠 High | Content | Large | Expand homepage content from 19 words to 500+ words | Thin content is penalised by Google's Helpful Content Update | |
| EX-031 | 🟠 High | Content | Small | Research and define target keywords for homepage | Can't write keyword-optimised copy without keyword targets | EX-030 |
| EX-032 | 🟠 High | Content | Large | Write expanded homepage body copy (500+ words) | 19 words provides no topical signal for indexing | EX-030 |
| EX-033 | 🟠 High | Content | Small | Write 3–5 keyword-rich H2 subheadings for homepage | Zero H2s means flat heading structure — no content hierarchy | EX-030 |
| EX-034 | 🟠 High | Content | Small | Write H3 subheadings under each H2 for homepage | Supports scannability and long-tail keyword coverage | EX-030 |
| EX-040 | 🟠 High | Technical | Medium | Implement structured data (JSON-LD) on homepage | Missing schema = ineligible for all rich results | |
| EX-041 | 🟠 High | Technical | Small | Implement Organization JSON-LD schema on homepage | Signals entity identity to Google Knowledge Graph | EX-040 |
| EX-042 | 🟠 High | Technical | Small | Implement WebPage JSON-LD schema on homepage | Helps Google understand page type and content | EX-040 |

---

## 🟡 Medium Priority Tasks

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| EX-050 | 🟡 Medium | On-Page | Small | Add explicit `<meta name="robots" content="index, follow">` tag | Currently relying on implicit crawler defaults — explicit is safer | |
| EX-060 | 🟡 Medium | Content | Medium | Add visual content (images) to homepage | Zero images = no image search traffic, lower engagement | |
| EX-061 | 🟡 Medium | Content | Medium | Source or create hero image for homepage | Foundation for all visual content additions | EX-060 |
| EX-062 | 🟡 Medium | Content | Small | Add hero image to homepage with descriptive alt text | Alt text = accessibility + image SEO signal | EX-060 |
| EX-070 | 🟡 Medium | On-Page | Small | Add 2–3 relevant authority external links to homepage | Single outbound link to iana.org sends no topical authority signal | |

---

## ✅ Passing (No Action Required)

| Signal | Status | Notes |
|--------|--------|-------|
| HTTPS | ✅ Active | Secure, no redirect issues observed |
| Page Load Time | ✅ 84ms | Excellent — no action needed |
| TTFB | ✅ 17ms | Excellent — server responds fast |
| H1 Tag | ✅ 1 present | Meets minimum requirement (content needs work) |
| Language Attribute | ✅ `lang="en"` | Correctly set on `<html>` |
| Viewport Meta | ✅ Set correctly | Mobile-responsive viewport configured |
| Mobile-Friendly | ✅ Yes | Responsive layout confirmed |

---

## Execution Order (Dependencies)

1. **Start with:** EX-031 (keyword research) — unblocks EX-032, EX-033, EX-034
2. **Then:** EX-020 (title tag) — requires keyword targets
3. **Then:** EX-001 (meta description) — requires keyword targets
4. **Parallel:** EX-002, EX-003, EX-004, EX-005, EX-006, EX-021, EX-022 (independent technical fixes)
5. **Then:** EX-013 (OG image) → EX-014 (og:image + og:url)
6. **Then:** EX-011, EX-012 (remaining OG tags)
7. **After content is written:** EX-040 parent → EX-041, EX-042 (schema)
8. **Last:** EX-060 parent → EX-061, EX-062 (images), EX-070 (external links)
