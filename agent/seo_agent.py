"""
SEO Autonomous Agent using Claude Agent SDK.

This module provides the SEOAgent class that wraps Claude Agent SDK
for performing autonomous SEO tasks. Uses OAuth authentication
via Claude Code (no API key required).

Memory System:
- Reads memory/CLAUDE.md at session start for SEO context
- Updates memory/seo-context.md after each task
"""

import asyncio
import json
from datetime import datetime
from typing import AsyncIterator, Optional
import logging
from pathlib import Path

from claude_agent_sdk import query, ClaudeSDKClient, ClaudeAgentOptions
from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage
from claude_agent_sdk._errors import MessageParseError

# Monkey-patch the SDK internal client so unknown message types (e.g. rate_limit_event)
# are silently skipped. The SDK calls parse_message() inside _internal/client.py and
# _internal/query.py which import it directly — so we must patch both the module
# attribute AND the reference inside the already-imported client module.
try:
    import claude_agent_sdk._internal.message_parser as _mp
    import claude_agent_sdk._internal.client as _mc

    _original_parse = _mp.parse_message

    def _safe_parse_message(data):
        try:
            return _original_parse(data)
        except MessageParseError as e:
            if "Unknown message type" in str(e):
                logging.getLogger(__name__).warning(
                    f"Skipping unknown SDK message type '{data.get('type')}'"
                )
                return None
            raise

    _mp.parse_message = _safe_parse_message
    _mc.parse_message = _safe_parse_message  # patch the already-imported reference
except Exception:
    pass

from .config import AgentConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Memory file paths (relative to project root)
MEMORY_DIR = "memory"
MEMORY_CLAUDE = "memory/CLAUDE.md"
MEMORY_STRATEGY = "memory/seo-strategy.md"
MEMORY_CONTEXT = "memory/seo-context.md"


class SEOAgent:
    """
    Autonomous SEO Agent that uses Claude Agent SDK to perform SEO tasks.
    
    Uses Claude Agent SDK for reliable OAuth authentication and proper
    communication with Claude Code.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """Initialize the SEO Agent with configuration."""
        self.config = config or AgentConfig()
        self.session_id: Optional[str] = None
        self.memory_context: dict = {}
        self._client: Optional[ClaudeSDKClient] = None
        
    def _get_memory_path(self, filename: str) -> Path:
        """Get absolute path to a memory file."""
        return Path(self.config.cwd) / filename
    
    def load_memory_context(self) -> str:
        """
        Load SEO context from memory files at session start.
        
        Returns:
            Combined context string to prepend to prompts
        """
        context_parts = []
        
        # Load main memory file
        memory_file = self._get_memory_path(MEMORY_CLAUDE)
        if memory_file.exists():
            try:
                content = memory_file.read_text()
                context_parts.append(f"## SEO Context\n{content}")
                logger.info(f"Loaded memory context from {MEMORY_CLAUDE}")
            except Exception as e:
                logger.warning(f"Failed to load {MEMORY_CLAUDE}: {e}")
        
        # Load current sprint state
        context_file = self._get_memory_path(MEMORY_CONTEXT)
        if context_file.exists():
            try:
                content = context_file.read_text()
                context_parts.append(f"## Current Sprint State\n{content}")
                logger.info(f"Loaded sprint context from {MEMORY_CONTEXT}")
            except Exception as e:
                logger.warning(f"Failed to load {MEMORY_CONTEXT}: {e}")
        
        if context_parts:
            return "\n\n".join(context_parts) + "\n\n"
        return ""
    
    def update_context_after_task(self, task: str, result: str) -> None:
        """
        Update seo-context.md after completing a task.
        
        Args:
            task: The task that was executed
            result: Summary of what was done
        """
        context_file = self._get_memory_path(MEMORY_CONTEXT)
        
        try:
            if context_file.exists():
                content = context_file.read_text()
            else:
                content = "# SEO Context - Sprint State\n\nNo context file found."
            
            # Find the "Last Session" section and update it
            today = datetime.now().strftime("%Y-%m-%d")
            
            # Truncate task and result
            task_summary = task[:80].replace('\n', ' ')
            result_summary = result[:150].replace('\n', ' ')
            
            new_entry = f"""## Last Session
- **Date:** {today}
- **Task:** {task_summary}
- **Outcome:** {result_summary}
"""
            
            # Remove any existing "## Last Session" section and everything after "---"
            # Keep everything before the session workflow section
            if "## Session Workflow" in content:
                content = content.split("## Session Workflow")[0]
            
            # Append new entry and footer
            footer = """

---

## Session Workflow

After each task, update this file with:
1. New tickets created
2. Completed tickets
3. What was done in the session
4. Any pending follow-ups
"""
            
            content = content.rstrip() + "\n\n" + new_entry + footer
            
            context_file.write_text(content)
            logger.info(f"Updated {MEMORY_CONTEXT} after task completion")
            
        except Exception as e:
            logger.warning(f"Failed to update {MEMORY_CONTEXT}: {e}")
    
    def _build_prompt_with_context(self, prompt: str, prompt_context=None) -> str:
        """Build prompt with memory context.

        If prompt_context is provided (a ComposedPromptContext), it is already
        embedded in the prompt string by the caller — skip the file-based memory
        load to avoid duplicating context.
        """
        if prompt_context is not None:
            return prompt

        memory_context = self.load_memory_context()

        if memory_context:
            return f"""{memory_context}

