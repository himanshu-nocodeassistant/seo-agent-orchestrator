# Bulk Page Templates Reference

Templates and patterns for generating programmatic SEO pages in bulk.

## Location Page Template

Use for "[service] in [location]" keyword patterns.

### URL Structure
```
/[service-slug]/[location-slug]
Example: /dental-implants/austin-tx
```

### Title Pattern
```
[Service] in [City] | [Brand Name]
Example: Dental Implants in Austin, TX | Perfect Smiles
```

### Meta Description Pattern
```
Find the best [service] in [city]. [unique_value_proposition]. Serving [city] and surrounding areas. Book your consultation today!
```

### Content Structure

```markdown
# [Service] in [City]

## Why Choose Our [Service] Services in [City]?
[intro_paragraph - 150-200 words]

## Our [Service] Services in [City]
[services_list - 3-5 service offerings]

## [City] [Service] Process
[process_steps - 4-step overview]

## Areas We Serve in [City]
[primary_area + additional_areas - 5-10 locations]

## FAQ About [Service] in [City]
[faqs - 5-7 common questions]

## Ready to Get Started?
[cta_section]
```

### Schema Markup (LocalBusiness)
```json
{
  "@context": "https://schema.org",
  "@type": "LocalBusiness",
  "name": "[Business Name]",
  "areaServed": {
    "@type": "City",
    "name": "[City]"
  },
  "serviceType": "[Service]"
}
```

## Comparison Page Template

Use for "[X] vs [Y]" keyword patterns.

### URL Structure
```
/[slug-a]-vs-[slug-b]
Example: /braces-vs-invisalign
```

### Title Pattern
```
[Name A] vs [Name B]: Which is Better for [Use Case]?
```

### Meta Description Pattern
```
Compare [Name A] and [Name B] for [Use Case]. Features, pricing, pros and cons. Find the best choice for your needs.
```

### Content Structure

```markdown
# [Name A] vs [Name B]

## Quick Verdict
[2-3 sentence recommendation]

## Feature Comparison
[table with 5-8 key features]

## [Name A] Overview
[name_a_overview - 150-200 words]

### [Name A] Pros
[3-5 bullet points]

### [Name A] Cons
[2-3 bullet points]

## [Name B] Overview
[name_b_overview - 150-200 words]

### [Name B] Pros
[3-5 bullet points]

### [Name B] Cons
[2-3 bullet points]

## Pricing Comparison
[pricing_section]

## Use Case Analysis
[use_case_section - when to choose each]

## FAQ: [Name A] vs [Name B]
[5-7 common questions]

## Conclusion: Which Should You Choose?
[final_recommendation]
```

## FAQ Page Template

Use for "[topic] FAQ" keyword patterns.

### URL Structure
```
/faq/[topic-slug]
Example: /faq/teeth-whitening
```

### Title Pattern
```
[Topic] FAQ: Common Questions Answered
```

### Meta Description Pattern
```
Find answers to common questions about [topic]. Expert guidance. Everything you need to know before your visit.
```

### Content Structure

```markdown
# Frequently Asked Questions About [Topic]

## Introduction
[intro_paragraph]

## FAQ Questions
[q1 through q7 - each with question as H2 and answer paragraph]

## Still Have Questions?
[contact_cta]

## Related Topics
[3-5 links to related pages]
```

### Schema Markup (FAQPage)
```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "[Question]",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "[Answer]"
      }
    }
  ]
}
```

## Bulk CSV Format

For bulk generation, use this CSV format:

```csv
page_type,service,location,city,primary_area,additional_areas,unique_value,intro_paragraph
location,Dental Implants,Austin TX,Austin,Downtown Austin,"North Austin,South Austin,East Austin","Latest implant technology with 3D imaging","Our Austin dental implant team..."
location,Zoom Whitening,Houston TX,Houston,Medical Center,"Downtown,The Heights,Memorial","Same-day whitening available","Experience professional teeth whitening..."
```

## Bulk JSON Format

```json
[
  {
    "page_type": "location",
    "service": "Dental Implants",
    "location": "Austin TX",
    "city": "Austin",
    "unique_value": "Latest technology",
    "intro_paragraph": "..."
  },
  {
    "page_type": "comparison",
    "name_a": "Braces",
    "name_b": "Invisalign",
    "use_case": "teens"
  }
]
```

## Internal Linking Strategy

For hub-and-spoke model:
1. **Hub Page**: Category page linking to all programmatic pages
2. **Spoke Pages**: Each programmatic page links back to hub and to 2-3 related pages
3. **Cross-links**: Between related programmatic pages (e.g., nearby locations)

## Indexation Strategy

1. Include all pages in XML sitemap
2. Set `priority` based on search volume potential
3. Use `changefreq: monthly` for location pages
4. Monitor indexation rate in Google Search Console