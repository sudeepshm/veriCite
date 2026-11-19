"""Deterministic API checks; no live provider requests or credentials needed."""
import unittest
from unittest.mock import patch, AsyncMock
import httpx
from fastapi.testclient import TestClient
from main import app
from integrations.providers import search_all

class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health(self):
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertIn('crossref', response.json()['providers'])

    def test_invalid_search(self):
        self.assertEqual(self.client.get('/api/evidence/search?q=a').status_code, 422)
        self.assertEqual(self.client.get('/api/evidence/search?q=learning&providers=wrong').status_code, 400)

    def test_open_access_timeout(self):
        with patch('main.open_access_lookup', new=AsyncMock(side_effect=httpx.ReadTimeout('timeout'))):
            response = self.client.get('/api/evidence/open-access?doi=10.1/test')
        self.assertEqual(response.status_code, 502)
        self.assertIn('retry', response.json()['detail'])

    def test_missing_configuration(self):
        with patch('main.open_access_lookup', new=AsyncMock(side_effect=ValueError('DOI must be provided'))):
            self.assertEqual(self.client.get('/api/evidence/open-access?doi=10.1/test').status_code, 400)

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_success_and_safe_errors(self):
        good = AsyncMock(return_value=[{'title':'Study','doi':'10.1/test'}])
        bad = AsyncMock(side_effect=httpx.ConnectError('URL contains api_key=secret'))
        with patch.dict('integrations.providers.SEARCH_PROVIDERS', {'good':good,'bad':bad}, clear=True):
            result = await search_all('learning', providers=['good','bad'])
        self.assertEqual(len(result['papers']),1)
        self.assertIn('bad',result['provider_errors'])
        self.assertNotIn('secret',str(result))

    async def test_semantic_scholar_zero_calls_on_primary_success(self):
        """When primary lookup succeeds, Semantic Scholar should receive zero calls."""
        primary_openalex = AsyncMock(return_value=[{'title': 'Primary Paper', 'doi': '10.1/test'}])
        primary_crossref = AsyncMock(return_value=[])
        fallback_s2 = AsyncMock(return_value=[{'title': 'S2 Paper', 'doi': '10.1/s2'}])
        with patch.dict('integrations.providers.PRIMARY_SEARCH_PROVIDERS', {'openalex': primary_openalex, 'crossref': primary_crossref}, clear=True), \
             patch.dict('integrations.providers.SEARCH_PROVIDERS', {'openalex': primary_openalex, 'crossref': primary_crossref, 'semantic_scholar': fallback_s2}, clear=True):
            result = await search_all('test query')
            self.assertEqual(len(result['papers']), 1)
            self.assertEqual(result['papers'][0]['title'], 'Primary Paper')
            fallback_s2.assert_not_called()

    async def test_open_access_fallback_retains_openalex_metadata(self):
        """Case 1: OpenAlex has metadata only, Semantic Scholar has the PDF -> return that PDF and retain OpenAlex metadata."""
        from integrations.providers import open_access_lookup
        mock_oa_data = {
            "doi": "https://doi.org/10.1234/test",
            "display_name": "Test Title From OpenAlex",
            "publication_year": 2024,
            "open_access": {"is_oa": False},
            "best_oa_location": {"pdf_url": None, "landing_page_url": "https://openalex.org/landing"},
        }
        mock_s2_data = {
            "url": "https://semanticscholar.org/paper/test",
            "openAccessPdf": {"url": "https://s2.org/download.pdf"},
        }

        async def fake_get_json(client, url, params=None, headers=None):
            if "openalex.org" in url:
                return mock_oa_data
            if "semanticscholar.org" in url:
                return mock_s2_data
            raise ValueError("Unknown URL")

        with patch("integrations.providers.get_json", side_effect=fake_get_json):
            async with httpx.AsyncClient() as client:
                res = await open_access_lookup(client, "10.1234/test")
                self.assertEqual(res["status"], "success")
                self.assertTrue(res["is_oa"])
                self.assertEqual(res["url_for_pdf"], "https://s2.org/download.pdf")
                self.assertEqual(res["url_for_landing_page"], "https://openalex.org/landing")
                self.assertEqual(res["source"], "openalex")

    async def test_open_access_both_fail_returns_lookup_failed(self):
        """Case 2: Both providers time out -> return lookup_failed with access status unknown."""
        from integrations.providers import open_access_lookup

        async def fake_timeout(client, url, params=None, headers=None):
            raise httpx.ReadTimeout("Timeout connecting to provider")

        with patch("integrations.providers.get_json", side_effect=fake_timeout):
            async with httpx.AsyncClient() as client:
                res = await open_access_lookup(client, "10.1234/test")
                self.assertEqual(res["status"], "lookup_failed")
                self.assertIsNone(res["is_oa"], "Access status must be unknown (None) on lookup failure")
                self.assertIsNone(res["url_for_pdf"])

if __name__ == '__main__':
    unittest.main()