## Task

{prompt}

## Important: Update Context After Task

After completing this task, you MUST update the file `memory/seo-context.md` to reflect:
1. What was accomplished
2. Any new tickets created
3. Any pending follow-up actions

Use the Edit tool to update memory/seo-context.md before ending your response.
"""
        return prompt
    
    def _create_sdk_options(self) -> ClaudeAgentOptions:
        """Create ClaudeAgentOptions from AgentConfig."""
        return ClaudeAgentOptions(
            cwd=self.config.cwd,
            permission_mode=self.config.permission_mode,
            allowed_tools=self.config.allowed_tools,
            setting_sources=self.config.setting_sources,
            system_prompt=self.config.system_prompt,
            model=self.config.model,
            max_turns=self.config.max_turns,
            max_budget_usd=self.config.max_budget_usd,
            mcp_servers=self.config.mcp_servers,
            hooks=self.config.hooks,
        )
    
    async def execute_task(self, prompt: str) -> str:
        """
        Execute a single SEO task using the SDK.
        
        Args:
            prompt: The task description for Claude
            
        Returns:
            The result from Claude
        """
        full_prompt = self._build_prompt_with_context(prompt)
        options = self._create_sdk_options()
        
        result_text = ""
        
        try:
            async for message in query(prompt=full_prompt, options=options):
                if message is None:
                    # Skipped by safe_parse_message patch (unknown type e.g. rate_limit_event)
                    continue
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                elif isinstance(message, ResultMessage):
                    if message.result:
                        result_text += message.result
                    # Capture session ID from result message
                    if message.session_id:
                        self.session_id = message.session_id
        except MessageParseError as e:
            logger.warning(f"SDK message parse error: {e}")
        
        # Update context after task completion
        if result_text:
            self.update_context_after_task(prompt, result_text)
        
        return result_text
    
    async def chat(self, message: str) -> str:
        """
        Send a message in the current conversation using ClaudeSDKClient.
        
        Args:
            message: The message to send
            
        Returns:
            Claude's response
        """
        # Create a new client for each chat message if not already created
        if self._client is None:
            self._client = ClaudeSDKClient(self._create_sdk_options())
            await self._client.connect()
        
        # Send the message
        await self._client.query(message)
        
        # Collect response
        result_text = ""
        async for message in self._client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result_text += block.text
            elif isinstance(message, ResultMessage):
                if message.result:
                    result_text += message.result
        
        return result_text
    
    async def execute_task_streaming(self, prompt: str) -> AsyncIterator[str]:
        """
        Execute a task and yield results as they arrive.
        
        Args:
            prompt: The task description for Claude
            
        Yields:
            Results as they arrive
        """
        full_prompt = self._build_prompt_with_context(prompt)
        options = self._create_sdk_options()
        
        try:
            async for message in query(prompt=full_prompt, options=options):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            yield block.text
                elif isinstance(message, ResultMessage):
                    if message.result:
                        yield message.result
        except MessageParseError as e:
            logger.warning(f"SDK message parse error in streaming (likely rate limit event): {e}")
    
    async def interrupt(self) -> None:
        """Interrupt the current task using ClaudeSDKClient."""
        if self._client:
            await self._client.interrupt()
            logger.info("Task interrupted via SDK")
    
    async def disconnect(self) -> None:
        """Disconnect the SDK client."""
        if self._client:
            await self._client.disconnect()
            self._client = None
            logger.info("Disconnected from Claude SDK")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
    
    @classmethod
    async def create_and_run_result(
        cls,
        prompt: str,
        config: Optional[AgentConfig] = None,
        prompt_context=None,
    ):
        """
        Run a prompt and return an AgentExecutionResult-like object with
        .result_text and .session_id attributes.

        Used by _run_agent_prompt in api/main.py so the full layered-memory
        workflow (config, hooks, session resume) goes through one code path.
        """
        agent = cls(config)
        try:
            full_prompt = agent._build_prompt_with_context(prompt, prompt_context)
            options = agent._create_sdk_options()
            result_text = ""
            session_id = None

            async for message in query(prompt=full_prompt, options=options):
                if message is None:
                    continue
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            result_text += block.text
                elif isinstance(message, ResultMessage):
                    if message.result:
                        result_text += message.result
                    if message.session_id:
                        session_id = message.session_id

            if result_text:
                agent.update_context_after_task(prompt, result_text)

            return type(
                "AgentExecutionResult",
                (),
                {"result_text": result_text, "session_id": session_id},
            )()
        except MessageParseError as e:
            logger.warning("SDK message parse error in create_and_run_result: %s", e)
            return type(
                "AgentExecutionResult",
                (),
                {"result_text": "", "session_id": None},
            )()
        finally:
            await agent.disconnect()

    @classmethod
    async def create_and_run(cls, prompt: str, config: Optional[AgentConfig] = None) -> str:
        """
        Convenience method to create agent, run task, and disconnect.
        
        Args:
            prompt: The task to execute
            config: Optional configuration
            
        Returns:
            The result from Claude
        """
        agent = cls(config)
        try:
            return await agent.execute_task(prompt)
        finally:
            await agent.disconnect()

