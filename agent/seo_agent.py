"""
SEO Autonomous Agent using Claude Code CLI via subprocess.

This module provides the SEOAgent class that wraps Claude Code CLI
for performing autonomous SEO tasks. Uses OAuth authentication
via Claude Code (no API key required).

Memory System:
- Reads memory/CLAUDE.md at session start for SEO context
- Updates memory/seo-context.md after each task
"""

import asyncio
import json
import subprocess
from datetime import datetime
from typing import AsyncIterator, Optional
import logging
from pathlib import Path

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
    Autonomous SEO Agent that uses Claude Code CLI to perform SEO tasks.
    
    Uses Claude Code CLI via subprocess for reliable OAuth authentication.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """Initialize the SEO Agent with configuration."""
        self.config = config or AgentConfig()
        self.session_id: Optional[str] = None
        self.memory_context: dict = {}
        
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
    
    def _run_claude(self, prompt: str, extra_args: list = None) -> str:
        """Run Claude CLI with the given prompt."""
        cmd = [
            self.config.cli_path,
            "--print",  # Non-interactive output
            "--verbose",
            "--no-chrome",
            "--model", self.config.model,  # Use configured model
            prompt
        ]
        
        if extra_args:
            cmd.extend(extra_args)
        
        result = subprocess.run(
            cmd,
            cwd=self.config.cwd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if result.returncode != 0:
            logger.error(f"Claude CLI error: {result.stderr}")
            return f"Error: {result.stderr}"
        
        return result.stdout
    
    async def execute_task(self, prompt: str) -> str:
        """
        Execute a single SEO task.
        
        Args:
            prompt: The task description for Claude
            
        Returns:
            The result from Claude
        """
        # Load memory context at session start
        memory_context = self.load_memory_context()
        
        # Build prompt with memory context
        if memory_context:
            full_prompt = f"""{memory_context}

## Task

{prompt}

## Important: Update Context After Task

After completing this task, you MUST update the file `memory/seo-context.md` to reflect:
1. What was accomplished
2. Any new tickets created
3. Any pending follow-up actions

Use the Edit tool to update memory/seo-context.md before ending your response.
"""
        else:
            full_prompt = prompt
        
        # Run synchronously in a thread to not block
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            self._run_claude, 
            full_prompt,
            ["--add-dir", self.config.cwd]
        )
        
        # Update context after task completion
        if result and not result.startswith("Error:"):
            self.update_context_after_task(prompt, result)
        
        return result
    
    async def chat(self, message: str) -> str:
        """
        Send a message in the current conversation.
        
        Args:
            message: The message to send
            
        Returns:
            Claude's response
        """
        return await self.execute_task(message)
    
    async def execute_task_streaming(self, prompt: str) -> AsyncIterator[str]:
        """
        Execute a task and yield results as they arrive.
        
        Note: This uses polling for simplicity.
        """
        result = await self.execute_task(prompt)
        yield result
    
    async def interrupt(self) -> None:
        """Interrupt the current task (not applicable for subprocess)."""
        logger.info("Interrupt not supported in subprocess mode")
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        pass
    
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
        return await agent.execute_task(prompt)


# Alias for backwards compatibility
class ClaudeSDKClient:
    """Compatibility wrapper - not used in subprocess mode."""
    pass
