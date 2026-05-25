"""
Comprehensive tests for SEO Agent.

Tests cover:
2. Memory System - loading and updating context
3. Skills - skill loading and invocation
4. Interrupt Feature - interrupting running tasks
5. Session Continuity - conversation memory across messages
"""

import pytest
import asyncio
import zipfile
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.seo_agent import SEOAgent
from agent.config import AgentConfig


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_cwd(tmp_path):
    """Create a temporary working directory with test files."""
    cwd = tmp_path / "test_project"
    cwd.mkdir()
    
    memory_dir = cwd / "memory"
    memory_dir.mkdir()
    
    claude_md = memory_dir / "CLAUDE.md"
    claude_md.write_text("""# SEO Project Context

This is a test SEO project.
Current focus: Content optimization
""")
    
    context_md = memory_dir / "seo-context.md"
    context_md.write_text("""# SEO Context - Sprint State

## Current Sprint
- Sprint 1: Site audit

## Last Session
- **Date:** 2026-01-01
- **Task:** Initial setup
- **Outcome:** Completed

## Session Workflow
""")
    
    return str(cwd)


@pytest.fixture
def agent_config(temp_cwd):
    """Create AgentConfig for testing."""
    return AgentConfig(
        cwd=temp_cwd,
        model="sonnet",
        permission_mode="acceptEdits",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Skill"],
        setting_sources=["user", "project"],
    )


@pytest.fixture
def agent(agent_config):
    """Create SEOAgent instance."""
    return SEOAgent(agent_config)


# ============================================================================
# TEST 2: MEMORY SYSTEM
# ============================================================================

class TestMemorySystem:
    """Test memory loading and updating functionality."""
    
    def test_load_memory_context(self, agent, temp_cwd):
        """Test that memory context is loaded from files."""
        context = agent.load_memory_context()
        
        assert "SEO Project Context" in context
        assert "This is a test SEO project" in context
    
    def test_load_sprint_state(self, agent, temp_cwd):
        """Test that sprint state is loaded."""
        context = agent.load_memory_context()
        
        assert "Sprint State" in context
        assert "Sprint 1: Site audit" in context
    
    def test_load_memory_nonexistent_file(self, agent, tmp_path):
        """Test handling of missing memory files."""
        config = AgentConfig(cwd=str(tmp_path / "nonexistent"))
        agent_no_mem = SEOAgent(config)
        
        context = agent_no_mem.load_memory_context()
        assert context == ""
    
    def test_update_context_after_task(self, agent, temp_cwd):
        """Test that context is updated after task completion."""
        task = "Test task for SEO optimization"
        result = "Completed SEO optimization for homepage"
        
        context_file = Path(temp_cwd) / "memory" / "seo-context.md"
        
        agent.update_context_after_task(task, result)
        
        updated_content = context_file.read_text()
        assert "Test task for SEO optimization" in updated_content
        
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in updated_content
    
    def test_update_context_truncates_long_content(self, agent, temp_cwd):
        """Test that long task/result content is truncated."""
        long_task = "A" * 200
        long_result = "B" * 300
        
        agent.update_context_after_task(long_task, long_result)
        
        context_file = Path(temp_cwd) / "memory" / "seo-context.md"
        content = context_file.read_text()
        
        assert len([l for l in content.split('\n') if l.startswith('- **Task:**')][0]) <= 100
    
    def test_build_prompt_with_context(self, agent):
        """Test prompt building with memory context."""
        prompt = "Analyze the website"
        full_prompt = agent._build_prompt_with_context(prompt)
        
        assert "SEO Project Context" in full_prompt
        assert "Analyze the website" in full_prompt
        assert "Update Context After Task" in full_prompt
    
    def test_build_prompt_without_context(self, agent, tmp_path):
        """Test prompt building without memory files."""
        config = AgentConfig(cwd=str(tmp_path))
        agent_empty = SEOAgent(config)
        
        prompt = "Simple task"
        full_prompt = agent_empty._build_prompt_with_context(prompt)
        
        assert full_prompt == prompt


# ============================================================================
# TEST 3: SKILLS
# ============================================================================

