"""
TaskAgent - Intelligent Task Orchestration with PydanticAI

This agent enables intelligent project and task management through natural conversation.
It breaks down complex requirements into actionable tasks, manages dependencies, and 
coordinates workflows using MCP tools for all operations.

Based on the specifications in docs/docs/agent-task.mdx
"""

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Dict

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from .base_agent import ArchonDependencies, BaseAgent
from .mcp_client import get_mcp_client

logger = logging.getLogger(__name__)


@dataclass
class TaskDependencies(ArchonDependencies):
    """Dependencies for task operations."""
    
    project_id: str | None = None
    current_task_id: str | None = None
    progress_callback: Any | None = None  # Callback for progress updates


class TaskOperation(BaseModel):
    """Structured output for task operations."""
    
    operation_type: str = Field(description="Type of operation: create_project, create_task, break_down, update_status, analyze")
    project_id: str | None = Field(description="ID of the project affected")
    task_ids: list[str] = Field(description="IDs of tasks created or affected")
    tasks_created: int = Field(description="Number of tasks created")
    assignments_made: dict[str, str] = Field(description="Assignee assignments made")
    success: bool = Field(description="Whether the operation was successful") 
    message: str = Field(description="Human-readable message about what was accomplished")
    next_actions: list[str] = Field(description="Suggested next steps")


