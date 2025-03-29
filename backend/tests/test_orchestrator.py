# backend/tests/test_orchestrator.py

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import json
import os
import sys
from pydantic import BaseModel

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import components to test
from backend.orchestrator import (
    OrchestrationManager,
    WorkflowRegistry,
    WorkflowStatus,
    WorkflowTaskResult,
    ComplianceResult,
    EvaluationResult,
    MarketResult,
    OrchestratorResult
)

# Test data
TEST_PROPOSAL_ID = "test-proposal-123"
TEST_USER_ID = "test-user-456"
TEST_PROPOSAL_DATA = {
    "proposal_id": TEST_PROPOSAL_ID,
    "title": "Test Proposal",
    "description": "This is a test proposal for unit testing",
    "vendor": "Test Vendor Inc",
    "category": "IT Services",
    "amount": 100000.0,
    "duration_months": 12,
    "regulatory_domain": "federal"
}

# Mock agent results
MOCK_COMPLIANCE_RESULT = ComplianceResult(
    status="compliant",
    details="No compliance issues found",
    regulatory_issues=[]
)

MOCK_EVALUATION_RESULT = EvaluationResult(
    score=85.0,
    strengths=["Good technical approach", "Reasonable pricing"],
    weaknesses=["Limited past performance"],
    recommendations=["Enhance documentation"]
)

MOCK_MARKET_RESULT = MarketResult(
    competitive_analysis="Competitive pricing compared to market",
    price_assessment="Within market average",
    market_trends=["Cloud adoption increasing", "Remote work focus"],
    recommendations=["Consider cloud-first approach"]
)

MOCK_ORCHESTRATOR_RESULT = OrchestratorResult(
    compliance=MOCK_COMPLIANCE_RESULT,
    evaluation=MOCK_EVALUATION_RESULT,
    market=MOCK_MARKET_RESULT,
    overall_recommendation="Recommend approval with standard oversight"
)

# Test the WorkflowRegistry
@pytest.mark.asyncio
async def test_workflow_registry():
    """Test the WorkflowRegistry class."""
    registry = WorkflowRegistry()
    
    # Test registering a workflow
    await registry.register_workflow(TEST_PROPOSAL_ID, "standard")
    workflow = await registry.get_workflow(TEST_PROPOSAL_ID)
    
    assert workflow is not None
    assert workflow["id"] == TEST_PROPOSAL_ID
    assert workflow["type"] == "standard"
    assert workflow["status"] == WorkflowStatus.PENDING
    
    # Test updating workflow status
    await registry.update_workflow_status(TEST_PROPOSAL_ID, WorkflowStatus.RUNNING)
    workflow = await registry.get_workflow(TEST_PROPOSAL_ID)
    assert workflow["status"] == WorkflowStatus.RUNNING
    
    # Test adding task result
    task_result = WorkflowTaskResult(
        task_id=f"{TEST_PROPOSAL_ID}-compliance",
        agent_type="compliance",
        status="completed",
        result={"status": "compliant"}
    )
    
    await registry.add_task_result(TEST_PROPOSAL_ID, task_result)
    workflow = await registry.get_workflow(TEST_PROPOSAL_ID)
    
    assert len(workflow["tasks"]) == 1
    assert workflow["tasks"][0].task_id == f"{TEST_PROPOSAL_ID}-compliance"
    assert workflow["results"]["compliance"] == {"status": "compliant"}
    
    # Test getting all workflows
    workflows = await registry.get_all_workflows()
    assert len(workflows) == 1
    assert workflows[0]["id"] == TEST_PROPOSAL_ID
    
    # Test cleanup
    await registry.register_workflow("old-workflow", "standard")
    # Simulate old creation time
    registry._workflows["old-workflow"]["created_at"] = 0
    
    removed = await registry.cleanup_old_workflows(max_age_hours=1)
    assert removed == 1
    
    workflows = await registry.get_all_workflows()
    assert len(workflows) == 1
    assert workflows[0]["id"] == TEST_PROPOSAL_ID