class TestSkills:
    """Test skill loading and invocation."""
    
    def test_skills_config_present(self, agent_config):
        """Test that skills are configured in allowed_tools."""
        assert "Skill" in agent_config.allowed_tools
    
    def test_setting_sources_configured(self, agent_config):
        """Test that setting_sources is configured for skills."""
        assert "project" in agent_config.setting_sources
        assert "user" in agent_config.setting_sources
    
    @pytest.mark.asyncio
    async def test_execute_task_with_skill(self, temp_cwd, tmp_path):
        """Test executing a task that uses a skill."""
        skills_dir = tmp_path / ".claude" / "skills" / "test-skill"
        skills_dir.mkdir(parents=True)
        
        skill_md = skills_dir / "SKILL.md"
        skill_md.write_text("""---
description: Test skill for SEO analysis
---

# Test Skill

This is a test skill for SEO tasks.
""")
        
        config = AgentConfig(
            cwd=temp_cwd,
            allowed_tools=["Read", "Skill"],
            setting_sources=["project"],
        )
        agent = SEOAgent(config)
        
        with patch('agent.seo_agent.query') as mock_query:
            from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage
            
            mock_msg = AssistantMessage(
                content=[TextBlock(text="Used skill to analyze content")],
                model="sonnet"
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=1000,
                duration_api_ms=500,
                is_error=False,
                num_turns=1,
                session_id="test-session"
            )
            
            async def mock_generator():
                yield mock_msg
                yield result_msg
            
            mock_query.return_value = mock_generator()
            
            result = await agent.execute_task("Use skill to analyze")
            
            assert "analyze" in result.lower()
            mock_query.assert_called_once()
    
    def test_skill_directory_structure(self):
        """Test that Skills directory exists and has expected structure.
        
        .skill files are ZIP archives containing SKILL.md with frontmatter.
        """
        skills_dir = Path("Skills")
        
        if skills_dir.exists():
            skill_files = list(skills_dir.glob("*.skill"))
            assert len(skill_files) > 0, "Should have at least one skill file"
            
            # Each .skill file is a ZIP archive containing SKILL.md
            for skill_file in skill_files:
                try:
                    with zipfile.ZipFile(skill_file, 'r') as zf:
                        # Look for SKILL.md inside the archive
                        namelist = zf.namelist()
                        skill_md_files = [n for n in namelist if n.endswith('SKILL.md')]
                        assert len(skill_md_files) > 0, f"Skill {skill_file.name} should contain SKILL.md"
                        
                        # Read SKILL.md content and check for frontmatter
                        with zf.open(skill_md_files[0]) as f:
                            content = f.read().decode('utf-8')
                        assert "---" in content, f"Skill {skill_file.name} should have frontmatter"
                except zipfile.BadZipFile:
                    # Not a valid ZIP - skip or fail appropriately
                    assert False, f"Skill file {skill_file.name} is not a valid ZIP archive"


# ============================================================================
# TEST 4: INTERRUPT FEATURE
# ============================================================================

class TestInterruptFeature:
    """Test interrupt functionality."""
    
    @pytest.mark.asyncio
    async def test_interrupt_with_client(self, agent):
        """Test interrupt when client is active."""
        mock_client = AsyncMock()
        agent._client = mock_client
        
        await agent.interrupt()
        
        mock_client.interrupt.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_interrupt_without_client(self, agent):
        """Test interrupt when no client is active."""
        agent._client = None
        
        await agent.interrupt()
    
    @pytest.mark.asyncio
    async def test_disconnect(self, agent):
        """Test disconnect functionality."""
        mock_client = AsyncMock()
        agent._client = mock_client
        
        await agent.disconnect()
        
        mock_client.disconnect.assert_called_once()
        assert agent._client is None
    
    @pytest.mark.asyncio
    async def test_context_manager_disconnects(self, agent_config):
        """Test that context manager properly disconnects."""
        mock_client = AsyncMock()
        
        with patch('agent.seo_agent.ClaudeSDKClient') as MockClient:
            MockClient.return_value = mock_client
            
            async with SEOAgent(agent_config) as agent:
                agent._client = mock_client
            
            mock_client.disconnect.assert_called_once()


# ============================================================================
# TEST 5: SESSION CONTINUITY
# ============================================================================

