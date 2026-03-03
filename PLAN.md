# PLAN.md - SDK Integration for SEO Agent

## Problem Statement

The current implementation uses `subprocess.run()` to call Claude CLI directly, which causes the error:
> "Execution failed: ProcessTransport is not ready for writing"

This error occurs because the Claude Agent SDK is not being used correctly.

## Solution

Rewrite `agent/seo_agent.py` to properly use the Claude Agent SDK:
- Use `query()` function for single task execution (`create_and_run`)
- Use `ClaudeSDKClient` for interactive mode (`chat()` method)
- Preserve existing memory/context functionality

---

## Red/Green TDD Approach

### Phase 1: RED (Write Failing Tests First)

#### Test 1: SDK Import Test
- [ ] **Test**: Verify `claude_agent_sdk` can be imported
- [ ] **Expected**: Import succeeds without errors

#### Test 2: Single Task Execution (`create_and_run`)
- [ ] **Test**: Run `python main.py "Hello, what is 2+2?"`
- [ ] **Expected**: 
  - [ ] ✅ Returns a valid response
  - [ ] ✅ No "ProcessTransport" error
  - [ ] ✅ Context is loaded from memory files

#### Test 3: Interactive Mode
- [ ] **Test**: Run `python main.py` and send "Hello"
- [ ] **Expected**:
  - [ ] ✅ Agent responds without error
  - [ ] ✅ Conversation continues properly

---

### Phase 2: GREEN (Implement Solution)

#### Step 1: Update imports in `agent/seo_agent.py`
- [ ] Import `query`, `ClaudeSDKClient`, `ClaudeAgentOptions` from `claude_agent_sdk`
- [ ] Import message types: `AssistantMessage`, `TextBlock`, `ResultMessage`

#### Step 2: Rewrite `execute_task()` method
- [ ] Replace subprocess call with `query()` function
- [ ] Map `AgentConfig` fields to `ClaudeAgentOptions`
- [ ] Handle streaming messages properly

#### Step 3: Rewrite `chat()` method for interactive mode
- [ ] Implement `ClaudeSDKClient` context manager
- [ ] Use `client.query()` to send messages
- [ ] Use `client.receive_response()` to get responses

#### Step 4: Update `agent/config.py` if needed
- [ ] Ensure all required SDK options are supported
- [ ] Add any missing field mappings

#### Step 5: Preserve Memory System
- [ ] Keep `load_memory_context()` functionality
- [ ] Keep `update_context_after_task()` functionality
- [ ] Verify memory files are read/written correctly

---

### Phase 3: REFACTOR (After Tests Pass)

- [ ] Clean up any unused code
- [ ] Add proper error handling
- [ ] Add logging for debugging
- [ ] Document any API changes

---

## Implementation Notes

### Key Code Changes

**Before (broken):**
```python
def _run_claude(self, prompt: str, extra_args: list = None) -> str:
    cmd = [self.config.cli_path, "--print", "--verbose", ...]
    result = subprocess.run(cmd, ...)
```

**After (fixed):**
```python
from claude_agent_sdk import query, ClaudeAgentOptions, ClaudeSDKClient
from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage

async def execute_task(self, prompt: str) -> str:
    options = ClaudeAgentOptions(
        cwd=self.config.cwd,
        permission_mode=self.config.permission_mode,
        allowed_tools=self.config.allowed_tools,
        setting_sources=self.config.setting_sources,
        model=self.config.model,
    )
    
    full_prompt = self._build_prompt_with_context(prompt)
    
    result_text = ""
    async for message in query(prompt=full_prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    result_text += block.text
        elif isinstance(message, ResultMessage):
            if message.result:
                result_text += message.result
    
    return result_text
```

---

## Verification Commands

```bash
# Test 1: Single task
python main.py "What is 1+1?"

# Test 2: Interactive mode
# (run without arguments, then type "Hello")
python main.py
```

---

## Success Criteria

1. ✅ No "ProcessTransport is not ready for writing" error
2. ✅ Single task execution works: `python main.py "task"`
3. ✅ Interactive mode works: `python main.py` + chat
4. ✅ Memory context is loaded before tasks
5. ✅ Memory context is updated after tasks
6. ✅ All existing functionality preserved
