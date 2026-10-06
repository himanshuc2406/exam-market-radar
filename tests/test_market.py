import unittest
from datetime import datetime, timezone, timedelta

from core import market


class MarketRadarTests(unittest.TestCase):
    def test_default_plan_is_quota_conscious_and_balanced(self):
        topics = market.topic_plan("SSC CGL", "both")
        self.assertEqual(len(topics), 8)
        self.assertIn("Percentage", topics)
        self.assertIn("Coding Decoding", topics)

    def test_banking_scan_depth_expands_topic_coverage(self):
        quick = market.topic_plan("Banking", "quant", limit=4)
        standard = market.topic_plan("Banking", "quant", limit=8)
        deep = market.topic_plan("Banking", "quant", limit=12)
        self.assertEqual((len(quick), len(standard), len(deep)), (4, 8, 12))
        self.assertIn("Data Interpretation", quick)
        self.assertIn("Ratio and Proportion", standard)
        self.assertIn("Arithmetic Word Problems", deep)

    def test_custom_topics_are_deduped_and_limited(self):
        topics = market.topic_plan("SSC CGL", "both", "Percentage, Percentage; Puzzles")
        self.assertEqual(topics, ["Percentage", "Puzzles"])

    def test_deep_demo_contains_twelve_topics(self):
        result = market.demo_scan("Banking", limit=12)
        self.assertEqual(len(result["opportunities"]), 12)
        self.assertEqual(len(result["topics"]), 12)

    def test_views_are_normalized_by_video_age(self):
        now = datetime(2026, 8, 30, tzinfo=timezone.utc)
        videos = [{
            "title": "Example", "views": 1000,
            "published_at": (now - timedelta(days=10)).isoformat(),
        }]
        row = market.enrich_videos(videos, now=now)[0]
        self.assertEqual(row["views_per_day"], 100)

    def test_known_channel_coverage_is_detected(self):
        result = market.own_coverage("Ratio and Proportion", [
            {"title": "Ratio and Proportion Complete Class"},
            {"title": "Number Series"},
        ])
        self.assertTrue(result["known"])
        self.assertEqual(result["count"], 1)

    def test_high_doubts_recommend_diagnostic_quiz(self):
        row = {
            "doubt_count": 12, "request_count": 2, "market_heat": 80,
            "inventory": 50, "own_coverage": {"known": True, "count": 2},
            "score_components": {"doubts": 100},
        }
        result = market.recommend_product(row, exam_days=60)
        self.assertEqual(result["product"], "Misconception Diagnostic Quiz")

    def test_close_exam_overrides_with_revision_mock(self):
        row = {
            "doubt_count": 12, "request_count": 2, "market_heat": 80,
            "inventory": 50, "own_coverage": {"known": True, "count": 0},
        }
        result = market.recommend_product(row, exam_days=10)
        self.assertEqual(result["product"], "Rapid Revision Mini Mock")

    def test_ranked_output_contains_explainable_scores(self):
        signals = [
            {"topic": "Percentage", "avg_views_per_day": 5000, "doubt_count": 20,
             "request_count": 8, "outlier_ratio": 5, "avg_engagement": 4,
             "channel_count": 3, "own_coverage": {"known": True, "count": 0},
             "inventory": 0},
            {"topic": "Analogy", "avg_views_per_day": 100, "doubt_count": 1,
             "request_count": 0, "outlier_ratio": 1, "avg_engagement": 1,
             "channel_count": 5, "own_coverage": {"known": True, "count": 3},
             "inventory": 50},
        ]
        ranked = market.rank_signals(signals, exam_days=45)
        self.assertEqual(ranked[0]["topic"], "Percentage")
        self.assertIn("score_components", ranked[0])
        self.assertIn("recommendation", ranked[0])


if __name__ == "__main__":
    unittest.main()
