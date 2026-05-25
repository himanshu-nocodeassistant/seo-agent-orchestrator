# SEO Task Backlog

## Audit: nocodeassistant.agency — Re-Audit #6 (Latest)
- **Audit Date:** 2026-03-06
- **Pages Audited:** /, /weweb-agency, /bubble-agency, /faq, /blog/weweb-vs-bubble, /case-studies/blomma, /case-studies/major-app, /case-studies/prepladder, /process, /about-us, robots.txt, sitemap.xml, favicon.ico
- **Sitemap URLs:** 58 (stable)
- **New tickets this session:** NCA-071 (PrepLadder meta desc), NCA-072 (/about-us title)
- **Resolved since last audit:** 0 — site last published Feb 20, 2026; zero tickets implemented

---

## 🔴 Critical Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-001 | 🔴 Critical | On-Page | Large | Replace 38 empty alt="" attributes with descriptive alt text (homepage + service pages) | 38 images have empty alt="" — accessibility failure and zero image SEO signal across all key pages | |
| NCA-001a | 🔴 Critical | On-Page | Small | Write alt text for 5 G2 star rating images | Decorative role images need aria-hidden or short descriptive alt | NCA-001 |
| NCA-001b | 🔴 Critical | On-Page | Small | Write alt text for 7 testimonial reviewer portrait images | Each reviewer photo needs a name-based alt e.g. "Yoran Bosch, CEO of Major.app" | NCA-001 |
| NCA-001c | 🔴 Critical | On-Page | Small | Write alt text for 8 client logo images | Client logos need company name alt text e.g. "Webflow logo" | NCA-001 |
| NCA-001d | 🔴 Critical | On-Page | Medium | Write alt text for remaining decorative/section images across service pages (38 total) | Navigation, hero, footer, and icon images all need alt="" or descriptive text | NCA-001 |
| NCA-002 | 🔴 Critical | Technical | Small | Remove duplicate JSON-LD Organization schema from homepage | Two identical schemas confuse Googlebot; only one should be injected — copy/paste bug in Webflow | |
| NCA-003 | 🔴 Critical | Technical | Small | Fix favicon.ico 404 — serve at /favicon.ico root path | favicon.ico returns 404 on every page load; confirmed via browser console error in every audit | |

---

## 🟠 High Priority Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-010 | 🟠 High | On-Page | Small | Rewrite homepage title tag keyword-first, brand last | "NocodeAssistant \| Internal Tools…" — brand-first wastes prime SERP real estate; keyword-first copy ready from 2026-03-03 | |
| NCA-011 | 🟠 High | On-Page | Small | Rewrite WeWeb Agency title (38 chars, keyword-first, drop "Trusted") | "Trusted WeWeb agency" = 38 chars, filler qualifier, no audience or outcome specificity | |
| NCA-012 | 🟠 High | On-Page | Small | Rewrite Bubble Agency title (39 chars, keyword-first, drop "Trusted") | Identical structural flaw to NCA-011 | |
| NCA-020 | 🟠 High | Technical | Small | Add og:url meta tag to all pages | Absent on homepage and all service pages — required for correct Open Graph canonical resolution | |
| NCA-021 | 🟠 High | Technical | Small | Add og:site_name meta tag to all pages | Absent sitewide — affects how brand name renders in LinkedIn/Facebook link previews | |
| NCA-030 | 🟠 High | Technical | Medium | Add WebPage JSON-LD schema to homepage (replacing duplicate Org) | Homepage only has (duplicate) Org schema — no page-type signal for Google | |
| NCA-031 | 🟠 High | Technical | Small | Fix JSON-LD @context from http:// to https:// on all pages | All pages use http://schema.org — outdated; https:// is the current W3C spec | |
| NCA-040 | 🟠 High | On-Page | Small | Rewrite WeWeb page H1 to be WeWeb-specific; rewrite Bubble H1 to mention Bubble | WeWeb H1 is identical to homepage; Bubble H1 says "custom" but never mentions Bubble | |
| NCA-060 | 🟠 High | Technical | Medium | Add AggregateRating JSON-LD to homepage (G2 4.8/5, 7+ reviews) | G2 rating displayed visually on homepage — zero schema; AggregateRating could unlock SERP star snippets | |
| NCA-068 | 🟠 High | On-Page | Small | Add meta descriptions to Blomma and Major App case study pages | Both pages have NO meta description — Google writes its own; high-intent conversion pages getting poor SERP snippets | |
| NCA-069 | 🟠 High | On-Page | Small | Rewrite Major App case study title (currently "Major App" — 9 chars) | 9-char title is critically thin; no brand, no keywords, no context — fails every title best practice | |
| NCA-071 | 🟠 High | On-Page | Small | Add meta description to /case-studies/prepladder (confirmed missing) | PrepLadder is a high-value enterprise case study (medical SaaS) with zero meta desc — same issue as NCA-068 | |

