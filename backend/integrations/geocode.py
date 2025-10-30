"""
Geocoding Integration using Nominatim (OpenStreetMap)
Free and open-source - no API key required
Rate limit: 1 request/second per their usage policy
"""
import httpx
import asyncio
from typing import Optional, Tuple, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from datetime import datetime, timedelta

from backend.config import settings

logger = logging.getLogger(__name__)


class NominatimGeocoder:
    """
    Nominatim geocoder using OpenStreetMap data
    Free to use with proper attribution and rate limiting
    https://nominatim.openstreetmap.org/
    """

    def __init__(self):
        self.base_url = settings.NOMINATIM_BASE_URL
        self.user_agent = settings.NOMINATIM_USER_AGENT
        self.rate_limit = settings.NOMINATIM_RATE_LIMIT_SECONDS
        self.last_request_time = None
        self.cache: Dict[str, tuple[Optional[Tuple[float, float]], datetime]] = {}
        self.cache_ttl = timedelta(days=30)  # Coordinates don't change often

    async def _rate_limit(self):
        """
        Implement rate limiting per Nominatim usage policy
        Requirement: max 1 request per second
        """
        if self.last_request_time:
            elapsed = (datetime.utcnow() - self.last_request_time).total_seconds()
            if elapsed < self.rate_limit:
                await asyncio.sleep(self.rate_limit - elapsed)

        self.last_request_time = datetime.utcnow()

    def _cache_key(self, address: str) -> str:
        """Generate cache key from address"""
        return address.lower().strip()

    def _get_cached(self, address: str) -> Optional[Tuple[float, float]]:
        """Get cached coordinates if valid"""
        key = self._cache_key(address)
        if key in self.cache:
            coords, cached_at = self.cache[key]
            if datetime.utcnow() - cached_at < self.cache_ttl:
                logger.info(f"Geocoding cache hit for {address}")
                return coords

        return None

    def _set_cache(self, address: str, coords: Optional[Tuple[float, float]]):
        """Cache coordinates"""
        key = self._cache_key(address)
        self.cache[key] = (coords, datetime.utcnow())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def geocode(
        self,
        address: str,
        city: Optional[str] = None,
        state: Optional[str] = None,
        postal_code: Optional[str] = None,
        country: str = "US"
    ) -> Optional[Tuple[float, float]]:
        """
        Geocode address to (latitude, longitude)
        Returns None if geocoding fails
        """
        # Build search query
        query_parts = []
        if address:
            query_parts.append(address)
        if city:
            query_parts.append(city)
        if state:
            query_parts.append(state)
        if postal_code:
            query_parts.append(postal_code)
        if country:
            query_parts.append(country)

        query = ", ".join(query_parts)

        # Check cache
        cached = self._get_cached(query)
        if cached is not None:
            return cached

        # Rate limit
        await self._rate_limit()

        # Make request
        url = f"{self.base_url}/search"
        params = {
            "q": query,
            "format": "json",
            "limit": 1,
            "addressdetails": 1,
        }

        headers = {
            "User-Agent": self.user_agent
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Geocoding: {query}")
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()

                results = response.json()

                if not results:
                    logger.warning(f"No geocoding results for: {query}")
                    self._set_cache(query, None)
                    return None

                result = results[0]
                lat = float(result["lat"])
                lon = float(result["lon"])

                logger.info(f"Geocoded {query} -> ({lat}, {lon})")

                # Cache result
                self._set_cache(query, (lat, lon))

                return (lat, lon)

        except httpx.HTTPError as e:
            logger.error(f"HTTP error geocoding {query}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error geocoding {query}: {e}")
            raise

    async def reverse_geocode(
        self,
        latitude: float,
        longitude: float
    ) -> Optional[Dict[str, Any]]:
        """
        Reverse geocode coordinates to address
        """
        await self._rate_limit()

        url = f"{self.base_url}/reverse"
        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "json",
            "addressdetails": 1,
        }

        headers = {
            "User-Agent": self.user_agent
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                logger.info(f"Reverse geocoding: ({latitude}, {longitude})")
                response = await client.get(url, params=params, headers=headers)
                response.raise_for_status()

                result = response.json()
                logger.info(f"Reverse geocoded ({latitude}, {longitude})")

                return result.get("address")

        except httpx.HTTPError as e:
            logger.error(f"HTTP error reverse geocoding: {e}")
            raise
        except Exception as e:
            logger.error(f"Error reverse geocoding: {e}")
            raise


# Global singleton
geocoder = NominatimGeocoder()
