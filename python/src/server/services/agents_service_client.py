"""
Agents Service Client - HTTP client for calling the agents service

This client allows the server to call agents running in the separate agents container
instead of trying to import them directly.
"""

import json
import logging
from typing import Any, Dict, Optional

import httpx

from ..config.service_discovery import get_agents_url

logger = logging.getLogger(__name__)


class AgentsServiceClient:
    """HTTP client for calling agents service."""

    def __init__(self):
        self.agents_url = get_agents_url()
        self.timeout = 120.0  # 2 minutes for agent operations
        logger.info(f"AgentsServiceClient initialized with URL: {self.agents_url}")

    async def call_document_agent(
        self,
        prompt: str,
        project_id: str,
        user_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call the document agent via HTTP.

        Args:
            prompt: The prompt for the document agent
            project_id: Project ID for context
            user_id: User ID for context
            context: Additional context

        Returns:
            Dict with agent response
        """
        try:
            request_data = {
                "agent_type": "document",
                "prompt": prompt,
                "context": {
                    "project_id": project_id,
                    "user_id": user_id,
                    **(context or {}),
                },
            }

            logger.info(f"Calling document agent: {prompt[:100]}...")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.agents_url}/agents/run",
                    json=request_data,
                    headers={"Content-Type": "application/json"},
                )
                
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"Document agent response: success={result.get('success')}")
                return result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling document agent: {e}")
            return {
                "success": False,
                "error": f"HTTP error: {str(e)}",
                "result": None,
            }
        except Exception as e:
            logger.error(f"Error calling document agent: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "result": None,
            }

    async def call_rag_agent(
        self,
        prompt: str,
        project_id: Optional[str] = None,
        source_filter: Optional[str] = None,
        match_count: int = 5,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Call the RAG agent via HTTP.

        Args:
            prompt: The prompt for the RAG agent
            project_id: Project ID for context
            source_filter: Source domain filter
            match_count: Maximum results to return
            context: Additional context

        Returns:
            Dict with agent response
        """
        try:
            request_data = {
                "agent_type": "rag",
                "prompt": prompt,
                "context": {
                    "project_id": project_id,
                    "source_filter": source_filter,
                    "match_count": match_count,
                    **(context or {}),
                },
            }

            logger.info(f"Calling RAG agent: {prompt[:100]}...")
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.agents_url}/agents/run",
                    json=request_data,
                    headers={"Content-Type": "application/json"},
                )
                
                response.raise_for_status()
                result = response.json()
                
                logger.info(f"RAG agent response: success={result.get('success')}")
                return result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error calling RAG agent: {e}")
            return {
                "success": False,
                "error": f"HTTP error: {str(e)}",
                "result": None,
            }
        except Exception as e:
            logger.error(f"Error calling RAG agent: {e}")
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "result": None,
            }

    async def health_check(self) -> Dict[str, Any]:
        """
        Check if the agents service is healthy.

        Returns:
            Dict with health status
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.agents_url}/health")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Agents service health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
            }


# Global instance
agents_client = AgentsServiceClient()
