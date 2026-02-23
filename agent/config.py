"""
Configuration for the SEO Autonomous Agent.

This module provides the AgentConfig dataclass that controls
how the SEO agent operates, including model selection,
permissions, and working directory.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os


# Claude Code CLI path - uses OAuth via Claude Code
CLAUDE_CLI_PATH = "/Users/himanshusharma/.npm-global/bin/claude"


@dataclass
class AgentConfig:
    """Configuration for the SEO Autonomous Agent."""
    
    # Working directory for the agent
    cwd: str = str(Path(__file__).parent.parent)
    
    # Claude CLI path - uses OAuth via Claude Code (no API key needed)
    cli_path: str = CLAUDE_CLI_PATH
    
    # Model to use (default, sonnet, opus, haiku)
    # Use "default" for Claude Code's default model
    model: str = "sonnet"
    
    # Permission mode for the agent
    permission_mode: str = "acceptEdits"
    
    # Tools allowed for the agent
    allowed_tools: list = field(default_factory=lambda: [
        "Read", "Write", "Edit", "Bash", "Glob", "Grep", 
        "WebSearch", "WebFetch", "Skill"
    ])
    
    # Setting sources for loading Skills
    setting_sources: list = field(default_factory=lambda: ["user", "project"])
    
    # Max turns per task
    max_turns: Optional[int] = None
    
    # Max budget in USD
    max_budget_usd: Optional[float] = None
    
    # Enable file checkpointing for rewinding
    enable_file_checkpointing: bool = False
    
    # Session ID to resume (optional)
    resume: Optional[str] = None
    
    # Custom system prompt
    system_prompt: Optional[str] = None
    
    def __post_init__(self):
        """Set defaults after initialization."""
        # Verify CLI path exists
        if not Path(self.cli_path).exists():
            raise FileNotFoundError(
                f"Claude CLI not found at {self.cli_path}. "
                "Please install Claude Code: npm install -g @anthropic-ai/claude-code"
            )
