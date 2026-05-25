# Location Page Playbook

Complete playbook for creating "[service] in [location]" pages at scale.

## When to Use This Playbook

Use when targeting geo-modified service keywords:
- "dentist in [city]"
- "[service] near me"
- "[service] [city] [state]"
- "[service] [zip code]"

## Keyword Pattern Research

### Step 1: Identify Location Clusters

Group locations by:
- **Primary cities**: High population, high search volume
- **Suburbs**: Lower competition, local intent
- **Service areas**: Neighborhoods that fall under service radius

### Step 2: Validate Search Demand

For each location, check:
- Keyword Planner for exact match volume
- "Near me" variant trends
- "Best of" variations

### Step 3: Determine Page Priority

| Priority | Criteria | Action |
|----------|----------|--------|
| High | Volume > 100/mo, low competition | Full unique content |
| Medium | Volume 30-100/mo | Template with local customization |
| Low | Volume < 30/mo | Consider noindex or redirect |

## Content Requirements

### Minimum for Each Page

1. **Unique H1**: Must include service + location
2. **Unique Intro**: 150-200 words, not template-swapped
3. **Local Signals**: Address, phone, hours, landmarks
4. **Schema Markup**: LocalBusiness or Service
5. **Internal Links**: Hub page + 2-3 related locations

### Content Sections (Required)

```markdown
# [Service] in [City] [State]

## Why Choose Our [Service] Services in [City]?
- 150-200 word unique intro paragraph
- Local signals: neighborhood names, landmarks
- Trust builders: certifications, years in business
- Call to action

## Our [Service] Services in [City]
- 3-5 specific service offerings
- Each with brief 2-3 sentence description
- Include local-specific details where relevant

## [City] [Service] Process
- 4-step numbered process
- Local-specific elements (city name in steps)
- Realistic timeline

## Areas We Serve in [City]
- Primary service area (the city itself)
- 5-10 nearby neighborhoods/suburbs
- Drive times if impressive

## FAQ About [Service] in [City]
- 5-7 questions about this specific location
- "How far do you travel?"
- "Do you serve [nearby city] too?"
- "What neighborhoods do you cover?"

## Contact CTA
- Address with embedded Google Maps
- Phone number
- Hours of operation
- "Book Now" button
```

### Content Sections (Optional)

- **Service-specific galleries**: Real photos of local work
- **Local testimonials**: Customer reviews mentioning location
- **Team bios**: Staff with local credentials/tenure
- **Community involvement**: Local partnerships, sponsorships

## LocalBusiness Schema Markup

```json
{
  "@context": "https://schema.org",
  "@type": "Dentist",
  "name": "Perfect Smiles - Austin",
  "description": "Leading provider of dental implants in Austin...",
  "address": {
    "@type": "PostalAddress",
    "streetAddress": "123 Main St",
    "addressLocality": "Austin",
    "addressRegion": "TX",
    "postalCode": "78701",
    "addressCountry": "US"
  },
  "geo": {
    "@type": "GeoCoordinates",
    "latitude": "30.2672",
    "longitude": "-97.7431"
  },
  "telephone": "+1-512-555-0100",
  "openingHours": "Mo-Fr 08:00-18:00",
  "areaServed": {
    "@type": "City",
    "name": "Austin"
  },
  "priceRange": "$$"
}
```

## Technical Requirements

### URL Structure
```
/service-category/city-state/
/dental-implants/austin-tx/
```

NOT:
- `/location-pages/austin-tx-dental-implants/` (keyword cannibalization)
- `/austin/dental-implants/` (weak structure)

### Title Tag (50-60 chars)
```
[Service] in [City], [State] | [Brand Name]
```

### Meta Description (150-160 chars)
```
Find the best [service] in [city]. [USP]. Serving [city] and nearby [neighborhoods]. Book your consultation today!
```

### H1 Tag
```
[Service] in [City] [State Abbreviation]
```

## Internal Linking Architecture

```
/services/ (Hub)
    ├── /dental-implants/
    │   ├── /dental-implants/austin-tx/
    │   ├── /dental-implants/houston-tx/
    │   ├── /dental-implants/dallas-tx/
    │   └── ...
    ├── /invisalign/
    │   ├── /invisalign/austin-tx/
    │   └── ...
    └── ...
```

Each location page links to:
- Parent category page
- 2-3 geographically related pages
- Related service pages

## Quality Checklist

Before publishing each page:

- [ ] H1 includes service + location
- [ ] Intro paragraph is unique (not just variables swapped)
- [ ] Address and contact info present
- [ ] LocalBusiness schema validates
- [ ] Links to hub page
- [ ] Links to 2+ related location pages
- [ ] Image with optimized alt text (location-relevant)
- [ ] Mobile-friendly layout
- [ ] Page speed < 3 seconds

## Common Mistakes

1. **Thin content**: Just swapping city names
   - Fix: Require unique intro paragraph for each page

2. **Keyword cannibalization**: Multiple pages for same keyword
   - Fix: Use canonical tags, consolidate similar locations

3. **Duplicate content**: Identical structure, swapped variables
   - Fix: Add unique value prop, local testimonials, specific details

4. **Orphan pages**: No internal links
   - Fix: Always include hub + related location links

5. **No local signals**: Generic content
   - Fix: Include address, phone, neighborhood names, landmarks