"""Agent API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from backend.database import get_db
from backend.models.user import User
from backend.api.auth import get_current_user
from backend.agents.meta_agent import meta_agent
from backend.agents.memory_agent import memory_agent

router = APIRouter()


class ExecuteTaskRequest(BaseModel):
    npi_number: str


class FeedbackRequest(BaseModel):
    run_id: str
    feedback_type: str  # correction, approval, rejection
    feedback_value: float  # -1.0 to 1.0
    feedback_text: Optional[str] = None


class MemorySearchRequest(BaseModel):
    query: str
    memory_type: Optional[str] = None
    top_k: int = 5


@router.post("/execute/provider-lookup")
async def execute_provider_lookup(
    request: ExecuteTaskRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute provider lookup via meta-agent"""
    result = await meta_agent.execute_provider_lookup(
        db=db,
        npi_number=request.npi_number,
        user_id=str(current_user.id)
    )

    return result


@router.get("/run/{run_id}")
async def get_run_details(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get agent run details with hierarchy"""
    result = await meta_agent.get_run_hierarchy(db=db, run_id=run_id)

    if not result:
        raise HTTPException(status_code=404, detail="Run not found")

    return result


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit feedback for reinforcement learning"""
    feedback = await meta_agent.apply_feedback(
        db=db,
        run_id=request.run_id,
        feedback_type=request.feedback_type,
        feedback_value=request.feedback_value,
        feedback_text=request.feedback_text,
        user_id=str(current_user.id)
    )

    return {
        "feedback_id": str(feedback.id),
        "message": "Feedback recorded successfully"
    }


@router.post("/memory/search")
async def search_memories(
    request: MemorySearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search agent memories semantically"""
    memories = await memory_agent.retrieve_memories(
        db=db,
        query=request.query,
        memory_type=request.memory_type,
        top_k=request.top_k
    )

    return [
        {
            "id": str(m.id),
            "content": memory_agent.decrypt_memory(m),
            "memory_type": m.memory_type,
            "agent_type": m.agent_type,
            "importance_score": m.importance_score,
            "access_count": m.access_count,
            "created_at": m.created_at.isoformat()
        }
        for m in memories
    ]


@router.get("/memory/recent")
async def get_recent_memories(
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get recent memories"""
    memories = await memory_agent.get_recent_memories(db=db, limit=limit)

    return [
        {
            "id": str(m.id),
            "content": memory_agent.decrypt_memory(m)[:100] + "...",
            "memory_type": m.memory_type,
            "created_at": m.created_at.isoformat()
        }
        for m in memories
    ]