# Test the OrchestrationManager with mocked components
@pytest.mark.asyncio
async def test_orchestration_manager():
    """Test the OrchestrationManager class with mocked components."""
    # Create mock Orchestrator
    mock_orchestrator = MagicMock()
    mock_orchestrator._run_compliance_agent = AsyncMock(return_value=MOCK_COMPLIANCE_RESULT)
    mock_orchestrator._run_evaluation_agent = AsyncMock(return_value=MOCK_EVALUATION_RESULT)
    mock_orchestrator._run_market_agent = AsyncMock(return_value=MOCK_MARKET_RESULT)
    mock_orchestrator._run_orchestrator_agent = AsyncMock(return_value=MOCK_ORCHESTRATOR_RESULT)
    
    # Create mock WorkflowManager
    mock_workflow_manager = MagicMock()
    mock_workflow_manager.determine_workflow_type = MagicMock(return_value=("standard", None))
    mock_workflow_manager.process_proposal = AsyncMock(return_value={
        "compliance": MOCK_COMPLIANCE_RESULT.model_dump(),
        "evaluation": MOCK_EVALUATION_RESULT.model_dump(),
        "market": MOCK_MARKET_RESULT.model_dump(),
        "recommendation": "Recommend approval with standard oversight"
    })
    
    # Patch the necessary components
    with patch('backend.orchestrator.Orchestrator', return_value=mock_orchestrator), \
         patch('backend.orchestrator.WorkflowManager', return_value=mock_workflow_manager):
        
        # Create OrchestrationManager
        manager = OrchestrationManager()
        
        # Override registry with new instance for testing
        manager.registry = WorkflowRegistry()
        
        # Test run_workflow
        result = await manager.run_workflow(
            proposal_id=TEST_PROPOSAL_ID,
            user_id=TEST_USER_ID,
            proposal_data=TEST_PROPOSAL_DATA
        )
        
        # Verify workflow was registered and updated
        workflow = await manager.registry.get_workflow(TEST_PROPOSAL_ID)
        assert workflow is not None
        assert workflow["status"] == WorkflowStatus.COMPLETED
        
        # Verify workflow manager was called
        mock_workflow_manager.process_proposal.assert_called_once_with(
            proposal_id=TEST_PROPOSAL_ID,
            user_id=TEST_USER_ID,
            proposal_data=TEST_PROPOSAL_DATA
        )
        
        # Verify result is correct
        assert result["proposal_id"] == TEST_PROPOSAL_ID
        assert result["compliance"] == MOCK_COMPLIANCE_RESULT.model_dump()
        assert result["evaluation"] == MOCK_EVALUATION_RESULT.model_dump()
        assert result["market"] == MOCK_MARKET_RESULT.model_dump()
        assert result["recommendation"] == "Recommend approval with standard oversight"

# Test error handling in OrchestrationManager
@pytest.mark.asyncio
async def test_orchestration_manager_error_handling():
    """Test error handling in the OrchestrationManager."""
    # Create mock WorkflowManager that raises an exception
    mock_workflow_manager = MagicMock()
    mock_workflow_manager.determine_workflow_type = MagicMock(return_value=("standard", None))
    mock_workflow_manager.process_proposal = AsyncMock(side_effect=Exception("Test error"))
    
    # Patch the necessary components
    with patch('backend.orchestrator.Orchestrator', return_value=MagicMock()), \
         patch('backend.orchestrator.WorkflowManager', return_value=mock_workflow_manager):
        
        # Create OrchestrationManager
        manager = OrchestrationManager()
        
        # Override registry with new instance for testing
        manager.registry = WorkflowRegistry()
        
        # Test run_workflow with exception
        with pytest.raises(Exception) as excinfo:
            await manager.run_workflow(
                proposal_id=TEST_PROPOSAL_ID,
                user_id=TEST_USER_ID,
                proposal_data=TEST_PROPOSAL_DATA
            )
        
        assert "Test error" in str(excinfo.value)
        
        # Verify workflow was registered and updated to failed
        workflow = await manager.registry.get_workflow(TEST_PROPOSAL_ID)
        assert workflow is not None
        assert workflow["status"] == WorkflowStatus.FAILED
        
        # Verify error task was added
        assert len(workflow["tasks"]) == 1
        assert workflow["tasks"][0].status == "failed"
        assert "Test error" in workflow["tasks"][0].error

if __name__ == "__main__":
    # Run the tests
    asyncio.run(test_workflow_registry())
    print("WorkflowRegistry tests passed!")
    
    asyncio.run(test_orchestration_manager())
    print("OrchestrationManager tests passed!")
    
    asyncio.run(test_orchestration_manager_error_handling())
    print("OrchestrationManager error handling tests passed!")
    
    print("All tests passed!")