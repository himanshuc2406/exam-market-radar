import unittest
from unittest.mock import patch

import app as webapp


class MarketRadarEndpointTests(unittest.TestCase):
    def setUp(self):
        webapp.app.config.update(TESTING=True)
        webapp.RADAR_CACHE.clear()
        self.client = webapp.app.test_client()

    @patch("app.store.count_questions_for_topic", return_value=7)
    @patch("app.store.init")
    @patch("app.yt.video_comments")
    @patch("app.yt.search_videos")
    @patch("app._key", return_value="test-key")
    def test_scan_returns_ranked_action(self, _key, search, comments, _init, _count):
        search.return_value = [{
            "video_id": "abc12345678", "title": "Percentage questions",
            "published_at": "2026-08-28T10:00:00Z", "views": 12000,
            "engagement": 4.2, "channel_id": "UC123", "channel_title": "Competitor",
            "url": "https://www.youtube.com/watch?v=abc12345678",
        }]
        comments.return_value = [
            {"text": "Sir percentage decrease kaise solve kare?", "likes": 8},
            {"text": "Please make a test on percentage", "likes": 5},
        ]
        response = self.client.post("/api/market-radar", json={
            "exam": "SSC CGL", "subject": "quant", "days": 30,
            "custom_topics": "Percentage",
        })
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        top = payload["data"]["opportunities"][0]
        self.assertEqual(top["topic"], "Percentage")
        self.assertIn("recommendation", top)
        self.assertEqual(top["top_videos"][0]["url"],
                         "https://www.youtube.com/watch?v=abc12345678")

    @patch("app.store.qbank_stats", return_value={"total": 1})
    @patch("app.store.add_questions", return_value=(1, 0))
    @patch("app.store.init")
    def test_generated_questions_are_saved_as_review_drafts(self, _init, add, _stats):
        response = self.client.post("/api/qbank/save-generated", json={
            "exam": "SSC CGL",
            "source_topic": "Percentage market opportunity",
            "questions": [{
                "question": "What is 20% of 250?",
                "options": ["40", "50", "60", "70"],
                "answer_index": 1,
                "topic": "Percentage",
                "difficulty": "easy",
            }],
        })
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        saved = add.call_args.args[0][0]
        self.assertEqual(saved["review_status"], "draft")
        self.assertEqual(saved["exam"], "SSC CGL")

    @patch("app.store.count_questions_for_topic", return_value=0)
    @patch("app.store.init")
    @patch("app.yt.video_comments", return_value=[])
    @patch("app.yt.search_videos")
    @patch("app._key", return_value="test-key")
    def test_repeat_scan_uses_cache_without_more_quota(self, _key, search, _comments,
                                                       _init, _count):
        search.return_value = [{
            "video_id": "abc12345678", "title": "Percentage questions",
            "published_at": "2026-08-28T10:00:00Z", "views": 1000,
            "engagement": 2.0, "channel_id": "UC123", "channel_title": "Example",
            "url": "https://www.youtube.com/watch?v=abc12345678",
        }]
        body = {"exam": "Banking", "subject": "quant", "days": 30,
                "scan_mode": "quick", "custom_topics": "Percentage"}
        first = self.client.post("/api/market-radar", json=body).get_json()["data"]
        second = self.client.post("/api/market-radar", json=body).get_json()["data"]
        self.assertFalse(first["cache_hit"])
        self.assertTrue(second["cache_hit"])
        self.assertGreater(first["quota_estimate"], 0)
        self.assertEqual(second["quota_estimate"], 0)
        self.assertEqual(search.call_count, 1)

    @patch("app.store.clear_qbank")
    @patch("app.store.init")
    def test_page_refresh_starts_a_fresh_review_bank(self, init, clear):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        init.assert_called_once()
        clear.assert_called_once()

    @patch("app.exports.build_question_bank_xlsx", return_value=b"PK-export")
    @patch("app.store.list_questions", return_value=[{"question": "Example"}])
    @patch("app.store.init")
    def test_excel_download_endpoint(self, _init, _list, _build):
        response = self.client.get("/api/qbank/export/xlsx?topic=Percentage")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"PK-export")
        self.assertIn(".xlsx", response.headers["Content-Disposition"])

    @patch("app.exports.build_question_bank_pdf", return_value=b"%PDF-export")
    @patch("app.store.list_questions", return_value=[{"question": "Example"}])
    @patch("app.store.init")
    def test_pdf_download_endpoint(self, _init, _list, _build):
        response = self.client.get("/api/qbank/export/pdf?difficulty=medium")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"%PDF-export")
        self.assertIn(".pdf", response.headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
