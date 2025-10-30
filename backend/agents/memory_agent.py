"""
Memory Agent - Manages episodic and semantic memory
Uses PostgreSQL + FAISS for hybrid storage
"""
from typing import List, Dict, Optional, Any
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from backend.models.agent import AgentMemory
from backend.ml.embeddings import embedding_service
from backend.utils.security import encryption_service

logger = logging.getLogger(__name__)


class MemoryAgent:
    """
    Memory Agent for storing and retrieving agent memories
    Combines SQL storage with vector semantic search
    """

    def __init__(self):
        self.name = "memory_agent"

    async def store_memory(
        self,
        db: AsyncSession,
        content: str,
        memory_type: str = "episodic",
        agent_type: str = "meta",
        related_run_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        importance_score: float = 0.5,
        encrypt: bool = False
    ) -> AgentMemory:
        """
        Store a memory with optional encryption and embedding
        """
        # Encrypt if requested
        content_encrypted = None
        if encrypt:
            content_encrypted = encryption_service.encrypt(content)

        # Create memory record
        memory = AgentMemory(
            memory_type=memory_type,
            content=content,
            content_encrypted=content_encrypted,
            agent_type=agent_type,
            related_run_id=related_run_id,
            tags=tags or [],
            importance_score=importance_score
        )

        db.add(memory)
        await db.flush()

        # Add to FAISS for semantic search
        try:
            embedding_service.add_documents(
                documents=[content],
                metadata=[{
                    "memory_id": str(memory.id),
                    "memory_type": memory_type,
                    "agent_type": agent_type,
                    "importance": importance_score
                }]
            )
            memory.embedding_stored = "faiss"
        except Exception as e:
            logger.error(f"Error storing embedding: {e}")

        await db.commit()
        await db.refresh(memory)

        logger.info(f"Stored {memory_type} memory: {memory.id}")

        return memory

    async def retrieve_memories(
        self,
        db: AsyncSession,
        query: str,
        memory_type: Optional[str] = None,
        agent_type: Optional[str] = None,
        top_k: int = 5
    ) -> List[AgentMemory]:
        """
        Retrieve relevant memories using semantic search
        """
        # Semantic search with FAISS
        try:
            search_results = embedding_service.search(query, top_k=top_k * 2)
        except Exception as e:
            logger.error(f"Error searching embeddings: {e}")
            search_results = []

        # Get memory IDs from search results
        memory_ids = [result[2].get("memory_id") for result in search_results if result[2].get("memory_id")]

        if not memory_ids:
            return []

        # Fetch full memory objects from DB
        stmt = select(AgentMemory).where(AgentMemory.id.in_(memory_ids))

        if memory_type:
            stmt = stmt.where(AgentMemory.memory_type == memory_type)
        if agent_type:
            stmt = stmt.where(AgentMemory.agent_type == agent_type)

        result = await db.execute(stmt)
        memories = result.scalars().all()

        # Update access count
        for memory in memories:
            memory.access_count += 1
            memory.last_accessed = datetime.utcnow()

        await db.commit()

        logger.info(f"Retrieved {len(memories)} memories for query: {query[:50]}")

        return memories[:top_k]

    async def get_recent_memories(
        self,
        db: AsyncSession,
        agent_type: Optional[str] = None,
        limit: int = 10
    ) -> List[AgentMemory]:
        """
        Get most recent memories
        """
        stmt = select(AgentMemory).order_by(AgentMemory.created_at.desc()).limit(limit)

        if agent_type:
            stmt = stmt.where(AgentMemory.agent_type == agent_type)

        result = await db.execute(stmt)
        memories = result.scalars().all()

        return memories

    async def get_important_memories(
        self,
        db: AsyncSession,
        agent_type: Optional[str] = None,
        min_importance: float = 0.7,
        limit: int = 10
    ) -> List[AgentMemory]:
        """
        Get high-importance memories
        """
        stmt = (
            select(AgentMemory)
            .where(AgentMemory.importance_score >= min_importance)
            .order_by(AgentMemory.importance_score.desc())
            .limit(limit)
        )

        if agent_type:
            stmt = stmt.where(AgentMemory.agent_type == agent_type)

        result = await db.execute(stmt)
        memories = result.scalars().all()

        return memories

    def decrypt_memory(self, memory: AgentMemory) -> str:
        """
        Decrypt memory content if encrypted
        """
        if memory.content_encrypted:
            try:
                return encryption_service.decrypt(memory.content_encrypted)
            except Exception as e:
                logger.error(f"Error decrypting memory: {e}")
                return memory.content
        return memory.content

    async def prune_memories(
        self,
        db: AsyncSession,
        max_age_days: int = 90,
        min_importance: float = 0.3,
        min_access_count: int = 1
    ):
        """
        Prune old, low-importance, or rarely accessed memories
        """
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)

        # Find memories to prune
        stmt = select(AgentMemory).where(
            (AgentMemory.created_at < cutoff_date) &
            (AgentMemory.importance_score < min_importance) &
            (AgentMemory.access_count < min_access_count)
        )

        result = await db.execute(stmt)
        memories_to_prune = result.scalars().all()

        # Delete memories
        for memory in memories_to_prune:
            await db.delete(memory)

        await db.commit()

        logger.info(f"Pruned {len(memories_to_prune)} memories")


# Global singleton
memory_agent = MemoryAgent()
