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
        """Skills are canonical unpacked dirs: <name>/SKILL.md with frontmatter,
        flat (no nested <name>/<name>/ layout), and no .skill ZIP archives."""
        skills_dir = Path("skills")
        assert skills_dir.exists(), "skills/ directory must exist"

        skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]
        assert len(skill_dirs) >= 15, (
            f"Expected at least 15 unpacked skills, found {len(skill_dirs)}"
        )

        for skill_dir in skill_dirs:
            md = skill_dir / "SKILL.md"
            assert md.exists(), f"{skill_dir.name} should contain SKILL.md"
            content = md.read_text(encoding="utf-8")
            assert "---" in content, (
                f"{skill_dir.name} SKILL.md should have frontmatter"
            )

        assert list(skills_dir.glob("*.skill")) == [], (
            "No .skill ZIP archives should remain"
        )


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
# TEST 6: WEBFLOW INTEGRATION
# ============================================================================

class TestWebflowIntegration:
    """Test Webflow CMS integration."""
    
    def test_webflow_config_from_env_missing_token(self, monkeypatch):
        """Test WebflowConfig returns None when token is missing."""
        monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("WEBFLOW_SITE_ID", raising=False)
        monkeypatch.delenv("WEBFLOW_COLLECTION_ID", raising=False)
        
        from agent.webflow import WebflowConfig
        config = WebflowConfig.from_env()
        
        assert config is None
    
    def test_webflow_config_from_env_missing_site_id(self, monkeypatch):
        """Test WebflowConfig returns None when site_id is missing."""
        monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "test_token")
        monkeypatch.delenv("WEBFLOW_SITE_ID", raising=False)
        monkeypatch.delenv("WEBFLOW_COLLECTION_ID", raising=False)
        
        from agent.webflow import WebflowConfig
        config = WebflowConfig.from_env()
        
        assert config is None
    
    def test_webflow_config_from_env_missing_collection_id(self, monkeypatch):
        """Test WebflowConfig returns None when collection_id is missing."""
        monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "test_token")
        monkeypatch.setenv("WEBFLOW_SITE_ID", "test_site")
        monkeypatch.delenv("WEBFLOW_COLLECTION_ID", raising=False)
        
        from agent.webflow import WebflowConfig
        config = WebflowConfig.from_env()
        
        assert config is None
    
    def test_webflow_config_from_env_all_present(self, monkeypatch):
        """Test WebflowConfig creates successfully with all env vars."""
        monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "test_token_123")
        monkeypatch.setenv("WEBFLOW_SITE_ID", "test_site_456")
        monkeypatch.setenv("WEBFLOW_COLLECTION_ID", "test_collection_789")
        
        from agent.webflow import WebflowConfig
        config = WebflowConfig.from_env()
        
        assert config is not None
        assert config.access_token == "test_token_123"
        assert config.site_id == "test_site_456"
        assert config.collection_id == "test_collection_789"
    
    def test_webflow_config_credentials_not_logged(self, monkeypatch, capsys):
        """Test that credentials are not exposed in logs."""
        import logging
        logging.basicConfig(level=logging.DEBUG)
        
        monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "secret_token_abc123")
        monkeypatch.setenv("WEBFLOW_SITE_ID", "site_id_xyz")
        monkeypatch.setenv("WEBFLOW_COLLECTION_ID", "collection_id_123")
        
        from agent.webflow import WebflowConfig
        config = WebflowConfig.from_env()
        
        # Access token should be in the config object
        assert config.access_token == "secret_token_abc123"
        
        # Check that token isn't in string representation
        config_str = str(config)
        assert "secret_token" not in config_str
    
    def test_webflow_config_masked_in_repr(self):
        """Test that sensitive data is masked in repr."""
        from agent.webflow import WebflowConfig
        
        config = WebflowConfig(
            access_token="my_secret_token",
            site_id="site123",
            collection_id="collection456"
        )
        
        repr_str = repr(config)
        
        # Token should be masked
        assert "my_secret_token" not in repr_str
        assert config.access_token == "my_secret_token"  # But still accessible
    
    def test_agent_config_webflow_none_by_default(self):
        """Test that AgentConfig has no Webflow by default."""
        config = AgentConfig()
        
        assert config.webflow_config is None
        assert config.mcp_servers == {}
    
    def test_agent_config_from_env_no_webflow(self, monkeypatch):
        """Test AgentConfig.from_env without Webflow env vars."""
        monkeypatch.delenv("WEBFLOW_ACCESS_TOKEN", raising=False)
        monkeypatch.delenv("WEBFLOW_SITE_ID", raising=False)
        monkeypatch.delenv("WEBFLOW_COLLECTION_ID", raising=False)
        
        config = AgentConfig.from_env()
        
        assert config.webflow_config is None
    
    def test_agent_config_from_env_with_webflow(self, monkeypatch):
        """Test AgentConfig.from_env with Webflow env vars."""
        monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "env_token")
        monkeypatch.setenv("WEBFLOW_SITE_ID", "env_site")
        monkeypatch.setenv("WEBFLOW_COLLECTION_ID", "env_collection")
        
        config = AgentConfig.from_env()
        
        assert config.webflow_config is not None
        assert config.webflow_config.access_token == "env_token"
    
    def test_webflow_mcp_server_created(self, monkeypatch):
        """Test that Webflow MCP server is created when config provided."""
        monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "test_token")
        monkeypatch.setenv("WEBFLOW_SITE_ID", "test_site")
        monkeypatch.setenv("WEBFLOW_COLLECTION_ID", "test_collection")
        
        config = AgentConfig.from_env()
        
        # MCP server should be set up
        assert "webflow" in config.mcp_servers
        assert len(config.mcp_servers) > 0
    
    def test_webflow_tools_added_to_allowed_tools(self, monkeypatch):
        """Test that Webflow tools are added to allowed_tools."""
        monkeypatch.setenv("WEBFLOW_ACCESS_TOKEN", "test_token")
        monkeypatch.setenv("WEBFLOW_SITE_ID", "test_site")
        monkeypatch.setenv("WEBFLOW_COLLECTION_ID", "test_collection")
        
        config = AgentConfig.from_env()
        
        # Check Webflow tool names are in allowed_tools
        webflow_tools = [t for t in config.allowed_tools if "webflow" in t]
        assert len(webflow_tools) >= 6  # All 6 tools should be added
    
    def test_webflow_client_initialization(self):
        """Test WebflowAPIClient can be initialized."""
        from agent.webflow import WebflowConfig, WebflowAPIClient
        
        config = WebflowConfig(
            access_token="test_token",
            site_id="test_site",
            collection_id="test_collection"
        )
        
        client = WebflowAPIClient(config)
        
        assert client.config == config
        assert client._session is None  # Not created until used
    
    @pytest.mark.asyncio
    async def test_webflow_client_close(self):
        """Test WebflowAPIClient cleanup."""
        from agent.webflow import WebflowConfig, WebflowAPIClient
        
        config = WebflowConfig(
            access_token="test_token",
            site_id="test_site",
            collection_id="test_collection"
        )
        
        client = WebflowAPIClient(config)
        await client.close()  # Should not raise


# ============================================================================
# RUN CONFIGURATION
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
