"""
Configuration for the SEO Autonomous Agent.

This module provides the AgentConfig dataclass that controls
how the SEO agent operates, including model selection,
permissions, and working directory.
"""

from dataclasses import dataclass, field
from pathlib import Path
import shutil
from typing import TYPE_CHECKING, Optional

import os


# Last-resort fallback only (legacy machine-specific path). Real resolution
# order: explicit arg > CLAUDE_CLI_PATH env > PATH lookup > this fallback.
_DEFAULT_CLI_PATH = "/Users/himanshusharma/.npm-global/bin/claude"

# Import config types only for type hints
if TYPE_CHECKING:
    from .webflow import WebflowConfig
    from .google_docs import GoogleDocsConfig


def _resolve_cli_path(explicit: Optional[str]) -> Optional[str]:
    """Resolve the Claude Code CLI path with environment/PATH fallbacks.

    Returns None when no usable CLI is found — validation happens lazily at
    run time so configs can be constructed for introspection/tests without a
    Claude install.
    """
    candidate = explicit or os.environ.get("CLAUDE_CLI_PATH")
    if candidate:
        path = Path(candidate).expanduser()
        if not path.exists():
            raise FileNotFoundError(
                f"Claude CLI not found at {path}. "
                "Set CLAUDE_CLI_PATH to the claude executable, or install "
                "Claude Code: npm install -g @anthropic-ai/claude-code"
            )
        return str(path)

    which = shutil.which("claude")
    if which:
        return which

    if Path(_DEFAULT_CLI_PATH).exists():
        return _DEFAULT_CLI_PATH

    return None


@dataclass
class AgentConfig:
    """Configuration for the SEO Autonomous Agent."""

    # Working directory for the agent
    cwd: str = str(Path(__file__).parent.parent)

    # Claude CLI path - uses OAuth via Claude Code (no API key needed).
    # None means auto-detect: CLAUDE_CLI_PATH env > PATH > legacy default.
    cli_path: Optional[str] = None

    # Model to use (default, sonnet, opus, haiku)
    # Use "default" for Claude Code's default model
    model: str = "sonnet"

    # Permission mode for the agent
    permission_mode: str = "acceptEdits"

    # Tools allowed for the agent
    # Bash is intentionally absent — _build_runtime_config stamps the profile's
    # explicit list before any real run. Direct callers (CLI, tests) should not
    # get shell access by default.
    allowed_tools: list = field(default_factory=lambda: [
        "Read", "Write", "Edit", "Glob", "Grep",
        "WebSearch", "WebFetch", "Skill"
    ])

    # Setting sources for loading Skills
    setting_sources: list = field(default_factory=lambda: ["user", "project"])

    # PostToolUse / other SDK hooks — see ClaudeAgentOptions.hooks
    hooks: Optional[dict] = None

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

    # Webflow CMS configuration (optional)
    webflow_config: Optional["WebflowConfig"] = None

    # Google Docs configuration (optional)
    google_docs_config: Optional["GoogleDocsConfig"] = None

    # MCP servers dict for Claude Agent SDK
    mcp_servers: dict = field(default_factory=dict)

    def __post_init__(self):
        """Set defaults after initialization."""
        # Resolve CLI path (env/PATH/legacy fallbacks); validated at run time
        self.cli_path = _resolve_cli_path(self.cli_path)

        # Auto-configure Webflow MCP server if config is provided
        if self.webflow_config is not None:
            self._setup_webflow_mcp()

        # Auto-configure Google Docs MCP server if config is provided
        if self.google_docs_config is not None:
            self._setup_google_docs_mcp()

    def _setup_webflow_mcp(self):
        """Set up Webflow MCP server from config."""
        from .webflow import create_webflow_server

        # Create MCP server from Webflow config
        webflow_server = create_webflow_server(self.webflow_config)

        # Add to MCP servers dict
        self.mcp_servers["webflow"] = webflow_server

        # Add Webflow tools to allowed tools
        webflow_tool_names = [
            "mcp__webflow__list_cms_items",
            "mcp__webflow__get_cms_item",
            "mcp__webflow__create_cms_item",
            "mcp__webflow__update_cms_item",
            "mcp__webflow__publish_cms_item",
            "mcp__webflow__get_collection_info",
        ]
        for tool_name in webflow_tool_names:
            if tool_name not in self.allowed_tools:
                self.allowed_tools.append(tool_name)

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
        - WEBFLOW_ACCESS_TOKEN: Webflow API token
        - WEBFLOW_SITE_ID: Webflow site ID
        - WEBFLOW_COLLECTION_ID: Webflow collection ID
        - GOOGLE_DOCS_CREDENTIALS_PATH: Path to Google service account credentials
        - GOOGLE_APPLICATION_CREDENTIALS: Alternative credentials path

        Returns:
            AgentConfig instance with integrations configured if env vars present
        """
        # SEO_AGENT_CWD overrides the repo-root working directory
        cwd = os.environ.get("SEO_AGENT_CWD")
        if cwd:
            if not Path(cwd).exists():
                raise FileNotFoundError(
                    f"SEO_AGENT_CWD points to a missing directory: {cwd}"
                )

        # Check for Webflow env vars
        webflow_config = None
        if os.environ.get("WEBFLOW_ACCESS_TOKEN"):
            from .webflow import WebflowConfig
            webflow_config = WebflowConfig.from_env()

        # Check for Google Docs env vars
        google_docs_config = None
        if os.environ.get("GOOGLE_DOCS_CREDENTIALS_PATH") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            from .google_docs import GoogleDocsConfig
            google_docs_config = GoogleDocsConfig.from_env()

        return cls(
            cwd=cwd or str(Path(__file__).parent.parent),
            webflow_config=webflow_config,
            google_docs_config=google_docs_config,
        )
