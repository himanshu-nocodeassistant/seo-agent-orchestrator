---
name: webflow-cms
description: Use when the user wants to manage Webflow CMS content - create, edit, update, or publish blog posts, pages, or CMS items. Also use when user mentions "publish to Webflow," "update blog," "create new post," "edit meta tags," "update SEO," "Webflow integration," "sync content," or needs to manage website content, titles, descriptions, or publish workflows.
---

# Webflow CMS Management

You are an expert in managing Webflow CMS content. Your goal is to help create, update, and publish CMS items efficiently.

## When to Use This Skill

Use this skill when the user wants to:

### Content Creation
- "Create a new blog post"
- "Add a new page to Webflow"
- "Publish new content"
- "Write a post about [topic]"

### Content Updates
- "Update the title of [page]"
- "Change the meta description"
- "Edit the blog post"
- "Update SEO settings"
- "Fix the slug"

### Publishing
- "Publish to live site"
- "Make changes go live"
- "Deploy the post"

### Content Management
- "List all posts"
- "Get collection info"
- "Find a specific post"
- "Check what content we have"

---

## Available Webflow Tools

These read tools are available to agents when Webflow is configured:

| Tool | Purpose |
|------|---------|
| `mcp__webflow__list_cms_items` | List items in collection (supports pagination) |
| `mcp__webflow__get_cms_item` | Get a single item by ID |
| `mcp__webflow__get_collection_info` | Get collection schema |

---

## Approval model

Agents must not call Webflow write tools. For every create, update, or publish action:

1. Read the current item or collection.
2. Prepare the complete payload and current snapshot.
3. Return this JSON block:

```json
{"webflow_proposal":{"operation":"update|create|publish","resource_id":"id or null","snapshot":{},"payload":{}}}
```

4. Wait for approval in Kanban or through the API.

The server checks the snapshot again, then applies the exact payload. A changed item
becomes stale and needs a new proposal.

---

## Common Workflows

### 1. Create a New Blog Post

```python
# Return these fields inside the proposal payload:
{
    "name": "Post Title",
    "slug": "post-title-slug",
    "content": "Full content here...",
    "seo-title": "SEO Title (50-60 chars)",
    "seo-desc": "Meta description (150-160 chars)",
    "excerpt": "Short summary",
    "featured": false,
    "display-date": "2026-03-03T00:00:00.000Z"
}
```

**Best Practices:**
- `slug`: Use kebab-case, include target keyword
- `seo-title`: 50-60 characters, include primary keyword
- `seo-desc`: 150-160 characters, compelling CTA
- `excerpt`: 1-2 sentence summary for cards/lists

### 2. Update SEO Meta Tags

Use the item ID and current snapshot in a proposal:
```python
{
    "item_id": "69a1671821da0058e48b43b1",
    "name": "Updated Title",
    "slug": "updated-slug",
    "seo-title": "New SEO Title",
    "seo-desc": "New meta description"
}
```

**When to update:**
- After SEO audit recommendations
- When targeting new keywords
- Refreshed content
- New meta suggestions

### 3. List and Find Content

```python
# List all items (use limit/offset for pagination)
list_cms_items(limit=100, offset=0)

# Get specific item by ID
get_cms_item(item_id="69a1671821da0058e48b43b1")
```

**Pagination:** Webflow API returns max 100 items. Use offset to paginate:
- First 100: offset=0
- Next 100: offset=100
- And so on...

### 4. Publish to Live Site

```python
# Publish a single item through an approved proposal
{"operation":"publish","resource_id":"69a1671821da0058e48b43b1","snapshot":{},"payload":{}}
```

**Workflow:**
1. Return the complete create or update proposal.
2. Review the preview.
3. Approve the proposal to apply it.
4. Return a separate publish proposal when it should go live.

---

## Field Reference

Based on the connected Webflow collection:

| Field | Type | Purpose |
|-------|------|---------|
| `name` | Text | Post title/headline |
| `slug` | Text | URL slug (kebab-case) |
| `content` | Rich Text | Main body content |
| `excerpt` | Text | Short summary for cards |
| `seo-title` | Text | Meta title (50-60 chars) |
| `seo-desc` | Text | Meta description (150-160 chars) |
| `featured` | Boolean | Featured post flag |
| `display-date` | Date | Publication date to show |
| `show-table-of-contents` | Boolean | Enable TOC |
| `isDraft` | Boolean | Draft status (system) |
| `isArchived` | Boolean | Archive status (system) |

---

## SEO Best Practices

### Title Tags
- 50-60 characters max
- Primary keyword near beginning
- Compelling, click-worthy
- Format: "Primary Keyword | Brand" or "How to [topic]"

### Meta Descriptions
- 150-160 characters
- Include primary keyword
- Clear value proposition
- Call to action

### URL Slugs
- Kebab-case: `/my-post-title/`
- Include target keyword
- Keep it short
- No stop words needed

### Content Structure
- Use headings (H2, H3)
- Include target keyword in first 100 words
- Add related keywords naturally
- Structure for featured snippets when possible

---

## Common Errors and Solutions

### "Unknown Error Occurred"
- Check Webflow API token is valid
- Ensure env vars are set: `WEBFLOW_ACCESS_TOKEN`, `WEBFLOW_SITE_ID`, `WEBFLOW_COLLECTION_ID`
- Token may need refresh in Webflow dashboard

### "Item not found"
- Verify item ID is correct
- Item may have been deleted

### "Publishing failed"
- Item must exist first (create or get)
- Check if item is already published

### "Pagination not working"
- Webflow max is 100 per request
- Loop with offset += 100 for more items

---

## Configuration

Webflow is auto-configured via environment variables:

```bash
WEBFLOW_ACCESS_TOKEN=your_token
WEBFLOW_SITE_ID=your_site_id
WEBFLOW_COLLECTION_ID=your_collection_id
```

Configuration exposes read tools to agents. It does not grant agents permission to
write. Webflow mutations use the approval API.

Or programmatically:
```python
from agent import AgentConfig, WebflowConfig

config = AgentConfig(
    webflow_config=WebflowConfig(
        access_token="token",
        site_id="site_id",
        collection_id="collection_id"
    )
)
```

---

## Related Skills

- **seo-audit**: Before updating content, run an audit to identify what needs improvement
- **copywriting**: For writing new content to publish
- **schema-markup**: Add structured data after publishing
- **content-strategy**: Plan content calendar and topics
