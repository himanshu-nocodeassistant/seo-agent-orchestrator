"""
SEO Autonomous Agent using Claude Code CLI via subprocess.

This module provides the SEOAgent class that wraps Claude Code CLI
for performing autonomous SEO tasks. Uses OAuth authentication
via Claude Code (no API key required).
"""

import asyncio
import json
import subprocess
from typing import AsyncIterator, Optional
import logging
from pathlib import Path

from .config import AgentConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SEOAgent:
    """
    Autonomous SEO Agent that uses Claude Code CLI to perform SEO tasks.
    
    Uses Claude Code CLI via subprocess for reliable OAuth authentication.
    """
    
    def __init__(self, config: Optional[AgentConfig] = None):
        """Initialize the SEO Agent with configuration."""
        self.config = config or AgentConfig()
        self.session_id: Optional[str] = None
        
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
        # Run synchronously in a thread to not block
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, 
            self._run_claude, 
            prompt,
            ["--add-dir", self.config.cwd]
        )
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