class TestSessionContinuity:
    """Test conversation memory across messages."""
    
    @pytest.mark.asyncio
    async def test_session_id_captured(self, agent):
        """Test that session ID is captured from responses."""
        with patch('agent.seo_agent.query') as mock_query:
            from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage
            
            mock_msg = AssistantMessage(
                content=[TextBlock(text="Hello")],
                model="sonnet"
            )
            result_msg = ResultMessage(
                subtype="success",
                duration_ms=1000,
                duration_api_ms=500,
                is_error=False,
                num_turns=1,
                session_id="test-session-123"
            )
            
            async def mock_generator():
                yield mock_msg
                yield result_msg
            
            mock_query.return_value = mock_generator()
            
            await agent.execute_task("Say hello")
            
            assert agent.session_id == "test-session-123"
    
    @pytest.mark.asyncio
    async def test_chat_creates_client_once(self, agent):
        """Test that chat reuses the same client.
        
        Properly mocks async generator for receive_response.
        """
        mock_client = AsyncMock()
        
        # Create proper async generator mock for receive_response
        async def mock_receive_response():
            return
            yield  # Makes this an async generator
        
        mock_client.receive_response = mock_receive_response
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.query = AsyncMock()
        
        with patch('agent.seo_agent.ClaudeSDKClient', return_value=mock_client):
            await agent.chat("Hello")
            
            assert agent._client is not None
            
            first_client = agent._client
            
            await agent.chat("How are you?")
            
            assert agent._client is first_client
    
    @pytest.mark.asyncio
    async def test_chat_continues_conversation(self, agent):
        """Test that chat maintains conversation context.
        
        Properly mocks async generator for receive_response.
        """
        mock_client = AsyncMock()
        
        from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage
        
        # First response as async generator
        async def mock_receive_first():
            yield AssistantMessage(content=[TextBlock(text="Hello!")], model="sonnet")
            yield ResultMessage(subtype="success", duration_ms=500, duration_api_ms=250, 
                        is_error=False, num_turns=1, session_id="session-1")
        
        # Second response as async generator
        async def mock_receive_second():
            yield AssistantMessage(content=[TextBlock(text="I remember you said hello")], model="sonnet")
            yield ResultMessage(subtype="success", duration_ms=500, duration_api_ms=250,
                        is_error=False, num_turns=2, session_id="session-1")
        
        mock_client.receive_response = Mock(side_effect=[mock_receive_first(), mock_receive_second()])
        mock_client.connect = AsyncMock()
        mock_client.disconnect = AsyncMock()
        mock_client.query = AsyncMock()
        
        with patch('agent.seo_agent.ClaudeSDKClient', return_value=mock_client):
            await agent.chat("Hello")
            
            mock_client.connect.assert_called_once()
            
            mock_client.query.assert_called_with("Hello")
            
            mock_client.query.reset_mock()
            
            await agent.chat("What did I say?")
            
            mock_client.query.assert_called_with("What did I say?")
    
    @pytest.mark.asyncio
    async def test_create_and_run_disconnects(self, agent_config):
        """Test that create_and_run properly disconnects."""
        with patch('agent.seo_agent.query') as mock_query:
            from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage
            
            mock_msg = AssistantMessage(content=[TextBlock(text="Done")], model="sonnet")
            result_msg = ResultMessage(subtype="success", duration_ms=100, duration_api_ms=50,
                                      is_error=False, num_turns=1, session_id="s1")
            
            async def mock_gen():
                yield mock_msg
                yield result_msg
            
            mock_query.return_value = mock_gen()
            
            with patch.object(SEOAgent, 'disconnect') as mock_disconnect:
                await SEOAgent.create_and_run("Test task", agent_config)
                
                mock_disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_multiple_tasks_maintain_session(self, agent):
        """Test that multiple execute_task calls can maintain session."""
        session_ids = []
        
        with patch('agent.seo_agent.query') as mock_query:
            from claude_agent_sdk.types import AssistantMessage, TextBlock, ResultMessage
            
            async def mock_generator(session_id):
                msg = AssistantMessage(content=[TextBlock(text="Response")], model="sonnet")
                result = ResultMessage(subtype="success", duration_ms=100, duration_api_ms=50,
                                      is_error=False, num_turns=1, session_id=session_id)
                yield msg
                yield result
            
            mock_query.return_value = mock_generator("session-A")
            await agent.execute_task("Task 1")
            session_ids.append(agent.session_id)
            
            mock_query.return_value = mock_generator("session-B")
            await agent.execute_task("Task 2")
            session_ids.append(agent.session_id)
            
            assert "session-A" in session_ids
            assert "session-B" in session_ids


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests that require actual SDK (marked for manual run)."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_full_interactive_session(self, agent_config):
        """Test complete interactive session with SDK.
        
        Run with: pytest -m integration
        """
        async with SEOAgent(agent_config) as agent:
            response1 = await agent.chat("My name is TestUser")
            assert response1 is not None
            assert len(response1) > 0
            
            response2 = await agent.chat("What is my name?")
            assert response2 is not None
    
    @pytest.mark.integration
    @pytest.mark.asyncio  
    async def test_skill_invocation(self, agent_config):
        """Test that skills are properly invoked.
        
        Run with: pytest -m integration
        """
        async with SEOAgent(agent_config) as agent:
            result = await agent.execute_task("What SEO skills are available?")
            assert result is not None


