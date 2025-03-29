# backend/orchestrator/__init__.py

"""
Orchestrator package for the Multi-Agent Acquisition System (MAAS).

This package provides orchestration functionality for managing and coordinating
multiple AI agents, including compliance, evaluation, and market research agents.
"""

import logging
import asyncio
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Export key classes and functions for the orchestrator package
from backend.azure_agents.orchestrator import (
    Orchestrator,
    ComplianceResult,
    EvaluationResult,
    MarketResult,
    OrchestratorResult,
    ProposalContext
)

from backend.azure_agents.workflows import (
    WorkflowManager,
    WorkflowType
)

from backend.azure_agents.compliance_agent import ComplianceAgent
from backend.azure_agents.evaluation_agent import EvaluationAgent
from backend.azure_agents.market_agent import MarketAgent

# Define orchestrator workflow status
class WorkflowStatus(str, Enum):
    """Enum for tracking the status of a workflow."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMEOUT = "timeout"

# Define workflow task result model
@dataclass
class WorkflowTaskResult:
    """Represents the result of a workflow task."""
    task_id: str
    agent_type: str
    status: str
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    processing_time_ms: Optional[float] = None

# Define workflow registry for tracking and managing workflows
class WorkflowRegistry:
    """Registry for tracking and managing workflows."""
    
    def __init__(self):
        """Initialize the workflow registry."""
        self._workflows = {}
        self._lock = asyncio.Lock()
    
    async def register_workflow(self, workflow_id: str, workflow_type: WorkflowType) -> None:
        """
        Register a new workflow in the registry.
        
        Args:
            workflow_id: Unique identifier for the workflow
            workflow_type: Type of workflow
        """
        async with self._lock:
            self._workflows[workflow_id] = {
                "id": workflow_id,
                "type": workflow_type,
                "status": WorkflowStatus.PENDING,
                "tasks": [],
                "created_at": asyncio.get_event_loop().time(),
                "updated_at": asyncio.get_event_loop().time(),
                "completed_at": None,
                "results": {}
            }
    
    async def update_workflow_status(self, workflow_id: str, status: WorkflowStatus) -> None:
        """
        Update the status of a workflow.
        
        Args:
            workflow_id: Unique identifier for the workflow
            status: New status for the workflow
        """
        async with self._lock:
            if workflow_id in self._workflows:
                self._workflows[workflow_id]["status"] = status
                self._workflows[workflow_id]["updated_at"] = asyncio.get_event_loop().time()
                
                if status == WorkflowStatus.COMPLETED or status == WorkflowStatus.FAILED:
                    self._workflows[workflow_id]["completed_at"] = asyncio.get_event_loop().time()
    
    async def add_task_result(self, workflow_id: str, task_result: WorkflowTaskResult) -> None:
        """
        Add a task result to a workflow.
        
        Args:
            workflow_id: Unique identifier for the workflow
            task_result: Result of the task
        """
        async with self._lock:
            if workflow_id in self._workflows:
                self._workflows[workflow_id]["tasks"].append(task_result)
                self._workflows[workflow_id]["updated_at"] = asyncio.get_event_loop().time()
                
                # Store the results by agent type
                if task_result.result:
                    self._workflows[workflow_id]["results"][task_result.agent_type] = task_result.result
    
    async def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a workflow by ID.
        
        Args:
            workflow_id: Unique identifier for the workflow
            
        Returns:
            Dict containing workflow details or None if not found
        """
        async with self._lock:
            return self._workflows.get(workflow_id)
    
    async def get_all_workflows(self) -> List[Dict[str, Any]]:
        """
        Get all workflows.
        
        Returns:
            List of dictionaries containing workflow details
        """
        async with self._lock:
            return list(self._workflows.values())
    
    async def cleanup_old_workflows(self, max_age_hours: int = 24) -> int:
        """
        Remove workflows older than specified hours.
        
        Args:
            max_age_hours: Maximum age in hours
            
        Returns:
            Number of workflows removed
        """
        now = asyncio.get_event_loop().time()
        max_age_seconds = max_age_hours * 3600
        removed_count = 0
        
        async with self._lock:
            to_remove = []
            
            for workflow_id, workflow in self._workflows.items():
                age = now - workflow["created_at"]
                
                if age > max_age_seconds:
                    to_remove.append(workflow_id)
            
            for workflow_id in to_remove:
                del self._workflows[workflow_id]
                removed_count += 1
        
        return removed_count

# Create a singleton registry instance
workflow_registry = WorkflowRegistry()

