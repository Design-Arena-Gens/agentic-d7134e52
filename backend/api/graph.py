"""Trust graph and TrustRank scoring API"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import List, Dict, Any
import networkx as nx
import logging
from datetime import datetime

from backend.database import get_db
from backend.models.user import User
from backend.models.provider import Provider, ProviderTrustScore
from backend.models.graph import ProviderEdge
from backend.api.auth import get_current_user
import math

router = APIRouter()
logger = logging.getLogger(__name__)


class ComputeTrustRequest(BaseModel):
    algorithm: str = "pagerank"  # pagerank, hits
    damping_factor: float = 0.85
    max_iterations: int = 100


class TrustScoreResponse(BaseModel):
    provider_id: str
    npi_number: str
    trust_score: float
    rank: int
    connections: int


@router.post("/compute-trust")
async def compute_trust_scores(
    request: ComputeTrustRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compute TrustRank scores using networkx PageRank
    Builds graph from provider edges and computes centrality
    """
    logger.info("Starting TrustRank computation")

    # Fetch all providers
    result = await db.execute(select(Provider))
    providers = result.scalars().all()

    if len(providers) == 0:
        raise HTTPException(status_code=400, detail="No providers found")

    # Fetch all edges
    result = await db.execute(select(ProviderEdge))
    edges = result.scalars().all()

    logger.info(f"Building graph with {len(providers)} nodes and {len(edges)} edges")

    # Build networkx graph
    G = nx.DiGraph()

    # Add nodes
    for provider in providers:
        G.add_node(str(provider.id), npi=provider.npi_number)

    # Add edges
    for edge in edges:
        G.add_edge(
            str(edge.source_provider_id),
            str(edge.target_provider_id),
            weight=edge.weight
        )

    # If no edges, create self-edges for all nodes
    if len(edges) == 0:
        logger.warning("No edges found, creating uniform graph")
        for provider in providers:
            G.add_edge(str(provider.id), str(provider.id), weight=1.0)

    # Compute PageRank
    if request.algorithm == "pagerank":
        scores = nx.pagerank(
            G,
            alpha=request.damping_factor,
            max_iter=request.max_iterations,
            weight='weight'
        )
    elif request.algorithm == "hits":
        hubs, authorities = nx.hits(G, max_iter=request.max_iterations)
        scores = authorities  # Use authority scores
    else:
        raise HTTPException(status_code=400, detail="Unknown algorithm")

    logger.info(f"Computed {len(scores)} trust scores")

    # Rank scores
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Store scores in database
    for rank, (provider_id, score) in enumerate(sorted_scores, start=1):
        # Check if score exists
        result = await db.execute(
            select(ProviderTrustScore).where(
                ProviderTrustScore.provider_id == provider_id
            )
        )
        trust_score_obj = result.scalar_one_or_none()

        # Count connections
        connection_count = G.degree(provider_id)

        if trust_score_obj:
            trust_score_obj.trust_score = score
            trust_score_obj.rank = rank
            trust_score_obj.connection_count = connection_count
            trust_score_obj.computed_at = datetime.utcnow()
        else:
            trust_score_obj = ProviderTrustScore(
                provider_id=provider_id,
                trust_score=score,
                rank=rank,
                connection_count=connection_count
            )
            db.add(trust_score_obj)

    await db.commit()

    logger.info("TrustRank computation completed")

    return {
        "message": "Trust scores computed successfully",
        "providers_scored": len(scores),
        "algorithm": request.algorithm,
        "top_score": sorted_scores[0][1] if sorted_scores else 0
    }


@router.post("/build-edges")
async def build_provider_edges(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Build provider graph edges based on:
    - Geographic proximity
    - Taxonomy similarity
    - Same organization
    """
    logger.info("Building provider edges")

    # Fetch all providers
    result = await db.execute(select(Provider))
    providers = result.scalars().all()

    edges_created = 0

    # Create edges based on rules
    for i, provider_a in enumerate(providers):
        for provider_b in providers[i+1:]:
            edges = []

            # Rule 1: Geographic proximity (within ~50km)
            if provider_a.latitude and provider_a.longitude and \
               provider_b.latitude and provider_b.longitude:

                distance = haversine_distance(
                    provider_a.latitude, provider_a.longitude,
                    provider_b.latitude, provider_b.longitude
                )

                if distance < 50:  # km
                    weight = max(0.1, 1.0 - (distance / 50))
                    edges.append(("location_proximity", weight))

            # Rule 2: Same taxonomy
            if provider_a.taxonomy_code and provider_b.taxonomy_code:
                if provider_a.taxonomy_code == provider_b.taxonomy_code:
                    edges.append(("taxonomy_match", 0.8))

            # Rule 3: Same city/state
            if provider_a.city and provider_b.city and \
               provider_a.state and provider_b.state:
                if provider_a.city == provider_b.city and \
                   provider_a.state == provider_b.state:
                    edges.append(("same_location", 0.6))

            # Create edges
            for edge_type, weight in edges:
                # Bidirectional edges
                edge1 = ProviderEdge(
                    source_provider_id=provider_a.id,
                    target_provider_id=provider_b.id,
                    edge_type=edge_type,
                    weight=weight
                )
                edge2 = ProviderEdge(
                    source_provider_id=provider_b.id,
                    target_provider_id=provider_a.id,
                    edge_type=edge_type,
                    weight=weight
                )

                db.add(edge1)
                db.add(edge2)
                edges_created += 2

    await db.commit()

    logger.info(f"Created {edges_created} edges")

    return {
        "message": "Graph edges built successfully",
        "edges_created": edges_created,
        "providers": len(providers)
    }


@router.get("/top-providers")
async def get_top_providers(
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> List[TrustScoreResponse]:
    """Get top-ranked providers by trust score"""
    result = await db.execute(
        select(ProviderTrustScore, Provider)
        .join(Provider, Provider.id == ProviderTrustScore.provider_id)
        .order_by(ProviderTrustScore.trust_score.desc())
        .limit(limit)
    )

    rows = result.all()

    return [
        TrustScoreResponse(
            provider_id=str(score.provider_id),
            npi_number=provider.npi_number,
            trust_score=score.trust_score,
            rank=score.rank or 0,
            connections=score.connection_count
        )
        for score, provider in rows
    ]


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two points on Earth in kilometers
    Uses Haversine formula
    """
    R = 6371  # Earth radius in km

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat/2)**2 + \
        math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

    return R * c
