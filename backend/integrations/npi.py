"""
NPI Registry Integration
Uses free public CMS NPI Registry API: https://npiregistry.cms.hhs.gov/api/
"""
import httpx
import asyncio
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from datetime import datetime, timedelta

from backend.config import settings

logger = logging.getLogger(__name__)


class NPIRegistryClient:
    """Client for NPI Registry API with caching and rate limiting"""

    def __init__(self):
        self.base_url = settings.NPI_REGISTRY_BASE_URL
        self.rate_limit = settings.NPI_RATE_LIMIT_SECONDS
        self.last_request_time = None
        self.cache: Dict[str, tuple[Dict[Any, Any], datetime]] = {}
        self.cache_ttl = timedelta(hours=24)

    async def _rate_limit(self):
        """Implement rate limiting"""
        if self.last_request_time:
            elapsed = (datetime.utcnow() - self.last_request_time).total_seconds()
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)

        self.last_request_time = datetime.utcnow()

    def _get_cached(self, npi_number: str) -> Optional[Dict[Any, Any]]:
        """Get cached result if valid"""
        if npi_number in self.cache:
            data, cached_at = self.cache[npi_number]
            if datetime.utcnow() - cached_at < self.cache_ttl:
                logger.info(f"Cache hit for NPI {npi_number}")
                return data

        return None

    def _set_cache(self, npi_number: str, data: Dict[Any, Any]):
        """Cache result"""
        self.cache[npi_number] = (data, datetime.utcnow())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def lookup_npi(self, npi_number: str) -> Optional[Dict[Any, Any]]:
        """
        Lookup provider by NPI number
        Free public API - no authentication required
        """
        # Check cache first
        cached = self._get_cached(npi_number)
        if cached:
            return cached

        # Rate limit
        await self._rate_limit()

        # Make request
        url = f"{self.base_url}?number={npi_number}&version=2.1"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Fetching NPI data for {npi_number}")
                response = await client.get(url)
                response.raise_for_status()

                data = response.json()

                # Check if results found
                if data.get("result_count", 0) == 0:
                    logger.warning(f"No results found for NPI {npi_number}")
                    return None

                result = data["results"][0]

                # Cache result
                self._set_cache(npi_number, result)

                logger.info(f"Successfully fetched NPI {npi_number}")
                return result

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching NPI {npi_number}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching NPI {npi_number}: {e}")
            raise

    def parse_provider_data(self, npi_data: Dict[Any, Any]) -> Dict[str, Any]:
        """
        Parse NPI registry response into structured format
        Maps complex NPI JSON to our Provider model fields
        """
        basic = npi_data.get("basic", {})
        addresses = npi_data.get("addresses", [])
        taxonomies = npi_data.get("taxonomies", [])

        # Get primary practice location
        practice_location = None
        for addr in addresses:
            if addr.get("address_purpose") == "LOCATION":
                practice_location = addr
                break

        if not practice_location and addresses:
            practice_location = addresses[0]

        # Get primary taxonomy
        primary_taxonomy = None
        for tax in taxonomies:
            if tax.get("primary"):
                primary_taxonomy = tax
                break

        if not primary_taxonomy and taxonomies:
            primary_taxonomy = taxonomies[0]

        return {
            "npi_number": npi_data.get("number"),
            "first_name": basic.get("first_name"),
            "last_name": basic.get("last_name"),
            "organization_name": basic.get("organization_name"),
            "taxonomy_code": primary_taxonomy.get("code") if primary_taxonomy else None,
            "taxonomy_description": primary_taxonomy.get("desc") if primary_taxonomy else None,
            "address_line_1": practice_location.get("address_1") if practice_location else None,
            "address_line_2": practice_location.get("address_2") if practice_location else None,
            "city": practice_location.get("city") if practice_location else None,
            "state": practice_location.get("state") if practice_location else None,
            "postal_code": practice_location.get("postal_code") if practice_location else None,
            "country": practice_location.get("country_code", "US") if practice_location else "US",
            "phone": practice_location.get("telephone_number") if practice_location else None,
            "fax": practice_location.get("fax_number") if practice_location else None,
            "raw_data": npi_data,
        }


# Global singleton
npi_client = NPIRegistryClient()
