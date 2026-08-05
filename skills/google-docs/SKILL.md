---
name: google-docs
description: Use when the user wants to save SEO audit reports, blog content, or any documents to Google Docs. Also use when user mentions "save to Google Docs," "create a doc," "export to doc," "write to document," "add to Google Docs," "generate report in docs," or needs to create, read, or append content to Google Docs. ALWAYS create a Google Doc when generating SEO audit reports, blog posts, content strategy documents, or any substantial SEO output.
---

# Google Docs Management

You are an expert in managing Google Docs for SEO content. Your goal is to help create, read, and append content to Google Docs efficiently.

## 🚨 MANDATORY: Always Create Google Docs for SEO Output

**IMPORTANT:** When you generate any of the following, you MUST create a Google Doc:
- SEO audit reports
- Blog posts or articles
- Content strategy documents
- Competitor analysis reports
- Keyword research
- Any substantial SEO content

**Never** just display the content in chat. Always save it to Google Docs so it's:
- Persisted and shareable
- Editable by the client
- Professional looking
- Accessible after the session ends

## When to Use This Skill

Use this skill when:

### SEO Outputs (ALWAYS do this)
- Running an SEO audit → Save report to Google Docs
- Writing a blog post → Create Google Doc
- Creating content strategy → Save to Google Docs
- Competitor analysis → Save to Google Docs
- Any substantial content → Save to Google Docs

### User Requests
- "Save this audit to Google Docs"
- "Create a new doc for the blog post"
- "Export the report to Google Docs"
- "Make a document for this content"
- "Write to a Google Doc"

### Content Appending
- "Add this to the existing doc"
- "Append the audit findings"
- "Add more content to the doc"
- "Continue writing in the document"

### Document Reading
- "Read the document"
- "Show me what's in the doc"
- "Get the content from Google Docs"

---

## Available Google Docs Tools

These tools are automatically available when Google Docs is configured:

| Tool | Purpose |
|------|---------|
| `mcp__google_docs__create_google_doc` | Create a new Google Doc |
| `mcp__google_docs__get_google_doc` | Get document content by ID |
| `mcp__google_docs__append_to_google_doc` | Append content to existing doc |
| `mcp__google_docs__update_google_doc_title` | Update document title |

---

## 🔒 Important - No Delete Capability

**By design, Google Docs cannot be deleted through this integration.**

The agent can only:
- ✅ Create new documents
- ✅ Read documents  
- ✅ Append content to documents
- ✅ Update document titles
- ❌ Delete documents (intentionally disabled)

This ensures audit reports and blog content are preserved and cannot be accidentally removed.

---

## Common Workflows

### 1. Create a New SEO Audit Report

```python
# Use create_google_doc tool with title and content:
{
    "title": "SEO Audit Report - [Website Name] - [Date]",
    "content": "# SEO Audit Report\n\nWebsite: [URL]\nDate: [Date]\n\n## Executive Summary\n\n[Summary here]\n\n## Technical SEO\n\n[Technical findings]\n\n## Content Analysis\n\n[Content recommendations]\n\n## Next Steps\n\n[Action items]"
}
```

**Best Practices:**
- Title: Include website name and date for easy reference
- Content: Use markdown formatting for structure
- Include sections: Executive Summary, Technical SEO, Content, Next Steps

### 2. Create Blog Post Document

```python
# Create a document for a blog post:
{
    "title": "Blog Post: [Topic] - [Date]",
    "content": "# [Blog Post Title]\n\n## Introduction\n\n[Hook and introduction]\n\n## Main Content\n\n### Section 1\n\n[Content]\n\n### Section 2\n\n[Content]\n\n## Conclusion\n\n[Summary and CTA]"
}
```

### 3. Append Content to Existing Document

```python
# Use append_to_google_doc with document ID and content:
{
    "document_id": "[DOCUMENT_ID_FROM_CREATE]",
    "text": "\n\n## Additional Findings\n\n[New content to append]\n\n---\nUpdated: [Date]"
}
```

**When to append:**
- Adding follow-up audit results
- Updating with new recommendations
- Continuing a draft document
- Adding research findings

### 4. Get Document Content

```python
# Use get_google_doc to retrieve content:
{
    "document_id": "[DOCUMENT_ID]"
}
```

---

## Document ID Management

When you create a document, you'll receive a `documentId` in the response:

```json
{
  "documentId": "1a2b3c4d5e6f7g8h9i0",
  "title": "SEO Audit Report"
}
```

**Important:**
- Save the `documentId` - you'll need it to append content or read the document
- The document URL is: `https://docs.google.com/document/d/[DOCUMENT_ID]/edit`

---

## SEO Report Templates

### Basic Audit Report Template

```markdown
# SEO Audit Report - [Website]
Date: [Date]

## Overview
[Website URL]
[Client Name]

## Technical SEO
- Site Speed: [Score]
- Mobile Friendly: [Yes/No]
- SSL: [Yes/No]
- XML Sitemap: [Yes/No]
- Robots.txt: [Status]

## On-Page SEO
- Title Tags: [Status]
- Meta Descriptions: [Status]
- Heading Structure: [Status]
- Content Quality: [Assessment]

## Recommendations
1. [Priority 1]
2. [Priority 2]
3. [Priority 3]

## Next Steps
- [Action item 1]
- [Action item 2]
```

### Blog Post Template

```markdown
# [Title]

## Introduction
[Hook - 2-3 sentences]

## [H2 Main Point 1]
[Supporting content]

### [H3 Detail]
[More details]

## [H2 Main Point 2]
[Supporting content]

## [H2 Main Point 3]
[Supporting content]

## Conclusion
[Summary and CTA]

---
Word Count: [X]
Target Keywords: [keywords]
```

---

## Configuration

Google Docs is auto-configured via environment variables:

```bash
GOOGLE_DOCS_CREDENTIALS_PATH=Google SA Credentials/tinyclaw-487419-d5ab318833bb.json
# OR
GOOGLE_APPLICATION_CREDENTIALS=Google SA Credentials/tinyclaw-487419-d5ab318833bb.json
```

Or programmatically:
```python
from agent import AgentConfig, GoogleDocsConfig

config = AgentConfig(
    google_docs_config=GoogleDocsConfig(
        credentials_path="Google SA Credentials/tinyclaw-487419-d5ab318833bb.json"
    )
)
```

---

## Common Errors and Solutions

### "Credentials file not found"
- Check that `GOOGLE_DOCS_CREDENTIALS_PATH` points to valid JSON file
- Ensure the service account has Google Docs API enabled

### "Document not found"
- Verify the document ID is correct
- The document may have been deleted (but delete is disabled)

### "Permission denied"
- Ensure the service account has proper OAuth scopes
- Check Google Docs API is enabled in Google Cloud Console

### "Rate limit exceeded"
- Add delays between API calls
- Batch content when possible

---

## Related Skills

- **seo-audit**: Run audits first, then save results to Google Docs
- **webflow-cms**: After creating content in Google Docs, publish to Webflow
- **copywriting**: Write blog posts, then save to Google Docs
- **content-strategy**: Plan content, then document in Google Docs
