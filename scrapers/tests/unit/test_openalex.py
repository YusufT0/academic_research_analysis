import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.openalex.client import OpenAlexClient, OpenAlexAPIError
from backend.services.openalex.citation_service import CitationService
from database.models import Article, Journal

@pytest.fixture
def openalex_client():
    client = OpenAlexClient()
    # Replace the internal httpx client get method with a mock
    client.client.get = AsyncMock()
    return client

@pytest.fixture
def citation_service():
    return CitationService()

@pytest.mark.asyncio
async def test_openalex_get_works_by_dois_success(openalex_client):
    # Mocking successful API response for a DOI
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "doi": "https://doi.org/10.1234/test",
                "id": "W123456",
                "cited_by_count": 42,
                "counts_by_year": [{"year": 2023, "cited_by_count": 20}, {"year": 2024, "cited_by_count": 22}],
                "fwci": 1.5,
                "percentile_year": {"value": 90.5}
            }
        ]
    }
    openalex_client.client.get.return_value = mock_response

    dois = ["10.1234/test"]
    results = await openalex_client.get_works_by_dois(dois)

    assert len(results) == 1
    assert results[0]["cited_by_count"] == 42
    assert results[0]["id"] == "W123456"
    assert results[0]["fwci"] == 1.5

@pytest.mark.asyncio
async def test_openalex_get_source_by_identifier(openalex_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "id": "S987654",
                "summary_stats": {
                    "h_index": 50,
                    "i10_index": 120
                },
                "cited_by_count": 5000,
                "works_count": 1000
            }
        ]
    }
    openalex_client.client.get.return_value = mock_response

    result = await openalex_client.get_source_by_identifier(name="Test Journal")
    
    assert result is not None
    assert result["id"] == "S987654"
    assert result["summary_stats"]["h_index"] == 50

@pytest.mark.asyncio
@patch("backend.services.openalex.citation_service.openalex_client")
async def test_update_articles_citations_bulk(mock_openalex_client, citation_service):
    # Mock OpenAlex results
    mock_openalex_client.get_works_by_dois = AsyncMock(return_value=[
        {
            "doi": "https://doi.org/10.1000/182",
            "id": "W123",
            "cited_by_count": 10,
            "fwci": 1.0,
            "counts_by_year": [{"year": 2023, "cited_by_count": 10}],
            "cited_by_percentile_year": {"min": 85.0, "max": 90.0}
        }
    ])

    # Create a mock article wrapper since Beanie requires DB context for true models
    mock_article = MagicMock(spec=Article)
    mock_article.doi = "10.1000/182"
    mock_article.save = AsyncMock()

    updated_count = await citation_service.update_articles_citations_bulk([mock_article])

    # Assertions
    assert updated_count == 1
    assert mock_article.openalex_id == "W123"
    assert mock_article.is_openalex_indexed is True
    assert mock_article.citation_count == 10
    assert mock_article.fwci == 1.0
    assert mock_article.citation_percentile == 85.0
    # ensure it mapped {"year": 2023, ...} to {"2023": 10}
    assert mock_article.historical_citation_data == {"2023": 10}
    mock_article.save.assert_awaited_once()

@pytest.mark.asyncio
@patch("backend.services.openalex.citation_service.openalex_client")
async def test_update_journal_citation_metrics(mock_openalex_client, citation_service):
    # Mock OpenAlex source result
    mock_openalex_client.get_source_by_identifier = AsyncMock(return_value={
        "id": "S999",
        "summary_stats": {
            "h_index": 20,
            "i10_index": 45
        },
        "cited_by_count": 1000,
        "works_count": 100,
        "counts_by_year": [{"year": 2022, "cited_by_count": 200}]
    })

    mock_journal = MagicMock(spec=Journal)
    mock_journal.issn = "1234-5678"
    mock_journal.name = "Mock Journal"
    mock_journal.save = AsyncMock()

    success = await citation_service.update_journal_citation_metrics(mock_journal)

    assert success is True
    assert mock_journal.h_index == 20
    assert mock_journal.i10_index == 45
    assert mock_journal.total_citation_count == 1000
    assert mock_journal.average_citation_count == 10.0 # 1000 / 100
    assert mock_journal.historical_citation_data == {"2022": 200}
    mock_journal.save.assert_awaited_once()
