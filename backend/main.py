# middleware/main.py

import os
from typing import Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, Header, Body, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from pydantic import BaseModel, Field
import httpx
import json
import logging
import dotenv
import time

# Load environment variables from .env file if present
dotenv.load_dotenv()

# Import our orchestrator components
from backend.orchestrator import orchestration_manager 
from backend.orchestrator.api import router as orchestrator_router

# Import utility modules
from utils.azure_tracing import setup_azure_tracing

# Configure Azure tracing if enabled
setup_azure_tracing()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="MAAS Middleware API",
    description="AI Agent Orchestration Layer for Multi-Agent Acquisition System",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Backend API URL
BACKEND_API_URL = os.getenv("BACKEND_API_URL", "http://backend-service:8000")

# Request and response models
class ProposalEvaluationRequest(BaseModel):
    proposal_id: str
    title: str = Field(..., description="Title of the proposal")
    description: str = Field(..., description="Detailed description of the proposal")
    vendor: str = Field(..., description="Name of the vendor")
    category: str = Field(..., description="Product or service category")
    amount: float = Field(..., description="Proposed contract amount")
    duration_months: int = Field(..., description="Contract duration in months")
    regulatory_domain: str = Field(..., description="Regulatory domain (e.g., federal, healthcare)")
    additional_details: Optional[Dict[str, Any]] = Field(default=None, description="Any additional proposal details")

class ProposalEvaluationResponse(BaseModel):
    proposal_id: str
    compliance: Dict[str, Any]
    evaluation: Dict[str, Any]
    market: Dict[str, Any]
    recommendation: str
    processing_time_ms: float

class HumanFeedbackRequest(BaseModel):
    proposal_id: str = Field(..., description="ID of the proposal")
    agent_type: str = Field(..., description="Type of agent (compliance, evaluation, market)")
    feedback: str = Field(..., description="Human feedback on agent output")
    rating: Optional[int] = Field(None, description="Optional rating (1-5 scale)")

class HumanFeedbackResponse(BaseModel):
    status: str
    message: str

# Helper function to validate JWT token
async def validate_token(authorization: str = Header(...)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    
    token = authorization.replace("Bearer ", "")
    
    # In production, validate the token with your backend
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{BACKEND_API_URL}/api/auth/validate-token",
                json={"token": token}
            )
            if response.status_code != 200:
                raise HTTPException(status_code=401, detail="Invalid token")
            return response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=500, detail="Error validating token")

# Include the orchestrator router
app.include_router(orchestrator_router)

# Legacy API routes (preserved for backward compatibility)
@app.post("/api/evaluate-proposal", response_model=ProposalEvaluationResponse)
async def evaluate_proposal(
    proposal: ProposalEvaluationRequest,
    background_tasks: BackgroundTasks,
    user_info: Dict = Depends(validate_token)
):
    """
    Evaluate a proposal using multiple AI agents.
    
    This endpoint is maintained for backward compatibility and uses the new orchestration system internally.
    """
    start_time = time.time()
    
    try:
        # Log the incoming request
        logger.info(f"Evaluating proposal: {proposal.proposal_id}")
        
        # Prepare the proposal data for our agents
        proposal_data = proposal.model_dump()
        
        # Add the user ID to the proposal data
        proposal_data["user_id"] = user_info.get("user_id")
        
        # Run the orchestrator workflow
        results = await orchestration_manager.run_workflow(
            proposal_id=proposal.proposal_id,
            user_id=user_info.get("user_id"),
            proposal_data=proposal_data
        )
        
        # Calculate processing time
        processing_time = (time.time() - start_time) * 1000
        
        # Log completion
        logger.info(f"Proposal evaluation completed in {processing_time:.2f}ms")
        
        # Return the results
        return {
            "proposal_id": proposal.proposal_id,
            "compliance": results["compliance"],
            "evaluation": results["evaluation"],
            "market": results["market"],
            "recommendation": results["recommendation"],
            "processing_time_ms": processing_time
        }
    except Exception as e:
        logger.error(f"Error evaluating proposal: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error evaluating proposal: {str(e)}")

@app.post("/api/human-feedback", response_model=HumanFeedbackResponse)
async def submit_human_feedback(
    feedback_request: HumanFeedbackRequest = Body(...),
    user_info: Dict = Depends(validate_token)
):
    """
    Submit human feedback on agent outputs for a specific proposal.
    """
    try:
        # Log the incoming feedback
        logger.info(f"Received feedback for proposal {feedback_request.proposal_id}, agent: {feedback_request.agent_type}")
        
        # Forward the feedback to the backend API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_API_URL}/api/feedback",
                json={
                    "proposal_id": feedback_request.proposal_id,
                    "agent_type": feedback_request.agent_type,
                    "feedback": feedback_request.feedback,
                    "rating": feedback_request.rating,
                    "user_id": user_info.get("user_id")
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Error storing feedback"
                )
        
        return {"status": "success", "message": "Feedback submitted successfully"}
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error submitting feedback: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "orchestrator": "online",
        "timestamp": time.time()
    }

# Application startup events
@app.on_event("startup")
async def startup_event():
    """
    Runs when the application starts.
    Initializes necessary components and connections.
    """
    logger.info("Starting MAAS Middleware API")
    
    # Setup Azure tracing if enabled
    setup_azure_tracing()
    
    # Log environment details
    logger.info(f"Environment: {os.getenv('ENVIRONMENT', 'development')}")
    logger.info(f"Backend API URL: {BACKEND_API_URL}")
    
    logger.info("MAAS Middleware API started successfully")

# Application shutdown events
@app.on_event("shutdown")
async def shutdown_event():
    """
    Runs when the application shuts down.
    Cleans up resources and connections.
    """
    logger.info("Shutting down MAAS Middleware API")
    
    # Clean up any pending workflows
    # This is an optional step and can be removed if not needed
    try:
        # Log active workflows before shutdown
        workflows = await orchestration_manager.get_all_workflows()
        active_count = sum(1 for w in workflows if w["status"] in ["pending", "running"])
        logger.info(f"Shutdown with {active_count} active workflows pending")
    except Exception as e:
        logger.error(f"Error during shutdown cleanup: {str(e)}")
    
    logger.info("MAAS Middleware API shutdown complete")

# Run the application if executed directly
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)