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

---

---

## Audit: nocodeassistant.agency — Re-Audit #2
- **Audit Date:** 2026-03-04
- **Pages Audited:** Homepage, /weweb-agency, /bubble-agency, /faq, /blog/weweb-vs-bubble, robots.txt, sitemap.xml
- **Sitemap URLs:** 57 (was 56 — 1 new blog post added)
- **Resolved since last audit:** NCA-051 (canonical trailing slash)
- **New tickets this session:** NCA-063, NCA-064

---

## 🔴 Critical Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-001 | 🔴 Critical | On-Page | Large | Add alt text to 37 images on homepage | 37/40 images have no alt attribute — accessibility failure + zero image SEO signal | |
| NCA-001a | 🔴 Critical | On-Page | Medium | Write alt text for 5 G2 star rating images on homepage | Decorative role images need aria-hidden or descriptive alt | NCA-001 |
| NCA-001b | 🔴 Critical | On-Page | Medium | Write alt text for 7 testimonial reviewer portrait images | Each reviewer photo needs a name-based alt e.g. "Yoran Bosch, CEO of Major.app" | NCA-001 |
| NCA-001c | 🔴 Critical | On-Page | Medium | Write alt text for 8 client logo images in client list section | Client logos need company name alt text | NCA-001 |
| NCA-001d | 🔴 Critical | On-Page | Medium | Write alt text for remaining 17 decorative/section images | Navigation, footer, and icon images need alt="" or descriptive text | NCA-001 |
| NCA-002 | 🔴 Critical | Technical | Small | Remove duplicate JSON-LD Organization schema from homepage | Two identical schemas confuse Googlebot; only one should be injected | |
| NCA-003 | 🔴 Critical | Technical | Small | Serve favicon.ico at /favicon.ico root path | favicon.ico still returns 404 — confirmed via browser console error on every page load | |

---

## 🟠 High Priority Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-010 | 🟠 High | On-Page | Small | Rewrite homepage title tag keyword-first (brand last) | "NocodeAssistant \| Internal Tools…" — brand name first wastes prime SERP real estate | |
| NCA-011 | 🟠 High | On-Page | Small | Rewrite WeWeb Agency page title (keyword-first, drop "Trusted") | "Trusted WeWeb agency" — 38 chars, filler qualifier, no audience specificity | |
| NCA-012 | 🟠 High | On-Page | Small | Rewrite Bubble Agency page title (keyword-first, drop "Trusted") | "Trusted Bubble agency" — 39 chars, identical pattern flaw as NCA-011 | |
| NCA-020 | 🟠 High | Technical | Small | Add og:url meta tag to homepage | og:url absent on all pages — required for correct Open Graph crawling | |
| NCA-021 | 🟠 High | Technical | Small | Add og:site_name meta tag to homepage | og:site_name absent — affects how brand name renders in social link previews | |
| NCA-030 | 🟠 High | Technical | Medium | Add WebPage JSON-LD schema to homepage | Homepage has only (duplicate) Org schema — no page-level schema for Google | |
| NCA-031 | 🟠 High | Technical | Small | Update JSON-LD @context from http:// to https:// on all pages | All pages use http://schema.org — outdated; https:// is the current spec | |
| NCA-040 | 🟠 High | On-Page | Small | Rewrite WeWeb Agency page H1 to be WeWeb-specific | H1 is identical to homepage ("We build Internal Tools & SaaS…") — missed differentiation | |
| NCA-060 | 🟠 High | Technical | Medium | Add AggregateRating JSON-LD to homepage | G2 4.8/5 rating displayed visually but has zero schema — could unlock SERP star snippets | |

---