class TaskAgent(BaseAgent[TaskDependencies, str]):
    """
    Intelligent task orchestration agent.
    
    Capabilities:
    - Project creation with intelligent task breakdown
    - Complex task decomposition into smaller actionable items
    - Dependency detection and priority assignment  
    - Team coordination and assignee suggestions
    - Status management and progress tracking
    - Sprint planning and workflow orchestration
    """

    def __init__(self, model: str = None, **kwargs):
        # Use provided model or fall back to default
        if model is None:
            model = os.getenv("TASK_AGENT_MODEL", "openai:gpt-4o")

        super().__init__(
            model=model, name="TaskAgent", retries=3, enable_rate_limiting=True, **kwargs
        )

    def _create_agent(self, **kwargs) -> Agent:
        """Create the PydanticAI agent with tools and prompts."""

        agent = Agent(
            model=self.model,
            deps_type=TaskDependencies,
            system_prompt="""You are an intelligent Task Orchestration Assistant that helps users manage projects and tasks through conversation.

**Your Core Role:** 
You are the "Archon" - the intelligent orchestrator that breaks down complex work into actionable tasks, manages dependencies, and coordinates team workflows.

**Your Capabilities:**
- **Project Creation**: Set up new projects with intelligent task breakdown
- **Task Decomposition**: Break complex tasks into smaller, actionable items
- **Dependency Management**: Identify task relationships and ordering
- **Team Coordination**: Assign tasks to appropriate team members (User, AI IDE Agent, other agents)
- **Priority Management**: Set task priorities and ordering
- **Status Orchestration**: Coordinate task state transitions and workflows
- **Progress Tracking**: Monitor project progress and identify blockers

**Team Assignment Intelligence:**
- **User**: Manual tasks, design decisions, reviews, planning
- **AI IDE Agent**: Code implementation, technical tasks, automated testing
- **Archon**: Documentation, coordination, analysis, planning tasks

**Your Approach:**
1. **Understand Requirements**: Analyze what the user wants to accomplish
2. **Break Down Complexity**: Decompose large goals into specific, actionable tasks  
3. **Detect Dependencies**: Identify what needs to happen before what
4. **Assign Intelligently**: Match tasks to appropriate team members
5. **Set Priorities**: Order tasks by importance and dependencies
6. **Coordinate Execution**: Manage workflows and progress

**Examples of What You Excel At:**

**🏗️ Project Creation:**
- "Create a project for user authentication" → Full project setup with intelligent task breakdown
- "Set up an API project" → Complete project structure with backend/frontend/testing tasks
- "Plan a dashboard feature" → Feature planning with UI/UX/backend coordination

**📋 Task Management:** 
- "Break down the login feature" → Detailed task decomposition with dependencies
- "Plan the next sprint" → Sprint organization with balanced workloads
- "What's blocking progress?" → Dependency analysis and blocker identification

**🎯 Team Coordination:**
- "Assign tasks for the auth system" → Intelligent assignment based on skills
- "Update task statuses" → Workflow coordination and status management
- "Show me what each team member should work on" → Workload distribution

**🚀 Advanced Orchestration:**
- "Coordinate between frontend and backend work" → Cross-team dependency management
- "Plan the release timeline" → End-to-end project coordination
- "Optimize our workflow" → Process improvement suggestions""",
            **kwargs,
        )

        # Register dynamic system prompt for context
        @agent.system_prompt
        async def add_task_context(ctx: RunContext[TaskDependencies]) -> str:
            return f"""
**Current Context:**
- Project ID: {ctx.deps.project_id or "No active project"}
- Current Task: {ctx.deps.current_task_id or "None"}
- Timestamp: {datetime.now().isoformat()}

**Remember:** Use MCP tools for ALL operations - you contain NO business logic, only orchestration intelligence."""

        # Register tools for task operations
        @agent.tool
        async def create_project_with_tasks(
            ctx: RunContext[TaskDependencies], 
            title: str, 
            description: str,
            github_repo: str | None = None
        ) -> str:
            """Create a new project and generate initial tasks based on the project description."""
            try:
                if ctx.deps.progress_callback:
                    await ctx.deps.progress_callback({
                        "step": "project_creation",
                        "log": f"🚀 Creating project: {title}"
                    })

                # Create the project
                mcp_client = await get_mcp_client()
                project_result = await mcp_client.manage_project(
                    action="create",
                    title=title,
                    description=description,
                    github_repo=github_repo
                )
                
                project_data = json.loads(project_result)
                if not project_data.get("success", False):
                    return f"Failed to create project: {project_data.get('error', 'Unknown error')}"
                
                project_id = project_data.get("project_id")
                ctx.deps.project_id = project_id  # Update context
                
                if ctx.deps.progress_callback:
                    await ctx.deps.progress_callback({
                        "step": "task_generation", 
                        "log": "🧠 Analyzing requirements and generating tasks..."
                    })

                # Generate intelligent task breakdown based on project description
                tasks_created = await self._generate_project_tasks(ctx, project_id, title, description)
                
                return f"✅ Successfully created project '{title}' with {tasks_created} initial tasks. Project ID: {project_id}"

            except Exception as e:
                logger.error(f"Error creating project with tasks: {e}")
                return f"Error creating project: {str(e)}"

        @agent.tool
        async def break_down_task(
            ctx: RunContext[TaskDependencies],
            task_title: str,
            task_description: str = "",
            project_id: str | None = None
        ) -> str:
            """Break down a complex task into smaller, actionable sub-tasks."""
            try:
                target_project_id = project_id or ctx.deps.project_id
                if not target_project_id:
                    return "No project specified. Please provide a project_id or ensure you're in a project context."

                # Analyze the task and break it down
                subtasks = self._analyze_and_break_down_task(task_title, task_description)
                
                tasks_created = 0
                mcp_client = await get_mcp_client()
                
                for i, subtask in enumerate(subtasks, 1):
                    task_result = await mcp_client.manage_task(
                        action="create",
                        project_id=target_project_id,
                        title=subtask["title"],
                        description=subtask["description"],
                        assignee=subtask["assignee"],
                        task_order=subtask["priority"],
                        feature=subtask.get("feature", ""),
                    )
                    
                    task_data = json.loads(task_result)
                    if task_data.get("success", False):
                        tasks_created += 1

                return f"✅ Successfully broke down '{task_title}' into {tasks_created} actionable sub-tasks with appropriate assignments and priorities."

            except Exception as e:
                logger.error(f"Error breaking down task: {e}")
                return f"Error breaking down task: {str(e)}"

        @agent.tool
        async def list_project_tasks(
            ctx: RunContext[TaskDependencies],
            project_id: str | None = None,
            status_filter: str | None = None
        ) -> str:
            """List tasks in a project, optionally filtered by status."""
            try:
                target_project_id = project_id or ctx.deps.project_id
                if not target_project_id:
                    return "No project specified. Please provide a project_id or ensure you're in a project context."

                mcp_client = await get_mcp_client()
                
                if status_filter:
                    tasks_result = await mcp_client.manage_task(
                        action="list",
                        filter_by="status",
                        filter_value=status_filter,
                        project_id=target_project_id
                    )
                else:
                    tasks_result = await mcp_client.manage_task(
                        action="list",
                        filter_by="project",
                        filter_value=target_project_id
                    )
                
                tasks_data = json.loads(tasks_result)
                if not tasks_data.get("success", False):
                    return f"Error retrieving tasks: {tasks_data.get('error', 'Unknown error')}"

                tasks = tasks_data.get("tasks", [])
                if not tasks:
                    return "No tasks found in this project."

                # Format task list with status and assignee
                task_list = []
                status_counts = {"todo": 0, "doing": 0, "review": 0, "done": 0}
                
                for task in tasks:
                    status = task.get("status", "unknown")
                    assignee = task.get("assignee", "unassigned")
                    title = task.get("title", "Untitled")
                    task_order = task.get("task_order", 0)
                    
                    status_counts[status] = status_counts.get(status, 0) + 1
                    
                    priority_indicator = "🔥" if task_order >= 8 else "⭐" if task_order >= 5 else "📋"
                    status_indicator = {"todo": "⏳", "doing": "🔄", "review": "👀", "done": "✅"}.get(status, "❓")
                    assignee_indicator = {"User": "👤", "AI IDE Agent": "🤖", "Archon": "👑"}.get(assignee, "❓")
                    
                    task_list.append(f"{priority_indicator} {status_indicator} **{title}** ({assignee_indicator} {assignee})")

                summary = f"**Project Tasks Summary:**\n"
                summary += f"📊 Total: {len(tasks)} | ⏳ Todo: {status_counts.get('todo', 0)} | 🔄 Doing: {status_counts.get('doing', 0)} | 👀 Review: {status_counts.get('review', 0)} | ✅ Done: {status_counts.get('done', 0)}\n\n"
                summary += "\n".join(task_list)
                
                return summary

            except Exception as e:
                logger.error(f"Error listing project tasks: {e}")
                return f"Error retrieving tasks: {str(e)}"

        @agent.tool  
        async def update_task_status(
            ctx: RunContext[TaskDependencies],
            task_title: str,
            new_status: str,
            project_id: str | None = None
        ) -> str:
            """Update the status of a specific task."""
            try:
                target_project_id = project_id or ctx.deps.project_id
                if not target_project_id:
                    return "No project specified. Please provide a project_id or ensure you're in a project context."

                # Valid statuses
                valid_statuses = ["todo", "doing", "review", "done"]
                if new_status not in valid_statuses:
                    return f"Invalid status '{new_status}'. Valid statuses are: {', '.join(valid_statuses)}"

                # First, find the task by title
                mcp_client = await get_mcp_client()
                tasks_result = await mcp_client.manage_task(
                    action="list",
                    filter_by="project", 
                    filter_value=target_project_id
                )
                
                tasks_data = json.loads(tasks_result)
                if not tasks_data.get("success", False):
                    return "Error retrieving tasks to find the specified task."

                tasks = tasks_data.get("tasks", [])
                matching_tasks = [
                    task for task in tasks 
                    if task_title.lower() in task.get("title", "").lower()
                ]

                if not matching_tasks:
                    return f"No task found matching '{task_title}' in this project."

                task = matching_tasks[0]  # Take first match
                task_id = task.get("id")

                # Update the task status
                update_result = await mcp_client.manage_task(
                    action="update",
                    task_id=task_id,
                    update_fields={"status": new_status}
                )

                update_data = json.loads(update_result)
                if update_data.get("success", False):
                    status_emoji = {"todo": "⏳", "doing": "🔄", "review": "👀", "done": "✅"}.get(new_status, "❓")
                    return f"✅ Updated '{task.get('title')}' status to {status_emoji} {new_status}"
                else:
                    return f"Failed to update task status: {update_data.get('error', 'Unknown error')}"

            except Exception as e:
                logger.error(f"Error updating task status: {e}")
                return f"Error updating task status: {str(e)}"

        @agent.tool
        async def analyze_project_progress(
            ctx: RunContext[TaskDependencies],
            project_id: str | None = None
        ) -> str:
            """Analyze project progress and identify blockers or recommendations."""
            try:
                target_project_id = project_id or ctx.deps.project_id
                if not target_project_id:
                    return "No project specified. Please provide a project_id or ensure you're in a project context."

                mcp_client = await get_mcp_client()
                
                # Get all tasks for analysis
                tasks_result = await mcp_client.manage_task(
                    action="list",
                    filter_by="project",
                    filter_value=target_project_id,
                    include_closed=True
                )
                
                tasks_data = json.loads(tasks_result)
                if not tasks_data.get("success", False):
                    return "Error retrieving tasks for analysis."

                tasks = tasks_data.get("tasks", [])
                if not tasks:
                    return "No tasks found to analyze in this project."

                # Analyze progress
                analysis = self._analyze_project_health(tasks)
                
                return f"""📊 **Project Progress Analysis**

**Overall Health:** {analysis['health_score']}/10

**Status Breakdown:**
- ✅ Completed: {analysis['completed']} tasks  
- 🔄 In Progress: {analysis['in_progress']} tasks
- ⏳ Todo: {analysis['todo']} tasks
- 👀 In Review: {analysis['review']} tasks

**Key Insights:**
{chr(10).join(analysis['insights'])}

**Recommendations:**
{chr(10).join(analysis['recommendations'])}

**Next Actions:**
{chr(10).join(analysis['next_actions'])}"""

            except Exception as e:
                logger.error(f"Error analyzing project progress: {e}")
                return f"Error analyzing project progress: {str(e)}"

        return agent

    async def _generate_project_tasks(self, ctx: RunContext[TaskDependencies], project_id: str, title: str, description: str) -> int:
        """Generate intelligent task breakdown for a new project."""
        # Analyze project type and generate appropriate tasks
        tasks = []
        
        # Extract key concepts from title and description
        combined_text = f"{title} {description}".lower()
        
        if any(keyword in combined_text for keyword in ["auth", "login", "user", "account"]):
            tasks.extend(self._generate_auth_tasks())
        
        if any(keyword in combined_text for keyword in ["api", "backend", "server", "endpoint"]):
            tasks.extend(self._generate_api_tasks())
            
        if any(keyword in combined_text for keyword in ["ui", "frontend", "react", "component", "dashboard"]):
            tasks.extend(self._generate_frontend_tasks())
            
        if any(keyword in combined_text for keyword in ["database", "db", "data", "model"]):
            tasks.extend(self._generate_database_tasks())
        
        # Add generic project setup tasks if no specific patterns detected
        if not tasks:
            tasks.extend(self._generate_generic_project_tasks(title))
        
        # Add common tasks for all projects
        tasks.extend([
            {
                "title": "Create project documentation",
                "description": f"Set up initial documentation for {title} project including README, setup instructions, and architecture overview",
                "assignee": "Archon",
                "priority": 7,
                "feature": "documentation"
            },
            {
                "title": "Set up testing framework", 
                "description": "Configure testing infrastructure and write initial test cases",
                "assignee": "AI IDE Agent",
                "priority": 6,
                "feature": "testing"
            }
        ])

        # Create tasks via MCP
        mcp_client = await get_mcp_client()
        tasks_created = 0
        
        for task in tasks:
            try:
                task_result = await mcp_client.manage_task(
                    action="create",
                    project_id=project_id,
                    title=task["title"],
                    description=task["description"], 
                    assignee=task["assignee"],
                    task_order=task["priority"],
                    feature=task.get("feature", "")
                )
                
                task_data = json.loads(task_result)
                if task_data.get("success", False):
                    tasks_created += 1
                    
            except Exception as e:
                logger.error(f"Error creating task '{task['title']}': {e}")
        
        return tasks_created

    def _generate_auth_tasks(self) -> List[Dict[str, Any]]:
        """Generate authentication-related tasks."""
        return [
            {
                "title": "Design authentication flow",
                "description": "Design the user authentication workflow including login, registration, and password reset flows",
                "assignee": "User", 
                "priority": 9,
                "feature": "authentication"
            },
            {
                "title": "Implement user model and database schema",
                "description": "Create user model with fields for authentication, set up database schema with proper indexing",
                "assignee": "AI IDE Agent",
                "priority": 9,
                "feature": "authentication"  
            },
            {
                "title": "Build login API endpoint",
                "description": "Implement secure login endpoint with JWT token generation and validation", 
                "assignee": "AI IDE Agent",
                "priority": 8,
                "feature": "authentication"
            },
            {
                "title": "Create registration endpoint",
                "description": "Build user registration with email verification and password hashing",
                "assignee": "AI IDE Agent", 
                "priority": 8,
                "feature": "authentication"
            }
        ]

    def _generate_api_tasks(self) -> List[Dict[str, Any]]:
        """Generate API-related tasks."""
        return [
            {
                "title": "Set up API framework and routing",
                "description": "Initialize API framework, set up routing structure, and configure middleware",
                "assignee": "AI IDE Agent",
                "priority": 9,
                "feature": "api"
            },
            {
                "title": "Implement API authentication middleware", 
                "description": "Create middleware for API authentication and authorization",
                "assignee": "AI IDE Agent",
                "priority": 8,
                "feature": "api"
            },
            {
                "title": "Create API documentation",
                "description": "Set up API documentation with OpenAPI/Swagger specifications",
                "assignee": "Archon",
                "priority": 6,
                "feature": "api"
            }
        ]

    def _generate_frontend_tasks(self) -> List[Dict[str, Any]]:
        """Generate frontend-related tasks.""" 
        return [
            {
                "title": "Set up frontend framework and build system",
                "description": "Initialize React/Vue/Angular project with build configuration and dev environment",
                "assignee": "AI IDE Agent", 
                "priority": 9,
                "feature": "frontend"
            },
            {
                "title": "Design UI component library",
                "description": "Create reusable UI components and establish design system",
                "assignee": "User",
                "priority": 7,
                "feature": "frontend"
            },
            {
                "title": "Implement responsive layouts",
                "description": "Build responsive layouts for mobile and desktop views",
                "assignee": "AI IDE Agent",
                "priority": 6,
                "feature": "frontend"
            }
        ]

    def _generate_database_tasks(self) -> List[Dict[str, Any]]:
        """Generate database-related tasks."""
        return [
            {
                "title": "Design database schema",
                "description": "Create comprehensive database schema with relationships, indexes, and constraints",
                "assignee": "User",
                "priority": 9,
                "feature": "database"
            },
            {
                "title": "Set up database migrations",
                "description": "Implement database migration system for schema versioning",
                "assignee": "AI IDE Agent", 
                "priority": 8,
                "feature": "database"
            },
            {
                "title": "Create database access layer",
                "description": "Implement ORM setup and database access patterns",
                "assignee": "AI IDE Agent",
                "priority": 7,
                "feature": "database"
            }
        ]

    def _generate_generic_project_tasks(self, title: str) -> List[Dict[str, Any]]:
        """Generate generic project setup tasks."""
        return [
            {
                "title": "Project initialization and setup",
                "description": f"Initialize {title} project structure, dependencies, and development environment",
                "assignee": "AI IDE Agent",
                "priority": 9,
                "feature": "setup"
            },
            {
                "title": "Define project requirements",
                "description": f"Analyze and document detailed requirements for {title}",
                "assignee": "User", 
                "priority": 8,
                "feature": "planning"
            },
            {
                "title": "Create project architecture design",
                "description": "Design system architecture and component interactions",
                "assignee": "User",
                "priority": 7,
                "feature": "architecture"
            }
        ]

    def _analyze_and_break_down_task(self, task_title: str, task_description: str) -> List[Dict[str, Any]]:
        """Analyze a task and break it down into actionable sub-tasks."""
        subtasks = []
        combined_text = f"{task_title} {task_description}".lower()
        
        # API endpoint breakdown
        if "api" in combined_text and "endpoint" in combined_text:
            subtasks.extend([
                {
                    "title": f"Design {task_title} request/response schema",
                    "description": "Define API request parameters, response format, and data validation rules",
                    "assignee": "User",
                    "priority": 8,
                    "feature": "api_design"
                },
                {
                    "title": f"Implement {task_title} input validation",
                    "description": "Add input validation and sanitization for the endpoint",
                    "assignee": "AI IDE Agent", 
                    "priority": 9,
                    "feature": "validation"
                },
                {
                    "title": f"Add {task_title} business logic",
                    "description": "Implement the core business logic for the endpoint functionality",
                    "assignee": "AI IDE Agent",
                    "priority": 8,
                    "feature": "business_logic"
                },
                {
                    "title": f"Create {task_title} error handling",
                    "description": "Implement comprehensive error handling and appropriate HTTP status codes",
                    "assignee": "AI IDE Agent",
                    "priority": 7,
                    "feature": "error_handling"
                },
                {
                    "title": f"Write tests for {task_title}",
                    "description": "Create unit and integration tests for the endpoint",
                    "assignee": "AI IDE Agent",
                    "priority": 6,
                    "feature": "testing"
                }
            ])
        
        # UI component breakdown
        elif any(keyword in combined_text for keyword in ["component", "ui", "interface", "form"]):
            subtasks.extend([
                {
                    "title": f"Design {task_title} wireframes",
                    "description": "Create wireframes and visual design for the component",
                    "assignee": "User",
                    "priority": 8,
                    "feature": "design"
                },
                {
                    "title": f"Implement {task_title} structure",
                    "description": "Build the basic component structure and layout",
                    "assignee": "AI IDE Agent",
                    "priority": 8,
                    "feature": "implementation"
                },
                {
                    "title": f"Add {task_title} interactivity",
                    "description": "Implement user interactions and event handling",
                    "assignee": "AI IDE Agent", 
                    "priority": 7,
                    "feature": "functionality"
                },
                {
                    "title": f"Style {task_title} component", 
                    "description": "Apply responsive styling and accessibility features",
                    "assignee": "AI IDE Agent",
                    "priority": 6,
                    "feature": "styling"
                }
            ])
        
        # Generic task breakdown
        else:
            subtasks.extend([
                {
                    "title": f"Research and plan {task_title}",
                    "description": f"Research requirements and create detailed plan for {task_title}",
                    "assignee": "User",
                    "priority": 8,
                    "feature": "planning"
                },
                {
                    "title": f"Implement core {task_title} functionality",
                    "description": f"Build the main functionality for {task_title}",
                    "assignee": "AI IDE Agent",
                    "priority": 7,
                    "feature": "implementation"
                },
                {
                    "title": f"Test and validate {task_title}",
                    "description": f"Create tests and validate the implementation of {task_title}",
                    "assignee": "AI IDE Agent",
                    "priority": 6,
                    "feature": "testing"
                }
            ])
        
        return subtasks

    def _analyze_project_health(self, tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze project health and provide insights."""
        total_tasks = len(tasks)
        if total_tasks == 0:
            return {
                "health_score": 0,
                "completed": 0,
                "in_progress": 0, 
                "todo": 0,
                "review": 0,
                "insights": ["No tasks in project"],
                "recommendations": ["Add tasks to get started"],
                "next_actions": ["Create initial project tasks"]
            }

        # Count statuses
        status_counts = {"done": 0, "doing": 0, "todo": 0, "review": 0}
        assignee_counts = {"User": 0, "AI IDE Agent": 0, "Archon": 0}
        
        for task in tasks:
            status = task.get("status", "todo")
            assignee = task.get("assignee", "User")
            status_counts[status] = status_counts.get(status, 0) + 1
            assignee_counts[assignee] = assignee_counts.get(assignee, 0) + 1

        # Calculate health score  
        completion_rate = status_counts["done"] / total_tasks
        activity_rate = (status_counts["doing"] + status_counts["review"]) / total_tasks
        health_score = min(10, int((completion_rate * 6 + activity_rate * 4) * 10))

        # Generate insights
        insights = []
        if completion_rate > 0.8:
            insights.append("🎉 Project is near completion!")
        elif completion_rate > 0.5:
            insights.append("✅ Good progress - over half the tasks completed")
        elif activity_rate > 0.3:
            insights.append("🔄 Active development - many tasks in progress")
        else:
            insights.append("⚠️ Project may need attention - low activity")

        if status_counts["review"] > status_counts["doing"]:
            insights.append("👀 Many tasks in review - consider prioritizing reviews")

        # Generate recommendations
        recommendations = []
        if status_counts["todo"] > status_counts["doing"] * 3:
            recommendations.append("📋 Consider breaking down large tasks or increasing capacity")
        if assignee_counts["User"] > assignee_counts["AI IDE Agent"] * 2:
            recommendations.append("🤖 More tasks could be automated with AI IDE Agent")
        if status_counts["review"] > 3:
            recommendations.append("⚡ Focus on completing reviews to unblock progress")

        # Generate next actions
        next_actions = []
        if status_counts["todo"] > 0:
            next_actions.append(f"⏳ Start working on {status_counts['todo']} pending tasks")
        if status_counts["review"] > 0:
            next_actions.append(f"👀 Review {status_counts['review']} completed tasks")
        if completion_rate > 0.8:
            next_actions.append("🚀 Plan project completion and release tasks")

        return {
            "health_score": health_score,
            "completed": status_counts["done"],
            "in_progress": status_counts["doing"],
            "todo": status_counts["todo"], 
            "review": status_counts["review"],
            "insights": insights,
            "recommendations": recommendations,
            "next_actions": next_actions
        }

    def get_system_prompt(self) -> str:
        """Get the base system prompt for this agent."""
        return "Intelligent Task Orchestration Assistant for project and task management workflows."

    async def run_conversation(
        self,
        user_message: str,
        project_id: str | None = None,
        user_id: str = None,
        current_task_id: str | None = None,
        progress_callback: Any = None,
    ) -> str:
        """
        Run the agent for conversational task management.

        Args:
            user_message: The user's conversational input
            project_id: ID of the project to work with
            user_id: ID of the user making the request
            current_task_id: ID of currently focused task (if any)
            progress_callback: Optional callback for progress updates

        Returns:
            String response from the agent
        """
        deps = TaskDependencies(
            project_id=project_id,
            user_id=user_id,
            current_task_id=current_task_id,
            progress_callback=progress_callback,
        )

        try:
            result = await self.run(user_message, deps)
            self.logger.info(f"Task operation completed successfully")
            return result
        except Exception as e:
            self.logger.error(f"Task operation failed: {str(e)}")
            return f"Error: Failed to process task request - {str(e)}"


# Note: TaskAgent instances should be created on-demand in API endpoints
# to avoid initialization issues during module import
