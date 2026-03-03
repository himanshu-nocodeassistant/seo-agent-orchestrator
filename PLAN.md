# PLAN.md - Webflow API Integration for SEO Agent

## Problem Statement

The SEO Agent needs to integrate with Webflow CMS to manage collection items (create, edit posts, titles, descriptions, etc.). The user wants:
- Direct API integration using Python
- Modular architecture for easy management
- Red/Green TDD approach
- Clean, readable codebase

## Solution

Create a modular Python integration using Webflow's Data API v2.0, exposing operations as Claude Agent SDK custom tools.

---

## CMS Operations Required

| Operation | Description |
|-----------|-------------|
| **List Items** | Fetch all posts/items in a collection |
| **Get Item** | Get single item details by ID |
| **Create Item** | Create new post with title, slug, content, etc. |
| **Update Item** | Edit existing post fields |
| **Publish Item** | Publish item to live site |

---

## Modular Architecture

```
agent/
├── __init__.py           # Export WebflowClient, WebflowTools
├── config.py              # AgentConfig (add Webflow config)
├── seo_agent.py          # Main agent (integrate Webflow tools)
├── webflow/
│   ├── __init__.py       # Export all components
│   ├── client.py         # WebflowAPIClient - raw API calls
│   ├── tools.py          # @tool decorators for SDK tools
│   ├── server.py         # create_sdk_mcp_server setup
│   └── config.py         # WebflowConfig dataclass
```

---

## Red/Green TDD Approach

### Phase 1: RED (Write Failing Tests First)

#### Test 1: Webflow API Client
- [ ] **Test**: Can import and instantiate WebflowAPIClient
- [ ] **Expected**: Client initialized with token, site_id, collection_id

#### Test 2: List Collection Items
- [ ] **Test**: Call `list_items()` with valid credentials
- [ ] **Expected**: Returns list of items from collection

#### Test 3: Create Item
- [ ] **Test**: Call `create_item()` with title, slug, content
- [ ] **Expected**: New item created in collection

#### Test 4: Update Item  
- [ ] **Test**: Call `update_item()` with item_id and fields
- [ ] **Expected**: Item updated with new values

#### Test 5: Publish Item
- [ ] **Test**: Call `publish_item()` with item_id
- [ ] **Expected**: Item published to live site

#### Test 6: Custom Tool Integration
- [ ] **Test**: Webflow tools registered with SDK
- [ ] **Expected**: Tools accessible as `mcp__webflow__*`

---

### Phase 2: GREEN (Implement Solution)

#### Step 1: Create Webflow Config
- [ ] Create `agent/webflow/config.py` with WebflowConfig dataclass
- [ ] Fields: access_token, site_id, collection_id, base_url

#### Step 2: Create API Client
- [ ] Create `agent/webflow/client.py` with WebflowAPIClient class
- [ ] Methods: list_items, get_item, create_item, update_item, publish_item
- [ ] Use aiohttp for async HTTP requests

#### Step 3: Create SDK Tools
- [ ] Create `agent/webflow/tools.py` with @tool decorators
- [ ] Tools: list_cms_items, get_cms_item, create_cms_item, update_cms_item, publish_cms_item

#### Step 4: Create MCP Server
- [ ] Create `agent/webflow/server.py` with create_webflow_server()
- [ ] Register all tools with create_sdk_mcp_server

#### Step 5: Integrate with Agent
- [ ] Update `agent/__init__.py` to export Webflow components
- [ ] Update `agent/config.py` to include Webflow settings
- [ ] Update `agent/seo_agent.py` to accept and use Webflow MCP server

#### Step 6: Update main.py
- [ ] Pass Webflow configuration to AgentConfig

---

### Phase 3: REFACTOR (After Tests Pass)

- [ ] Add error handling for API failures
- [ ] Add logging for debugging
- [ ] Validate environment variables
- [ ] Document usage instructions

---

## API Reference

Based on [Webflow Data API v2.0](https://developers.webflow.com/data/v2.0.0/reference):

### Endpoints

```
Base URL: https://api.webflow.com

GET    /collections/{collection_id}/items         - List items
GET    /collections/{collection_id}/items/{id}   - Get item
POST   /collections/{collection_id}/items         - Create item
PATCH  /collections/{collection_id}/items         - Update item
POST   /collections/{collection_id}/items/publish - Publish item
```

### Headers
```
Authorization: Bearer {access_token}
Content-Type: application/json
```

---

## Success Criteria

1. ✅ Webflow client can authenticate with API token
2. ✅ List items returns collection items
3. ✅ Create item adds new post to collection
4. ✅ Update item modifies existing post
5. ✅ Publish item pushes to live site
6. ✅ Custom tools exposed via Claude Agent SDK
7. ✅ Modular, readable codebase
8. ✅ Tests pass for all operations
