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

    def test_claims_endpoint_matches_job_report_claims(self):
        """Ensure /api/verify/{job_id}/claims returns the same claim IDs as the completed job report."""
        import asyncio
        from app.pipeline import create_job, run_pipeline
        from app.database import get_job

        fixture = """Study findings
Accuracy rose from 50% to 60% in the adult pilot [1].

References
[1] Rao, M. (2025). Classification accuracy in an adult pilot. Fixture Studies, 1, 1.
"""
        job = create_job("test_claims.txt", "text/plain")
        asyncio.run(
            run_pipeline(
                job.job_id,
                fixture.encode("utf-8"),
                "test_claims.txt",
                "text/plain",
                test_resolver={"[1]": "source-1.txt", "1": "source-1.txt"},
            )
        )
        completed = get_job(job.job_id)
        self.assertIsNotNone(completed.report)
        report_claim_ids = [c["claim_id"] for c in completed.report["claims"]]

        res = self.client.get(f"/api/verify/{job.job_id}/claims")
        self.assertEqual(res.status_code, 200)
        api_claim_ids = [c["claim_id"] for c in res.json().get("claims", [])]

        self.assertGreater(len(report_claim_ids), 0, "Report must contain claims")
        self.assertEqual(set(api_claim_ids), set(report_claim_ids), "Claims route must return same claim IDs as report")

class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_partial_success_and_safe_errors(self):
        good = AsyncMock(return_value=[{'title':'Study','doi':'10.1/test'}])
        bad = AsyncMock(side_effect=httpx.ConnectError('URL contains api_key=secret'))
        with patch.dict('integrations.providers.SEARCH_PROVIDERS', {'good':good,'bad':bad}, clear=True):
            result = await search_all('learning', providers=['good','bad'])
        self.assertEqual(len(result['papers']),1)
        self.assertIn('bad',result['provider_errors'])
        self.assertNotIn('secret',str(result))

    async def test_crossref_only_search(self):
        """In Crossref-only mode, only Crossref is queried."""
        primary_crossref = AsyncMock(return_value=[{'title': 'Crossref Paper', 'doi': '10.1/crossref', 'source': 'crossref'}])
        with patch.dict('integrations.providers.SEARCH_PROVIDERS', {'crossref': primary_crossref}, clear=True):
            result = await search_all('test query')
            self.assertEqual(len(result['papers']), 1)
            self.assertEqual(result['papers'][0]['title'], 'Crossref Paper')
            primary_crossref.assert_called_once()

    async def test_open_access_crossref_link(self):
        """Crossref open access extracts direct link from item.link."""
        from integrations.providers import open_access_lookup
        mock_cr_data = {
            "message": {
                "DOI": "10.1234/test",
                "URL": "https://doi.org/10.1234/test",
                "link": [{"URL": "https://publisher.com/paper.pdf", "content-type": "application/pdf"}],
            }
        }

        async def fake_get_json(client, url, params=None, headers=None):
            if "api.crossref.org" in url:
                return mock_cr_data
            raise ValueError(f"Unknown URL {url}")

        with patch("integrations.providers.get_json", side_effect=fake_get_json):
            async with httpx.AsyncClient() as client:
                res = await open_access_lookup(client, "10.1234/test")
                self.assertEqual(res["status"], "success")
                self.assertTrue(res["is_oa"])
                self.assertEqual(res["url_for_pdf"], "https://publisher.com/paper.pdf")
                self.assertEqual(res["url_for_landing_page"], "https://doi.org/10.1234/test")
                self.assertEqual(res["source"], "crossref")

    async def test_open_access_timeout_returns_lookup_failed(self):
        """Crossref timeout returns lookup_failed with access status unknown."""
        from integrations.providers import open_access_lookup

        async def fake_timeout(client, url, params=None, headers=None):
            raise httpx.ReadTimeout("Timeout connecting to Crossref")

        with patch("integrations.providers.get_json", side_effect=fake_timeout):
            async with httpx.AsyncClient() as client:
                res = await open_access_lookup(client, "10.1234/test")
                self.assertEqual(res["status"], "lookup_failed")
                self.assertIsNone(res["is_oa"], "Access status must be unknown (None) on lookup failure")
                self.assertIsNone(res["url_for_pdf"])

if __name__ == '__main__':
    unittest.main()
