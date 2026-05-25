# Comparison Page Playbook

Complete playbook for creating "[X] vs [Y]" comparison pages at scale.

## When to Use This Playbook

Use when targeting comparison/intent keywords:
- "[Product A] vs [Product B]"
- "[Method A] vs [Method B]"
- "[Approach A] vs [Approach B]"
- "Should I get [A] or [B]"

## When NOT to Use This Playbook

- When one option is clearly superior (may seem biased)
- When there's no meaningful differentiation
- When both options are extremely niche

## Keyword Pattern Research

### Step 1: Identify Comparison Pairs

Find comparison opportunities:
- Products in same category
- Competing methodologies
- Treatment alternatives
- Software solutions

### Step 2: Assess Balance

Ideal comparisons are:
- Roughly equal market share
- Both have pros and cons
- Neither is clearly "wrong"
- Decision factors vary by user

### Step 3: Determine User Intent

Common comparison intents:
- "Which is better for [use case]?"
- "[Use case] - [A] or [B]?"
- "Is [A] worth the extra cost?"
- "[A] vs [B] for [audience]"

## Content Requirements

### Minimum for Each Page

1. **Balanced coverage**: Equal time on both options
2. **Feature comparison table**: Clear, scannable
3. **Use case analysis**: Different options for different needs
4. **Honest pros/cons**: Not overly promotional
5. **Clear recommendation**: Based on specific criteria

### Content Structure

```markdown
# [Name A] vs [Name B]

## Quick Verdict (3-5 sentences)
- Who wins for what use case
- Price comparison
- Which to choose when...
- One-liner conclusion

## Feature Comparison Table
| Feature | [Name A] | [Name B] |
|---------|---------|---------|
| Cost | $X | $Y |
| Duration | X weeks | Y weeks |
| Pain Level | Low/Medium/High | Low/Medium/High |
| Results Last | X years | Y years |
| Recovery Time | X days | Y days |
| Requires Maintenance | Yes/No | Yes/No |

## [Name A] Deep Dive (200-300 words)
### Overview
### Best For
- [Use case 1]
- [Use case 2]
- [Use case 3]

### Pros (3-5 bullets)
### Cons (2-3 bullets)

## [Name B] Deep Dive (200-300 words)
### Overview
### Best For
- [Use case 1]
- [Use case 2]
- [Use case 3]

### Pros (3-5 bullets)
### Cons (2-3 bullets)

## Pricing Breakdown
[Detailed cost comparison including]
- Initial investment
- Ongoing costs
- Insurance coverage
- Hidden fees

## Use Case Analysis
### For [Audience 1]: [Recommendation]
### For [Audience 2]: [Recommendation]
### For [Audience 3]: [Recommendation]

## FAQ: [Name A] vs [Name B]
[5-7 common questions about choosing between them]

## Conclusion: Which Should You Choose?
[Decision matrix or flowchart]
- Choose [A] if...
- choose [B] if...
- Final recommendation
```

## Balance Requirements

To avoid appearing biased:

1. **Equal word count**: A and B sections should be similar length
2. **Equal features**: Cover the same features for both
3. **Honest cons**: Both should have real downsides listed
4. **Transparent methodology**: State how comparison was derived
5. **No "winner" in title**: Avoid "X is better than Y" titles

### Bad Title Examples
- "Braces Are Better Than Invisalign"
- "Why Dental Implants Win Over Bridges"
- "The Only Guide to [A] You Need"

### Good Title Examples
- "Braces vs. Invisalign: Which Is Right for You?"
- "Dental Implants vs. Bridges: A Comprehensive Guide"
- "[A] vs [B]: Complete Comparison for [Use Case]"

## FAQ Schema for Comparison Pages

```json
{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
    {
      "@type": "Question",
      "name": "Is [A] or [B] more cost-effective?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "While [A] costs $X upfront, [B] may require $Y in ongoing maintenance..."
      }
    },
    {
      "@type": "Question",
      "name": "How long does [A] last compared to [B]?",
      "acceptedAnswer": {
        "@type": "Answer",
        "text": "[A] typically lasts X years with proper care, while [B] may need replacement after Y years..."
      }
    }
  ]
}
```

## Technical Requirements

### URL Structure
```
/[slug-a]-vs-[slug-b]
/braces-vs-invisalign/
/dental-implants-vs-dental-bridges/
```

NOT:
- `/braces/or/` (weak structure)
- `/compare-braces-invisalign/` (keyword stuffed)

### Title Tag (50-60 chars)
```
[Name A] vs [Name B]: Which is Better for [Use Case]?
```

### Meta Description (150-160 chars)
```
Compare [Name A] and [Name B] for [Use Case]. Features, pricing, pros and cons compared. Find the best choice for your needs.
```

## Internal Linking

```
/treatments/ (Hub)
    ├── /braces-vs-invisalign/
    ├── /implants-vs-bridges/
    └── /whitening-options/

/guides/ (Educational)
    ├── /braces-guide/
    └── /invisalign-guide/
```

Link structure:
- Comparison page → Individual product/service pages
- Individual pages → Relevant comparisons
- Related guides linked in "Learn More" section

## Quality Checklist

Before publishing:

- [ ] Title is balanced (no "winner" implied)
- [ ] Both options get equal coverage
- [ ] Feature table includes 5-8 key features
- [ ] Pros/cons are honest for both
- [ ] Use case recommendations are specific
- [ ] FAQ schema validates
- [ ] Internal links to individual options
- [ ] CTA leads to consultation/quote request

## Common Mistakes

1. **Obvious bias**: Always recommending one option
   - Fix: Add genuine pros for both, base recommendations on use case

2. **Missing key features**: Comparing only obvious features
   - Fix: Include hidden costs, maintenance, longevity, recovery

3. **Thin content**: 300-word page for major decision
   - Fix: Require 1000+ words for major purchase comparisons

4. **No clear CTA**: Readers don't know next step
   - Fix: Add "Schedule Consultation" or "Get Quote" prominently

5. **Outdated information**: Prices or features have changed
   - Fix: Add "Last updated" date, review annually