# ============================================================================
# EDGE CASES
# ============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    @pytest.mark.asyncio
    async def test_execute_task_empty_prompt(self, agent):
        """Test handling of empty prompt.
        
        Properly mocks async generator for query.
        """
        with patch('agent.seo_agent.query') as mock_query:
            from claude_agent_sdk.types import ResultMessage
            
            # Must be an async generator, not a regular iterator
            async def mock_gen():
                yield ResultMessage(subtype="success", duration_ms=100, duration_api_ms=50,
                             is_error=False, num_turns=1, session_id="s1")
            
            mock_query.return_value = mock_gen()
            
            result = await agent.execute_task("")
            assert result == ""
    
    def test_config_defaults(self):
        """Test AgentConfig default values."""
        config = AgentConfig()
        
        assert config.model == "sonnet"
        assert config.permission_mode == "acceptEdits"
        assert "Skill" in config.allowed_tools
        assert "project" in config.setting_sources
    
    def test_config_validation(self, tmp_path):
        """Test config validates CLI path."""
        config = AgentConfig(cwd=str(tmp_path))
        
        assert config is not None


# ============================================================================
# TEST 6: AGENT CONFIG — NO MCP SERVERS BY DEFAULT
# ============================================================================

class TestAgentConfigNoMcpServersByDefault:
    """Test that AgentConfig has no MCP servers by default (Webflow removed)."""

    def test_agent_config_has_no_mcp_servers_by_default(self):
        """AgentConfig has no MCP servers unless google_docs_config is provided."""
        config = AgentConfig()
        assert config.mcp_servers == {}

    def test_agent_config_from_env_no_mcp_servers(self, monkeypatch):
        """AgentConfig.from_env without any integration env vars has empty mcp_servers."""
        monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("GOOGLE_DOCS_CREDENTIALS_PATH", raising=False)
        monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        config = AgentConfig.from_env()
        assert config.mcp_servers == {}

    def test_agent_config_site_url_from_env(self, monkeypatch):
        """AgentConfig reads TARGET_SITE_URL from environment."""
        monkeypatch.setenv("TARGET_SITE_URL", "https://my-demo-site.example.com")
        config = AgentConfig.from_env()
        assert config.site_url == "https://my-demo-site.example.com"

    def test_agent_config_site_name_from_env(self, monkeypatch):
        """AgentConfig reads TARGET_SITE_NAME from environment."""
        monkeypatch.setenv("TARGET_SITE_NAME", "Demo Portfolio Site")
        config = AgentConfig.from_env()
        assert config.site_name == "Demo Portfolio Site"

    def test_agent_config_site_url_default(self, monkeypatch):
        """AgentConfig uses 'https://example.com' default when env var not set."""
        monkeypatch.delenv("TARGET_SITE_URL", raising=False)
        config = AgentConfig.from_env()
        assert config.site_url == "https://example.com"

    def test_agent_config_site_name_default(self, monkeypatch):
        """AgentConfig uses 'My Site' default when env var not set."""
        monkeypatch.delenv("TARGET_SITE_NAME", raising=False)
        config = AgentConfig.from_env()
        assert config.site_name == "My Site"


# ============================================================================
# RUN CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
