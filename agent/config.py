"""
Configuration for the SEO Autonomous Agent.

This module provides the AgentConfig dataclass that controls
how the SEO agent operates, including model selection,
permissions, and working directory.
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from agent.retry import RetryConfig

# Import config types only for type hints
if TYPE_CHECKING:
    from .google_docs import GoogleDocsConfig


@dataclass
class AgentConfig:
    """Configuration for the SEO Autonomous Agent."""

    # Working directory for the agent
    cwd: str = str(Path(__file__).parent.parent)

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

    # Google Docs configuration (optional)
    google_docs_config: Optional["GoogleDocsConfig"] = None

    # MCP servers dict for Claude Agent SDK
    mcp_servers: dict = field(default_factory=dict)

    # Target site URL (used in prompts and orchestration)
    site_url: str = field(default_factory=lambda: os.environ.get("TARGET_SITE_URL", "https://example.com"))

    # Target site name (used in prompts and orchestration)
    site_name: str = field(default_factory=lambda: os.environ.get("TARGET_SITE_NAME", "My Site"))

    # Retry configuration for failed tool calls
    retry_config: RetryConfig = field(default_factory=RetryConfig)

    # Enable supervisor logging (Phase 1)
    enable_supervisor_logging: bool = field(default_factory=lambda: os.environ.get("SUPERVISOR_LOGGING", "true").lower() == "true")

    # Enable validation layer (Phase 3)
    enable_validation: bool = True

    # Validation score threshold (0.0 - 1.0)
    validation_threshold: float = 0.7

    def __post_init__(self):
        """Set defaults after initialization."""
        # Resolve Claude CLI path — CLAUDE_CLI_PATH env var overrides, then shutil.which
        cli_path = os.environ.get("CLAUDE_CLI_PATH") or shutil.which("claude")
        if not cli_path or not Path(cli_path).exists():
            raise FileNotFoundError(
                "Claude CLI not found. Set CLAUDE_CLI_PATH or ensure 'claude' is on PATH. "
                "Install with: npm install -g @anthropic-ai/claude-code"
            )

        # Auto-configure Google Docs MCP server if config is provided
        if self.google_docs_config is not None:
            self._setup_google_docs_mcp()

    def _setup_google_docs_mcp(self):
        """Set up Google Docs MCP server from config."""
        from .google_docs import create_google_docs_server

        # Create MCP server from Google Docs config
        google_docs_server = create_google_docs_server(self.google_docs_config)

        # Add to MCP servers dict
        self.mcp_servers["google_docs"] = google_docs_server

        # Add Google Docs tools to allowed tools
        google_docs_tool_names = [
            "mcp__google_docs__create_google_doc",
            "mcp__google_docs__get_google_doc",
            "mcp__google_docs__append_to_google_doc",
            "mcp__google_docs__update_google_doc_title",
        ]
        for tool_name in google_docs_tool_names:
            if tool_name not in self.allowed_tools:
                self.allowed_tools.append(tool_name)

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """
        Create AgentConfig from environment variables.

        Environment variables:
        - GOOGLE_DOCS_CREDENTIALS_PATH: Path to Google service account credentials
        - GOOGLE_APPLICATION_CREDENTIALS: Alternative credentials path
        - TARGET_SITE_URL: Target site URL for prompts (default: https://example.com)
        - TARGET_SITE_NAME: Target site name for prompts (default: My Site)
        - CLAUDE_CLI_PATH: Optional override for Claude CLI binary location

        Returns:
            AgentConfig instance with integrations configured if env vars present
        """
        # Check for Google Docs env vars
        google_docs_config = None
        if os.environ.get("GOOGLE_DOCS_CREDENTIALS_PATH") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            from .google_docs import GoogleDocsConfig
            google_docs_config = GoogleDocsConfig.from_env()

        return cls(
            google_docs_config=google_docs_config,
            retry_config=RetryConfig(
                max_attempts=int(os.environ.get("RETRY_MAX_ATTEMPTS", "3")),
                initial_delay_ms=int(os.environ.get("RETRY_INITIAL_DELAY_MS", "1000")),
                max_delay_ms=int(os.environ.get("RETRY_MAX_DELAY_MS", "10000")),
                backoff_multiplier=float(os.environ.get("RETRY_BACKOFF_MULTIPLIER", "2.0")),
            ),
            enable_supervisor_logging=os.environ.get("SUPERVISOR_LOGGING", "true").lower() == "true",
        )
