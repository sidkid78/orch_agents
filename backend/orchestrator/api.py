# backend/orchestrator/api.py

"""
API routes for the orchestrator functionality.

This module provides FastAPI routes for interacting with the orchestration system,
including running workflows, checking workflow status, and managing agent executions.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
import asyncio
import logging
import time
from datetime import datetime

# Import orchestration components
from backend.orchestrator import (
    orchestration_manager,
    WorkflowStatus,
    WorkflowType
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])

# API models
class WorkflowRequest(BaseModel):
    """Model for requesting a workflow run."""
    proposal_id: str
    user_id: str
    proposal_data: Dict[str, Any]

class WorkflowResponse(BaseModel):
    """Model for workflow run response."""
    workflow_id: str
    status: str
    message: str

class WorkflowStatusResponse(BaseModel):
    """Model for workflow status response."""
    id: str
    status: str
    type: str
    created_at: float
    updated_at: float
    completed_at: Optional[float] = None
    task_count: int
    results: Optional[Dict[str, Any]] = None

class WorkflowsListResponse(BaseModel):
    """Model for listing workflows response."""
    workflows: List[WorkflowStatusResponse]
    count: int

class WorkflowCancelResponse(BaseModel):
    """Model for workflow cancellation response."""
    id: str
    status: str
    message: str

class WorkflowCleanupResponse(BaseModel):
    """Model for workflow cleanup response."""
    removed_count: int
    message: str

class WorkflowResultResponse(BaseModel):
    """Model for detailed workflow result response."""
    proposal_id: str
    workflow_type: str = Field(..., description="Type of workflow executed")
    processing_time_ms: float = Field(..., description="Total processing time in milliseconds")
    compliance: Dict[str, Any] = Field(..., description="Compliance agent results")
    evaluation: Dict[str, Any] = Field(..., description="Evaluation agent results")
    market: Dict[str, Any] = Field(..., description="Market agent results")
    recommendation: str = Field(..., description="Final recommendation")

# API routes
@router.post("/workflows", response_model=WorkflowResponse, status_code=202)
async def create_workflow(
    workflow_request: WorkflowRequest,
    background_tasks: BackgroundTasks
):
    """
    Start a new proposal evaluation workflow.
    
    This endpoint triggers the orchestration process asynchronously.
    """
    logger.info(f"Received workflow request for proposal: {workflow_request.proposal_id}")
    
    try:
        # Register the workflow but don't run it yet
        workflow_type, _ = orchestration_manager.workflow_manager.determine_workflow_type(
            workflow_request.proposal_data
        )
        await orchestration_manager.registry.register_workflow(
            workflow_request.proposal_id, 
            workflow_type
        )
        
        # Run the workflow in the background
        async def run_workflow_task():
            try:
                await orchestration_manager.run_workflow(
                    proposal_id=workflow_request.proposal_id,
                    user_id=workflow_request.user_id,
                    proposal_data=workflow_request.proposal_data
                )
            except Exception as e:
                logger.error(f"Background workflow execution failed: {str(e)}")
        
        # Add to background tasks
        background_tasks.add_task(run_workflow_task)
        
        return {
            "workflow_id": workflow_request.proposal_id,
            "status": "accepted",
            "message": f"Workflow for proposal {workflow_request.proposal_id} has been started"
        }
    
    except Exception as e:
        logger.error(f"Error creating workflow: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating workflow: {str(e)}"
        )

@router.get("/workflows/{workflow_id}", response_model=WorkflowStatusResponse)
async def get_workflow_status(workflow_id: str):
    """
    Get the status of a specific workflow.
    """
    try:
        status = await orchestration_manager.get_workflow_status(workflow_id)
        return status
    except ValueError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting workflow status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting workflow status: {str(e)}"
        )

@router.get("/workflows", response_model=WorkflowsListResponse)
async def list_workflows(
    status: Optional[str] = Query(None, description="Filter by workflow status"),
    limit: int = Query(10, description="Maximum number of workflows to return"),
    offset: int = Query(0, description="Offset for pagination")
):
    """
    List all workflows with optional filtering.
    """
    try:
        workflows = await orchestration_manager.get_all_workflows()
        
        # Filter by status if specified
        if status:
            workflows = [w for w in workflows if w["status"] == status]
        
        # Apply pagination
        paginated_workflows = workflows[offset:offset + limit]
        
        return {
            "workflows": paginated_workflows,
            "count": len(workflows)
        }
    except Exception as e:
        logger.error(f"Error listing workflows: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing workflows: {str(e)}"
        )

@router.post("/workflows/{workflow_id}/cancel", response_model=WorkflowCancelResponse)
async def cancel_workflow(workflow_id: str):
    """
    Cancel a running workflow.
    """
    try:
        result = await orchestration_manager.cancel_workflow(workflow_id)
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error canceling workflow: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error canceling workflow: {str(e)}"
        )

@router.post("/cleanup", response_model=WorkflowCleanupResponse)
async def cleanup_workflows(max_age_hours: int = Query(24, description="Maximum age in hours")):
    """
    Clean up old workflows.
    """
    try:
        result = await orchestration_manager.cleanup_workflows(max_age_hours)
        return result
    except Exception as e:
        logger.error(f"Error cleaning up workflows: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up workflows: {str(e)}"
        )

@router.get("/workflows/{workflow_id}/result", response_model=WorkflowResultResponse)
async def get_workflow_result(workflow_id: str):
    """
    Get the detailed results of a completed workflow.
    """
    try:
        # Get workflow status first
        workflow = await orchestration_manager.registry.get_workflow(workflow_id)
        
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")
        
        if workflow["status"] != WorkflowStatus.COMPLETED:
            raise ValueError(f"Workflow {workflow_id} is not completed (status: {workflow['status']})")
        
        # Compile the results
        results = workflow["results"]
        
        return {
            "proposal_id": workflow_id,
            "workflow_type": workflow["type"],
            "processing_time_ms": (workflow["completed_at"] - workflow["created_at"]) * 1000 if workflow["completed_at"] else 0,
            "compliance": results.get("compliance", {}),
            "evaluation": results.get("evaluation", {}),
            "market": results.get("market", {}),
            "recommendation": results.get("recommendation", "No recommendation available")
        }
    except ValueError as e:
        raise HTTPException(
            status_code=404 if "not found" in str(e) else 400,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error getting workflow result: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting workflow result: {str(e)}"
        )

# Endpoint for running a workflow synchronously (for testing)
@router.post("/run-sync", response_model=WorkflowResultResponse)
async def run_workflow_sync(workflow_request: WorkflowRequest):
    """
    Run a workflow synchronously and return the results.
    
    This endpoint is mainly for testing purposes.
    """
    logger.info(f"Running synchronous workflow for proposal: {workflow_request.proposal_id}")
    
    try:
        # Run the workflow and get the results
        results = await orchestration_manager.run_workflow(
            proposal_id=workflow_request.proposal_id,
            user_id=workflow_request.user_id,
            proposal_data=workflow_request.proposal_data
        )
        
        return results
    except Exception as e:
        logger.error(f"Error running sync workflow: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error running sync workflow: {str(e)}"
        )