---

## 🟡 Medium Priority Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-050 | 🟡 Medium | Technical | Small | Add explicit `<meta name="robots" content="index, follow">` to all pages | Missing on every page — relying on implicit crawler defaults is risky | |
| NCA-051 | 🟡 Medium | Technical | Small | Fix canonical trailing slash on homepage — add trailing slash to match URL | Canonical is `https://www.nocodeassistant.agency` (no slash); page loads as `.../` (with slash) — inconsistency confirmed 2026-03-06 | |
| NCA-052 | 🟡 Medium | Technical | Small | Add lastmod, priority, and changefreq to all 58 sitemap.xml entries | Sitemap has 58 URLs with no freshness metadata — deprives Google of crawl priority signals | |
| NCA-053 | 🟡 Medium | Technical | Medium | Add FAQPage JSON-LD schema to /faq page | 11 Q&A items present but zero structured data — FAQ rich results (accordion in SERPs) currently impossible | |
| NCA-054 | 🟡 Medium | Technical | Medium | Add Service JSON-LD schema to /weweb-agency page | Service page only has Org schema — no service-type signal; ineligible for service-related rich results | |
| NCA-055 | 🟡 Medium | Technical | Medium | Add Service JSON-LD schema to /bubble-agency page | Same gap as NCA-054 | |
| NCA-061 | 🟡 Medium | Content | Large | Conduct full SEO audit of all 46 blog posts | 46 posts in sitemap untouched — likely widespread keyword and meta description gaps | |
| NCA-062 | 🟡 Medium | Technical | Medium | Add CaseStudy/Article JSON-LD to all 3 case study pages | All case studies carry only Org schema — no content-type signal; parent for 062b/062c | |
| NCA-062b | 🟡 Medium | Technical | Medium | Add Article JSON-LD to /case-studies/major-app | Same gap as NCA-062 | NCA-062 |
| NCA-062c | 🟡 Medium | Technical | Medium | Add Article JSON-LD to /case-studies/prepladder | Same gap as NCA-062 | NCA-062 |
| NCA-063 | 🟡 Medium | Technical | Large | Add BlogPosting JSON-LD schema to all 46 blog posts (template-level Webflow fix) | Zero blog posts have Article/BlogPosting schema — template fix would resolve all 46 at once | |
| NCA-065 | 🟡 Medium | On-Page | Small | Rewrite FAQ page title — "FAQ \| NocodeAssistant" (21 chars) is too generic | 21 chars, zero keyword targeting; rewrite to "No-Code Development FAQs \| NocodeAssistant" (~45 chars) | |
| NCA-070 | 🟡 Medium | On-Page | Small | Rewrite FAQ page H1 from "FAQ" to keyword-focused heading | Single word H1 has zero SEO value; rewrite to "No-Code Development FAQs" or similar | |

---

## 🟢 Low Priority Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-064 | 🟢 Low | On-Page | Medium | Audit and fix truncated blog meta descriptions across all 46 posts | weweb-vs-bubble description ends mid-sentence ("…pricing, and vendor") — Webflow CMS field limit likely affecting multiple posts | |
| NCA-066 | 🟢 Low | On-Page | Small | Expand WeWeb and Bubble page meta descriptions (both under 85 chars) | WeWeb: 80 chars, Bubble: 81 chars — below 120-char optimal floor; missing audience-specific keywords | |
| NCA-067 | 🟢 Low | Technical | Small | Add trailing slash to homepage URL in sitemap.xml | Sitemap has `https://www.nocodeassistant.agency` (no slash); canonical uses slash — minor crawler inconsistency | |
| NCA-072 | 🟢 Low | On-Page | Small | Rewrite /about-us title — "About Us \| NocodeAssistant" (28 chars) has no keyword value | 28 chars, no keyword signal; rewrite to "No-Code Agency for SMBs \| NocodeAssistant" (~43 chars) | |

