#!/usr/bin/env python3
"""
Main entry point for the SEO Autonomous Agent.

This script provides a CLI interface to the SEO agent, supporting
both command-line task execution and interactive mode.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from agent import SEOAgent, AgentConfig


async def main():
    """Main function to run the SEO agent."""
    print("=" * 60)
    print("SEO Autonomous Agent")
    print("=" * 60)
    print("\nUsing Claude Code OAuth (no API key required)")
    print()
    
    # Create agent configuration (auto-detects Webflow from env vars)
    config = AgentConfig.from_env()
    # Ensure working directory is set to project root
    config.cwd = Path(__file__).parent
    
    # Check for command line arguments
    if len(sys.argv) > 1:
        # Execute task from command line argument
        task = " ".join(sys.argv[1:])
        print(f"\nExecuting task: {task}")
        print("-" * 40)
        
        result = await SEOAgent.create_and_run(task, config)
        print(result)
    else:
        # Interactive mode
        print("\nEntering interactive mode...")
        print("Type 'exit' to quit, 'interrupt' to stop current task\n")
        
        async with SEOAgent(config) as agent:
            print("Agent connected! Ready for tasks.\n")
            
            while True:
                try:
                    user_input = input("\nYou: ").strip()
                    
                    if user_input.lower() in ["exit", "quit", "q"]:
                        print("Goodbye!")
                        break
                    elif user_input.lower() in ["interrupt", "stop"]:
                        await agent.interrupt()
                        print("Task interrupted.")
                        continue
                    elif not user_input:
                        continue
                    
                    response = await agent.chat(user_input)
                    print(f"\nClaude: {response}")
                    
                except KeyboardInterrupt:
                    print("\nGoodbye!")
                    break
                except Exception as e:
                    print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
