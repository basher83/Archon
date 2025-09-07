"""
Agents module for PydanticAI-powered agents in the Archon system.

This module contains various specialized agents for different tasks:
- DocumentAgent: Processes and validates project documentation
- RAGAgent: Conversational search and retrieval
- TaskAgent: Intelligent task orchestration and project management ✅
- PlanningAgent: Generates feature plans and technical specifications (planned)
- ERDAgent: Creates entity relationship diagrams (planned)

All agents are built using PydanticAI for type safety and structured outputs.
"""

from .base_agent import BaseAgent
from .document_agent import DocumentAgent
from .rag_agent import RagAgent
from .task_agent import TaskAgent

__all__ = ["BaseAgent", "DocumentAgent", "RagAgent", "TaskAgent"]
