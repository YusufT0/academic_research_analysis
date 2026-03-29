import asyncio
import logging
import re
from typing import List, Dict, Any, Optional
import httpx
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

from backend.core.config import settings

logger = logging.getLogger(__name__)

class OpenAlexRateLimitError(Exception):
    """OpenAlex API Rate Limit Exception"""
    pass

class OpenAlexAPIError(Exception):
    """OpenAlex General API Exception"""
    pass


class OpenAlexClient:
    """
    OpenAlex API HTTP Client
    Handles rate limiting, connection pooling, retries, and chunking.
    Designed for reliability and performance.
    """

    def __init__(self):
        self.base_url = settings.openalex_api_base_url.rstrip("/")
        self.timeout = settings.openalex_api_timeout
        self.chunk_size = settings.openalex_bulk_chunk_size
        
        # Setup headers
        self.headers = {"Accept": "application/json"}
        if settings.openalex_polite_email:
            self.headers["mailto"] = settings.openalex_polite_email
            
        # Using a custom limits configuration to prevent saturating our connection and OpenAlex
        limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=self.timeout,
            limits=limits
        )

    async def close(self):
        """Close the internal HTTP client."""
        await self.client.aclose()

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.RequestError, OpenAlexRateLimitError)),
        reraise=True
    )
    async def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Internal request maker with automatic retries on network failures or rate limits.
        """
        try:
            response = await self.client.get(endpoint, params=params)
            
            if response.status_code == 429:
                logger.warning("OpenAlex API Rate Limit hit. Retrying...")
                raise OpenAlexRateLimitError("Rate limit exceeded")
                
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"OpenAlex API HTTP Error: {e.response.status_code} - {e.response.text}")
            raise OpenAlexAPIError(f"HTTP Error {e.response.status_code}") from e
        except httpx.RequestError as e:
            logger.error(f"OpenAlex Request Error: {e}")
            raise

    async def get_works_by_dois(self, dois: List[str]) -> List[Dict[str, Any]]:
        """
        Fetch articles (works) in bulk using their DOIs.
        Splits into chunks automatically.
        """
        all_results = []
        
        # Clean DOIs — strip any number of doi.org URL prefixes (handles double-prefix like https://doi.org/https://doi.org/10.xxx)
        clean_dois = [re.sub(r'^(https?://doi\.org/)+', '', doi.strip()) for doi in dois if doi]
        
        for i in range(0, len(clean_dois), self.chunk_size):
            chunk = clean_dois[i:i + self.chunk_size]
            # OpenAlex expects multiple values for the SAME filter separated by pipe:
            # works?filter=doi:10.123|10.456
            doi_list_str = "|".join(chunk)
            doi_filter = f"doi:{doi_list_str}"
            
            params = {
                "filter": doi_filter,
                "per-page": self.chunk_size,
                "select": "id,doi,cited_by_count,counts_by_year,fwci,cited_by_percentile_year"
            }
            
            try:
                data = await self._make_request("/works", params=params)
                if "results" in data:
                    all_results.extend(data["results"])
            except Exception as e:
                logger.error(f"Failed to fetch OpenAlex data for chunk starting with {chunk[0]}: {e}")
                continue
                
        return all_results

    async def get_citing_works(
        self,
        openalex_id: str,
        per_page: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Verilen OpenAlex ID'sini cite eden çalışmaları getir.
        GET /works?filter=cites:{openalex_id}&sort=cited_by_count:desc
        Atıf sayısına göre azalan sırada döner (en etkili cite'lar önce).
        """
        params = {
            "filter": f"cites:{openalex_id}",
            "per-page": min(per_page, 50),
            "select": "id,doi,title,cited_by_count,publication_year",
            "sort": "cited_by_count:desc",
        }
        try:
            data = await self._make_request("/works", params=params)
            return data.get("results", [])
        except Exception as e:
            logger.error(f"get_citing_works failed for {openalex_id}: {e}")
            return []

    async def get_source_by_identifier(self, issn: str = None, name: str = None) -> Optional[Dict[str, Any]]:
        """
        Fetch journal (source) data by ISSN or Name.
        """
        params = {}
        if issn:
            params["filter"] = f"issn:{issn}"
        elif name:
            params["search"] = name
        else:
            return None
            
        try:
            data = await self._make_request("/sources", params=params)
            results = data.get("results", [])
            if results:
                # Get the absolute most relevant source (first result)
                return results[0]
        except Exception as e:
            logger.error(f"Failed to fetch OpenAlex source (issn={issn}, name={name}): {e}")
            
        return None

# Provide a singleton instance
openalex_client = OpenAlexClient()