---

## ✅ Resolved — nocodeassistant.agency

| ID | Title | Resolved |
|----|-------|---------|
| NCA-022 | Twitter meta tags now fully present (title, description, image) | 2026-03-04 |
| NCA-051 | ~~Canonical trailing slash~~ — REOPENED 2026-03-06 (was false positive) | — |

---

## ✅ Passing — nocodeassistant.agency (Audit #6, 2026-03-06)

| Signal | Status | Notes |
|--------|--------|-------|
| HTTPS | ✅ Active | Secure, no redirect issues |
| Charset | ✅ UTF-8 | Correct |
| lang="en" | ✅ Present | Correctly set |
| Viewport meta | ✅ Set | Mobile-responsive |
| Meta description (homepage) | ✅ 148 chars | Present and above optimal floor |
| OG title + description + image | ✅ Present | All three set |
| Twitter card | ✅ Full | card, title, description, image all set (NCA-022 resolved) |
| robots.txt | ✅ Valid | User-agent: * Allow: / Sitemap: referenced |
| Sitemap | ✅ 58 URLs | Stable |
| Favicon CDN link | ✅ In `<head>` | PNG via CDN works; root /favicon.ico is separate (NCA-003) |
| H1 per page | ✅ 1 per page | All pages have exactly one H1 |
| Homepage content depth | ✅ 860 words | Healthy word count |
| Internal links | ✅ 16+ (homepage) | Good |
| Load speed | ✅ Fast | TTFB ~77ms |
| Blog volume | ✅ 46 posts | Strong content asset (needs audit — NCA-061) |

---

## Execution Order — nocodeassistant.agency Quick Wins

### Phase 1: Zero-Dev Fixes (<1 day each, all in Webflow)
1. **NCA-002** — Remove duplicate JSON-LD (~15 min, CMS fix)
2. **NCA-003** — Upload favicon.ico to Webflow hosting root (~15 min)
3. **NCA-031** — Change `http://schema.org` → `https://schema.org` (single string replacement)
4. **NCA-020 + NCA-021** — Add og:url and og:site_name to Webflow header (2 meta tags)
5. **NCA-050** — Add robots meta tag globally in Webflow header (1 tag)
6. **NCA-067** — Fix sitemap homepage URL trailing slash in Webflow settings
7. **NCA-051** — Fix canonical trailing slash in Webflow settings

### Phase 2: Copy + Title Rewrites (content work, no dev)
8. **NCA-010 / NCA-011 / NCA-012** — 3 title tag rewrites (copy already drafted 2026-03-03)
9. **NCA-040** — Rewrite WeWeb H1 + Bubble H1
10. **NCA-065** — Rewrite FAQ page title
11. **NCA-070** — Rewrite FAQ H1
12. **NCA-068 + NCA-071** — Add meta descriptions to all 3 case studies
13. **NCA-069** — Rewrite Major App title (9 chars → 50+ chars)
14. **NCA-066** — Expand WeWeb + Bubble meta descriptions
15. **NCA-072** — Rewrite /about-us title

### Phase 3: Schema + Structured Data
16. **NCA-060** — AggregateRating JSON-LD (high reward — SERP stars)
17. **NCA-030** — WebPage JSON-LD on homepage
18. **NCA-053** — FAQPage JSON-LD on /faq
19. **NCA-054 + NCA-055** — Service JSON-LD on WeWeb + Bubble pages
20. **NCA-062 / 062b / 062c** — CaseStudy JSON-LD on all 3 case studies

### Phase 4: Alt Text (batch by image group)
21. **NCA-001a** — 5 G2 star rating images
22. **NCA-001b** — 7 testimonial portrait images
23. **NCA-001c** — 8 client logo images
24. **NCA-001d** — Remaining 18 decorative/section images

### Phase 5: Large Scale / Template Fixes
25. **NCA-063** — BlogPosting JSON-LD for all 46 posts (Webflow template-level fix)
26. **NCA-052** — Sitemap lastmod/priority metadata
27. **NCA-061** — Full blog SEO audit (46 posts)
28. **NCA-064** — Audit + fix truncated blog meta descriptions

