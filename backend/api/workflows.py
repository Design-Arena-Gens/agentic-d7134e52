"""Workflow orchestration API"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime

from backend.database import get_db
from backend.models.user import User
from backend.models.workflow import WorkflowExecution
from backend.models.provider import Provider
from backend.api.auth import get_current_user
from backend.agents.meta_agent import meta_agent
from backend.integrations.npi import npi_client
from backend.integrations.geocode import geocoder
import json
from backend.utils.security import compute_integrity_hash

router = APIRouter()


class RunWorkflowRequest(BaseModel):
    npi_number: str
    workflow_type: str = "provider_verification"


class WorkflowStatus(BaseModel):
    id: str
    status: str
    progress_percentage: int
    current_step: Optional[str]
    steps_completed: list
    started_at: str
    completed_at: Optional[str]


@router.post("/run")
async def run_workflow(
    request: RunWorkflowRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Execute end-to-end workflow
    Performs: NPI lookup -> Geocoding -> Storage -> Evidence collection
    """
    # Create workflow execution
    workflow = WorkflowExecution(
        workflow_type=request.workflow_type,
        input_params={"npi_number": request.npi_number},
        status="running",
        user_id=str(current_user.id)
    )

    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)

    # Execute workflow in background
    background_tasks.add_task(
        execute_workflow_task,
        workflow_id=str(workflow.id),
        npi_number=request.npi_number
    )

    return {
        "workflow_id": str(workflow.id),
        "status": "running",
        "message": "Workflow started"
    }


async def execute_workflow_task(workflow_id: str, npi_number: str):
    """Background task to execute workflow"""
    from backend.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            # Get workflow
            result = await db.execute(
                select(WorkflowExecution).where(WorkflowExecution.id == workflow_id)
            )
            workflow = result.scalar_one()

            evidence = []
            steps_completed = []

            # Step 1: NPI Lookup
            workflow.current_step = "npi_lookup"
            workflow.progress_percentage = 20
            await db.commit()

            npi_data = await npi_client.lookup_npi(npi_number)

            if not npi_data:
                workflow.status = "failed"
                workflow.error_message = "NPI not found"
                await db.commit()
                return

            parsed = npi_client.parse_provider_data(npi_data)
            steps_completed.append("npi_lookup")
            evidence.append({
                "step": "npi_lookup",
                "source": "CMS NPI Registry",
                "data": {
                    "npi": npi_number,
                    "name": f"{parsed.get('first_name', '')} {parsed.get('last_name', '')}".strip() or parsed.get('organization_name'),
                    "taxonomy": parsed.get('taxonomy_description')
                }
            })

            # Step 2: Geocoding
            workflow.current_step = "geocoding"
            workflow.progress_percentage = 40
            workflow.steps_completed = steps_completed
            await db.commit()

            coords = None
            if parsed.get("address_line_1"):
                try:
                    coords = await geocoder.geocode(
                        address=parsed["address_line_1"],
                        city=parsed.get("city"),
                        state=parsed.get("state"),
                        postal_code=parsed.get("postal_code")
                    )
                    if coords:
                        parsed["latitude"] = coords[0]
                        parsed["longitude"] = coords[1]
                        steps_completed.append("geocoding")
                        evidence.append({
                            "step": "geocoding",
                            "source": "Nominatim (OpenStreetMap)",
                            "data": {
                                "latitude": coords[0],
                                "longitude": coords[1],
                                "address": parsed.get("address_line_1")
                            }
                        })
                except Exception as e:
                    evidence.append({
                        "step": "geocoding",
                        "source": "Nominatim (OpenStreetMap)",
                        "error": str(e)
                    })

            # Step 3: Store provider
            workflow.current_step = "storage"
            workflow.progress_percentage = 60
            workflow.steps_completed = steps_completed
            await db.commit()

            # Check if provider exists
            result = await db.execute(
                select(Provider).where(Provider.npi_number == npi_number)
            )
            provider = result.scalar_one_or_none()

            if not provider:
                # Compute integrity hash
                raw_json = json.dumps(parsed["raw_data"], sort_keys=True)
                integrity_hash = compute_integrity_hash(raw_json)

                provider = Provider(
                    npi_number=parsed["npi_number"],
                    first_name=parsed.get("first_name"),
                    last_name=parsed.get("last_name"),
                    organization_name=parsed.get("organization_name"),
                    taxonomy_code=parsed.get("taxonomy_code"),
                    taxonomy_description=parsed.get("taxonomy_description"),
                    address_line_1=parsed.get("address_line_1"),
                    address_line_2=parsed.get("address_line_2"),
                    city=parsed.get("city"),
                    state=parsed.get("state"),
                    postal_code=parsed.get("postal_code"),
                    country=parsed.get("country", "US"),
                    phone=parsed.get("phone"),
                    fax=parsed.get("fax"),
                    latitude=parsed.get("latitude"),
                    longitude=parsed.get("longitude"),
                    raw_data=parsed["raw_data"],
                    integrity_hash=integrity_hash,
                    last_verified=datetime.utcnow()
                )

                db.add(provider)
                await db.commit()
                await db.refresh(provider)

            steps_completed.append("storage")
            evidence.append({
                "step": "storage",
                "source": "Database",
                "data": {
                    "provider_id": str(provider.id),
                    "stored": True
                }
            })

            # Step 4: Finalize
            workflow.current_step = "finalize"
            workflow.progress_percentage = 100
            workflow.steps_completed = steps_completed
            workflow.evidence = evidence
            workflow.status = "success"
            workflow.results = {
                "provider_id": str(provider.id),
                "npi_number": npi_number,
                "verification_complete": True
            }
            workflow.completed_at = datetime.utcnow()
            await db.commit()

        except Exception as e:
            workflow.status = "failed"
            workflow.error_message = str(e)
            workflow.completed_at = datetime.utcnow()
            await db.commit()


@router.get("/{workflow_id}/status", response_model=WorkflowStatus)
async def get_workflow_status(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get workflow execution status"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return WorkflowStatus(
        id=str(workflow.id),
        status=workflow.status,
        progress_percentage=workflow.progress_percentage,
        current_step=workflow.current_step,
        steps_completed=workflow.steps_completed or [],
        started_at=workflow.started_at.isoformat(),
        completed_at=workflow.completed_at.isoformat() if workflow.completed_at else None
    )


@router.get("/{workflow_id}/evidence")
async def get_workflow_evidence(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get workflow evidence trail"""
    result = await db.execute(
        select(WorkflowExecution).where(WorkflowExecution.id == workflow_id)
    )
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "workflow_id": str(workflow.id),
        "status": workflow.status,
        "evidence": workflow.evidence or [],
        "results": workflow.results
    }
