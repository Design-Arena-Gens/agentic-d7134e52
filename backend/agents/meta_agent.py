"""
Meta-Agent - Orchestrates other agents and manages task decomposition
Coordinates NPI lookup, geocoding, memory storage, and analysis
"""
from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import uuid

from backend.models.agent import AgentRun, FeedbackSignal
from backend.agents.memory_agent import memory_agent
from backend.integrations.npi import npi_client
from backend.integrations.geocode import geocoder

logger = logging.getLogger(__name__)


class MetaAgent:
    """
    Meta-Agent orchestrates complex tasks by decomposing them
    and dispatching to specialized sub-agents
    """

    def __init__(self):
        self.name = "meta_agent"

    async def initialize(self):
        """Initialize meta-agent"""
        logger.info("Meta-agent initialized")

    async def start_run(
        self,
        db: AsyncSession,
        agent_type: str,
        task_description: str,
        input_data: Dict[str, Any],
        parent_run_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> AgentRun:
        """
        Start a new agent run
        """
        run = AgentRun(
            agent_type=agent_type,
            task_description=task_description,
            input_data=input_data,
            status="running",
            parent_run_id=parent_run_id,
            user_id=user_id,
            started_at=datetime.utcnow()
        )

        db.add(run)
        await db.commit()
        await db.refresh(run)

        logger.info(f"Started {agent_type} run: {run.id}")

        return run

    async def complete_run(
        self,
        db: AsyncSession,
        run: AgentRun,
        output_data: Dict[str, Any],
        status: str = "success",
        error_message: Optional[str] = None
    ):
        """
        Complete an agent run
        """
        run.status = status
        run.output_data = output_data
        run.error_message = error_message
        run.completed_at = datetime.utcnow()
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

        await db.commit()

        logger.info(f"Completed {run.agent_type} run: {run.id} - {status}")

    async def execute_provider_lookup(
        self,
        db: AsyncSession,
        npi_number: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute provider lookup workflow:
        1. Lookup NPI
        2. Geocode address
        3. Store in memory
        4. Return enriched data
        """
        # Start meta run
        run = await self.start_run(
            db=db,
            agent_type="meta",
            task_description=f"Provider lookup for NPI {npi_number}",
            input_data={"npi_number": npi_number},
            user_id=user_id
        )

        try:
            # Step 1: NPI Lookup
            npi_run = await self.start_run(
                db=db,
                agent_type="npi_lookup",
                task_description=f"Fetch NPI data for {npi_number}",
                input_data={"npi_number": npi_number},
                parent_run_id=str(run.id),
                user_id=user_id
            )

            npi_data = await npi_client.lookup_npi(npi_number)

            if not npi_data:
                await self.complete_run(
                    db=db,
                    run=npi_run,
                    output_data={},
                    status="failed",
                    error_message="NPI not found"
                )
                await self.complete_run(
                    db=db,
                    run=run,
                    output_data={},
                    status="failed",
                    error_message="NPI not found"
                )
                return {"error": "NPI not found", "run_id": str(run.id)}

            parsed_data = npi_client.parse_provider_data(npi_data)

            await self.complete_run(
                db=db,
                run=npi_run,
                output_data=parsed_data
            )

            # Step 2: Geocode address
            geocode_run = await self.start_run(
                db=db,
                agent_type="geocoding",
                task_description=f"Geocode address for {npi_number}",
                input_data={
                    "address": parsed_data.get("address_line_1"),
                    "city": parsed_data.get("city"),
                    "state": parsed_data.get("state"),
                    "postal_code": parsed_data.get("postal_code")
                },
                parent_run_id=str(run.id),
                user_id=user_id
            )

            coords = None
            if parsed_data.get("address_line_1"):
                try:
                    coords = await geocoder.geocode(
                        address=parsed_data.get("address_line_1"),
                        city=parsed_data.get("city"),
                        state=parsed_data.get("state"),
                        postal_code=parsed_data.get("postal_code")
                    )
                except Exception as e:
                    logger.warning(f"Geocoding failed: {e}")

            geocode_output = {}
            if coords:
                parsed_data["latitude"] = coords[0]
                parsed_data["longitude"] = coords[1]
                geocode_output = {"latitude": coords[0], "longitude": coords[1]}

            await self.complete_run(
                db=db,
                run=geocode_run,
                output_data=geocode_output
            )

            # Step 3: Store in memory
            memory_text = f"Provider {npi_number}: {parsed_data.get('first_name', '')} {parsed_data.get('last_name', '')} {parsed_data.get('organization_name', '')} in {parsed_data.get('city', '')}, {parsed_data.get('state', '')}"

            await memory_agent.store_memory(
                db=db,
                content=memory_text,
                memory_type="episodic",
                agent_type="meta",
                related_run_id=str(run.id),
                tags=["provider", "npi_lookup", npi_number],
                importance_score=0.7
            )

            # Complete meta run
            await self.complete_run(
                db=db,
                run=run,
                output_data=parsed_data
            )

            return {
                "success": True,
                "run_id": str(run.id),
                "provider": parsed_data
            }

        except Exception as e:
            logger.error(f"Error in provider lookup: {e}", exc_info=True)
            await self.complete_run(
                db=db,
                run=run,
                output_data={},
                status="failed",
                error_message=str(e)
            )
            return {
                "error": str(e),
                "run_id": str(run.id)
            }

    async def get_run_hierarchy(
        self,
        db: AsyncSession,
        run_id: str
    ) -> Dict[str, Any]:
        """
        Get full run hierarchy (parent and all children)
        """
        # Get main run
        result = await db.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            return None

        # Get child runs
        result = await db.execute(
            select(AgentRun).where(AgentRun.parent_run_id == run_id)
        )
        children = result.scalars().all()

        return {
            "run": {
                "id": str(run.id),
                "agent_type": run.agent_type,
                "status": run.status,
                "task_description": run.task_description,
                "input_data": run.input_data,
                "output_data": run.output_data,
                "duration_seconds": run.duration_seconds,
                "started_at": run.started_at.isoformat() if run.started_at else None,
                "completed_at": run.completed_at.isoformat() if run.completed_at else None
            },
            "children": [
                {
                    "id": str(child.id),
                    "agent_type": child.agent_type,
                    "status": child.status,
                    "duration_seconds": child.duration_seconds
                }
                for child in children
            ]
        }

    async def apply_feedback(
        self,
        db: AsyncSession,
        run_id: str,
        feedback_type: str,
        feedback_value: float,
        feedback_text: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> FeedbackSignal:
        """
        Apply human feedback to agent run for reinforcement learning
        """
        # Get run
        result = await db.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )
        run = result.scalar_one_or_none()

        if not run:
            raise ValueError(f"Run {run_id} not found")

        # Create feedback signal
        feedback = FeedbackSignal(
            run_id=run_id,
            agent_type=run.agent_type,
            feedback_type=feedback_type,
            feedback_value=feedback_value,
            feedback_text=feedback_text,
            user_id=user_id
        )

        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)

        logger.info(f"Feedback applied to run {run_id}: {feedback_type} = {feedback_value}")

        # TODO: Update agent weights/parameters based on feedback
        # This would involve updating a policy model or scoring weights

        return feedback


# Global singleton
meta_agent = MetaAgent()