---

## Audit: example.com (Practice)
- **Audit Date:** 2026-03-03
- **Pages Audited:** https://example.com (homepage)
- **Total Tasks:** 24 (11 simple, 4 parent tasks with 13 subtasks)

---

## 🔴 Critical Tasks — example.com

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| EX-001 | 🔴 Critical | On-Page | Small | Write and add meta description to homepage | Missing entirely — direct CTR loss in SERPs | |
| EX-002 | 🔴 Critical | Technical | Small | Create /robots.txt file | Currently 404 — crawlers have no direction | |
| EX-003 | 🔴 Critical | Technical | Small | Generate and submit XML sitemap at /sitemap.xml | Missing 404 — Google must discover pages on its own | |
| EX-004 | 🔴 Critical | Technical | Small | Add canonical tag to homepage | No canonical = duplicate content risk | |
| EX-005 | 🔴 Critical | Technical | Small | Add twitter:card meta tag to homepage | Twitter previews render blank without it | |
| EX-006 | 🔴 Critical | Technical | Small | Create and serve favicon.ico at /favicon.ico | Currently 404 — console error on every page load | |
| EX-010 | 🔴 Critical | On-Page | Medium | Add all Open Graph tags to homepage | Social shares look broken | |
| EX-011 | 🔴 Critical | On-Page | Small | Add og:title to homepage | Required for Facebook/LinkedIn previews | EX-010 |
| EX-012 | 🔴 Critical | On-Page | Small | Add og:description to homepage | Controls social snippet text | EX-010 |
| EX-013 | 🔴 Critical | On-Page | Medium | Source/design OG image (1200×630px) for homepage | og:image is most clicked in social previews | EX-010 |
| EX-014 | 🔴 Critical | On-Page | Small | Add og:image and og:url to homepage | Completes Open Graph implementation | EX-010 |

---

## 🟠 High Priority Tasks — example.com

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| EX-020 | 🟠 High | On-Page | Small | Rewrite homepage title tag (50–60 chars, keyword-first) | "Example Domain" is 14 chars with zero keyword signal | |
| EX-021 | 🟠 High | Technical | Small | Update page charset from windows-1252 to UTF-8 | Outdated encoding — can break special characters | |
| EX-022 | 🟠 High | On-Page | Small | Add internal navigation links to homepage | Zero internal links = no PageRank distribution | |
| EX-030 | 🟠 High | Content | Large | Expand homepage content from 19 words to 500+ words | Thin content penalised by Google's Helpful Content Update | |
| EX-031 | 🟠 High | Content | Small | Research and define target keywords for homepage | Can't write keyword-optimised copy without keyword targets | EX-030 |
| EX-032 | 🟠 High | Content | Large | Write expanded homepage body copy (500+ words) | 19 words provides no topical signal | EX-030 |
| EX-033 | 🟠 High | Content | Small | Write 3–5 keyword-rich H2 subheadings for homepage | Zero H2s — flat heading structure | EX-030 |
| EX-034 | 🟠 High | Content | Small | Write H3 subheadings under each H2 | Supports scannability and long-tail coverage | EX-030 |
| EX-040 | 🟠 High | Technical | Medium | Implement structured data (JSON-LD) on homepage | No schema = ineligible for all rich results | |
| EX-041 | 🟠 High | Technical | Small | Implement Organization JSON-LD schema | Signals entity identity to Knowledge Graph | EX-040 |
| EX-042 | 🟠 High | Technical | Small | Implement WebPage JSON-LD schema | Helps Google understand page type | EX-040 |

---

## 🟡 Medium Priority Tasks — example.com

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| EX-050 | 🟡 Medium | On-Page | Small | Add explicit robots meta tag (index, follow) | Relying on implicit crawler defaults | |
| EX-060 | 🟡 Medium | Content | Medium | Add visual content (images) to homepage | Zero images = no image search traffic | |
| EX-061 | 🟡 Medium | Content | Medium | Source or create hero image for homepage | Foundation for visual content additions | EX-060 |
| EX-062 | 🟡 Medium | Content | Small | Add hero image with descriptive alt text | Alt text = accessibility + image SEO signal | EX-060 |
| EX-070 | 🟡 Medium | On-Page | Small | Add 2–3 relevant authority external links | Single outbound link sends no topical authority signal | |