## 🟡 Medium Priority Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-050 | 🟡 Medium | Technical | Small | Add `<meta name="robots" content="index, follow">` to all pages | Missing explicit robots directive — relying on crawler defaults | |
| NCA-052 | 🟡 Medium | Technical | Small | Add lastmod, priority, and changefreq to all sitemap.xml entries | Sitemap has 57 URLs with no metadata — deprives Google of crawl freshness signals | |
| NCA-053 | 🟡 Medium | Technical | Medium | Add FAQPage JSON-LD schema to /faq page | 11 Q&A items present but zero structured data — FAQ rich results currently impossible | |
| NCA-054 | 🟡 Medium | Technical | Medium | Add Service JSON-LD schema to /weweb-agency page | Service pages have only Org schema — no service-level structured data | |
| NCA-055 | 🟡 Medium | Technical | Medium | Add Service JSON-LD schema to /bubble-agency page | Same as NCA-054 — Bubble service page also lacks Service schema | |
| NCA-061 | 🟡 Medium | Content | Large | Conduct full SEO audit of all 46 blog posts | 46 posts confirmed in sitemap — no individual page audit done; likely keyword and meta gaps | |
| NCA-062 | 🟡 Medium | Technical | Medium | Add Article or CaseStudy JSON-LD to /case-studies/blomma | Case study pages have no schema — missing structured data for rich results | |
| NCA-062b | 🟡 Medium | Technical | Medium | Add Article or CaseStudy JSON-LD to /case-studies/major-app | Same schema gap as NCA-062 | |
| NCA-062c | 🟡 Medium | Technical | Medium | Add Article or CaseStudy JSON-LD to /case-studies/prepladder | Same schema gap as NCA-062 | |
| NCA-063 | 🟡 Medium | Technical | Large | Add BlogPosting JSON-LD schema to all 46 blog posts | All blog posts carry only Org schema — no Article/BlogPosting type; ineligible for article rich results | |

---

## 🟢 Low Priority Tasks — nocodeassistant.agency

| ID | Priority | Category | Effort | Task | Why | Parent |
|----|----------|----------|--------|------|-----|--------|
| NCA-064 | 🟢 Low | On-Page | Medium | Audit and fix truncated blog meta descriptions | weweb-vs-bubble description ends mid-sentence ("…pricing, and vendor") — poor SERP snippet quality | |

---

## ✅ Resolved — nocodeassistant.agency

| ID | Title | Resolved |
|----|-------|---------|
| NCA-022 | Twitter meta tags now fully present (title, description, image) | 2026-03-04 |
| NCA-051 | Canonical trailing slash now matches URL (both use trailing slash) | 2026-03-04 |

---

## ✅ Passing — nocodeassistant.agency (Re-Audit #2, 2026-03-04)

| Signal | Status | Notes |
|--------|--------|-------|
| HTTPS | ✅ Active | Secure |
| Charset | ✅ UTF-8 | Correct |
| lang="en" | ✅ Present | Correctly set |
| Viewport meta | ✅ Set | Mobile-responsive |
| Meta description | ✅ Present | 144 chars on homepage |
| Canonical tag | ✅ Present | Now consistent with trailing slash |
| robots.txt | ✅ Valid | User-agent: * Allow: / Sitemap: referenced |
| Sitemap | ✅ 57 URLs | Stable, growing |
| OG title + description + image | ✅ Present | All three set |
| Twitter card | ✅ Full | card, title, description, image all set |
| Favicon CDN link | ✅ In `<head>` | PNG via CDN works; root /favicon.ico is separate issue |
| H1 | ✅ 1 per page | Correct |
| Content depth | ✅ 860 words (homepage) | Healthy word count |
| Internal links | ✅ 16 (homepage) | Good internal linking |
| Load speed | ✅ Fast | TTFB ~77ms |
| Bubble H1 | ✅ Differentiated | "We build **custom** Internal Tools…" — minor but different |

---

## Execution Order — nocodeassistant.agency Quick Wins

1. **NCA-002** — Remove duplicate JSON-LD (CMS copy/paste fix, ~15 min)
2. **NCA-003** — Serve favicon.ico at root path (~15 min in Webflow hosting)
3. **NCA-031** — Fix @context to https:// (single string change in CMS)
4. **NCA-020 + NCA-021** — Add og:url and og:site_name (2 tag additions)
5. **NCA-050** — Add robots meta tag (1 tag addition, site-wide)
6. **NCA-060** — AggregateRating JSON-LD (high reward, ~1 hour)
7. **NCA-010 / 011 / 012** — Rewrite 3 title tags (copy is ready from 2026-03-03 session)
8. **NCA-040** — Rewrite WeWeb H1
9. **NCA-001a–d** — Alt text in batches by image group
10. **NCA-053 / 054 / 055** — Schema additions for FAQ and service pages
11. **NCA-062 / 062b / 062c** — Case study schema
12. **NCA-063** — BlogPosting schema (large, template-level fix in Webflow)
