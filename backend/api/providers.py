"""Provider API endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
import json

from backend.database import get_db
from backend.models.provider import Provider, ProviderTrustScore
from backend.models.user import User
from backend.api.auth import get_current_user
from backend.integrations.npi import npi_client
from backend.integrations.geocode import geocoder
from backend.utils.security import compute_integrity_hash

router = APIRouter()


class ProviderResponse(BaseModel):
    id: str
    npi_number: str
    first_name: Optional[str]
    last_name: Optional[str]
    organization_name: Optional[str]
    taxonomy_description: Optional[str]
    city: Optional[str]
    state: Optional[str]
    latitude: Optional[float]
    longitude: Optional[float]
    trust_score: Optional[float]


@router.get("/{npi_number}", response_model=ProviderResponse)
async def get_provider(
    npi_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get provider by NPI number"""
    result = await db.execute(
        select(Provider).where(Provider.npi_number == npi_number)
    )
    provider = result.scalar_one_or_none()

    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    # Get trust score if available
    trust_result = await db.execute(
        select(ProviderTrustScore).where(
            ProviderTrustScore.provider_id == provider.id
        )
    )
    trust_score = trust_result.scalar_one_or_none()

    return ProviderResponse(
        id=str(provider.id),
        npi_number=provider.npi_number,
        first_name=provider.first_name,
        last_name=provider.last_name,
        organization_name=provider.organization_name,
        taxonomy_description=provider.taxonomy_description,
        city=provider.city,
        state=provider.state,
        latitude=provider.latitude,
        longitude=provider.longitude,
        trust_score=trust_score.trust_score if trust_score else None
    )


@router.post("/lookup/{npi_number}", response_model=ProviderResponse)
async def lookup_and_store_provider(
    npi_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Lookup provider from NPI registry and store"""
    # Check if already exists
    result = await db.execute(
        select(Provider).where(Provider.npi_number == npi_number)
    )
    existing = result.scalar_one_or_none()

    if existing:
        return ProviderResponse(
            id=str(existing.id),
            npi_number=existing.npi_number,
            first_name=existing.first_name,
            last_name=existing.last_name,
            organization_name=existing.organization_name,
            taxonomy_description=existing.taxonomy_description,
            city=existing.city,
            state=existing.state,
            latitude=existing.latitude,
            longitude=existing.longitude,
            trust_score=None
        )

    # Lookup from NPI registry
    npi_data = await npi_client.lookup_npi(npi_number)

    if not npi_data:
        raise HTTPException(status_code=404, detail="NPI not found in registry")

    # Parse data
    parsed = npi_client.parse_provider_data(npi_data)

    # Geocode
    coords = None
    if parsed.get("address_line_1"):
        try:
            coords = await geocoder.geocode(
                address=parsed["address_line_1"],
                city=parsed.get("city"),
                state=parsed.get("state"),
                postal_code=parsed.get("postal_code")
            )
        except Exception:
            pass

    if coords:
        parsed["latitude"] = coords[0]
        parsed["longitude"] = coords[1]

    # Compute integrity hash
    raw_json = json.dumps(parsed["raw_data"], sort_keys=True)
    integrity_hash = compute_integrity_hash(raw_json)

    # Create provider
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
        integrity_hash=integrity_hash
    )

    db.add(provider)
    await db.commit()
    await db.refresh(provider)

    return ProviderResponse(
        id=str(provider.id),
        npi_number=provider.npi_number,
        first_name=provider.first_name,
        last_name=provider.last_name,
        organization_name=provider.organization_name,
        taxonomy_description=provider.taxonomy_description,
        city=provider.city,
        state=provider.state,
        latitude=provider.latitude,
        longitude=provider.longitude,
        trust_score=None
    )


@router.get("/search/by-location")
async def search_providers_by_location(
    latitude: float,
    longitude: float,
    radius_km: float = 50,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search providers near location"""
    # Simple bounding box search
    # For production, use PostGIS or more sophisticated geo queries
    lat_delta = radius_km / 111.0  # rough km to degree
    lon_delta = radius_km / (111.0 * abs(latitude / 90.0 + 0.1))

    result = await db.execute(
        select(Provider).where(
            (Provider.latitude >= latitude - lat_delta) &
            (Provider.latitude <= latitude + lat_delta) &
            (Provider.longitude >= longitude - lon_delta) &
            (Provider.longitude <= longitude + lon_delta)
        ).limit(limit)
    )

    providers = result.scalars().all()

    return [
        ProviderResponse(
            id=str(p.id),
            npi_number=p.npi_number,
            first_name=p.first_name,
            last_name=p.last_name,
            organization_name=p.organization_name,
            taxonomy_description=p.taxonomy_description,
            city=p.city,
            state=p.state,
            latitude=p.latitude,
            longitude=p.longitude,
            trust_score=None
        )
        for p in providers
    ]