# Create a high-level orchestration manager
class OrchestrationManager:
    """
    High-level manager for orchestrating workflows and agents.
    
    This class provides a simplified interface for running workflows and
    managing agents within the system.
    """
    
    def __init__(self):
        """Initialize the orchestration manager."""
        # Create the base orchestrator
        self.orchestrator = Orchestrator()
        
        # Create the workflow manager
        self.workflow_manager = WorkflowManager(self.orchestrator)
        
        # Reference to the workflow registry
        self.registry = workflow_registry
    
    async def run_workflow(self, proposal_id: str, user_id: str, proposal_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Run a complete workflow for a proposal.
        
        Args:
            proposal_id: Unique identifier for the proposal
            user_id: ID of the user submitting the proposal
            proposal_data: Dictionary containing all proposal details
            
        Returns:
            Dictionary with results from all agents and final recommendation
        """
        try:
            # Determine workflow type
            workflow_type, _ = self.workflow_manager.determine_workflow_type(proposal_data)
            
            # Register the workflow
            await self.registry.register_workflow(proposal_id, workflow_type)
            
            # Update status to running
            await self.registry.update_workflow_status(proposal_id, WorkflowStatus.RUNNING)
            
            # Start timing
            start_time = asyncio.get_event_loop().time()
            
            # Run the workflow
            results = await self.workflow_manager.process_proposal(
                proposal_id=proposal_id,
                user_id=user_id,
                proposal_data=proposal_data
            )
            
            # Calculate processing time
            processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Add task results to registry
            for agent_type, result in results.items():
                if agent_type not in ["workflow", "recommendation"]:
                    task_result = WorkflowTaskResult(
                        task_id=f"{proposal_id}-{agent_type}",
                        agent_type=agent_type,
                        status="completed",
                        result=result,
                        processing_time_ms=processing_time_ms / len(results)  # Approximation
                    )
                    await self.registry.add_task_result(proposal_id, task_result)
            
            # Update workflow status to completed
            await self.registry.update_workflow_status(proposal_id, WorkflowStatus.COMPLETED)
            
            # Return the combined results
            return {
                "proposal_id": proposal_id,
                "compliance": results.get("compliance", {}),
                "evaluation": results.get("evaluation", {}),
                "market": results.get("market", {}),
                "recommendation": results.get("recommendation", ""),
                "processing_time_ms": processing_time_ms,
                "workflow_type": workflow_type
            }
        
        except Exception as e:
            logger.error(f"Error in workflow {proposal_id}: {str(e)}")
            
            # Update workflow status to failed
            await self.registry.update_workflow_status(proposal_id, WorkflowStatus.FAILED)
            
            # Create an error task result
            task_result = WorkflowTaskResult(
                task_id=f"{proposal_id}-error",
                agent_type="orchestrator",
                status="failed",
                error=str(e)
            )
            await self.registry.add_task_result(proposal_id, task_result)
            
            # Re-raise the exception
            raise

    async def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get the status of a workflow.
        
        Args:
            workflow_id: Unique identifier for the workflow
            
        Returns:
            Dictionary containing workflow status and details
        """
        workflow = await self.registry.get_workflow(workflow_id)
        
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        return {
            "id": workflow_id,
            "status": workflow["status"],
            "type": workflow["type"],
            "created_at": workflow["created_at"],
            "updated_at": workflow["updated_at"],
            "completed_at": workflow["completed_at"],
            "task_count": len(workflow["tasks"]),
            "results": {k: v for k, v in workflow["results"].items() if k != "recommendation"}
        }
    
    async def get_all_workflows(self) -> List[Dict[str, Any]]:
        """
        Get all workflows.
        
        Returns:
            List of dictionaries containing workflow details
        """
        workflows = await self.registry.get_all_workflows()
        
        # Format the responses
        return [
            {
                "id": w["id"],
                "status": w["status"],
                "type": w["type"],
                "created_at": w["created_at"],
                "updated_at": w["updated_at"],
                "completed_at": w["completed_at"],
                "task_count": len(w["tasks"])
            }
            for w in workflows
        ]
    
    async def cancel_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Cancel a running workflow.
        
        Args:
            workflow_id: Unique identifier for the workflow
            
        Returns:
            Dictionary containing the updated workflow status
        """
        workflow = await self.registry.get_workflow(workflow_id)
        
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if workflow["status"] != WorkflowStatus.RUNNING:
            raise ValueError(f"Cannot cancel workflow with status {workflow['status']}")
        
        # Update workflow status to canceled
        await self.registry.update_workflow_status(workflow_id, WorkflowStatus.CANCELED)
        
        # Return updated status
        return {
            "id": workflow_id,
            "status": WorkflowStatus.CANCELED,
            "message": f"Workflow {workflow_id} has been canceled"
        }
    
    async def cleanup_workflows(self, max_age_hours: int = 24) -> Dict[str, Any]:
        """
        Clean up old workflows.
        
        Args:
            max_age_hours: Maximum age in hours
            
        Returns:
            Dictionary containing the number of workflows removed
        """
        removed_count = await self.registry.cleanup_old_workflows(max_age_hours)
        
        return {
            "removed_count": removed_count,
            "message": f"Removed {removed_count} workflows older than {max_age_hours} hours"
        }

# Create a singleton instance
orchestration_manager = OrchestrationManager()

# Export the orchestration manager
__all__ = [
    'Orchestrator',
    'ComplianceResult',
    'EvaluationResult', 
    'MarketResult',
    'OrchestratorResult',
    'ProposalContext',
    'WorkflowManager',
    'WorkflowType',
    'WorkflowStatus',
    'WorkflowTaskResult',
    'WorkflowRegistry',
    'workflow_registry',
    'OrchestrationManager',
    'orchestration_manager'
]