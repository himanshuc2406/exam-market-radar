"""Market-radar scoring and test-product recommendations.

The functions in this module are intentionally deterministic: YouTube supplies
public signals, while this layer explains exactly how those signals become an
action.  It does not claim to measure YouTube search volume.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone


TOPIC_BASKETS = {
    "ssc": {
        "quant": [
            "Percentage", "Profit and Loss", "Ratio and Proportion", "Time and Work",
            "Time Speed Distance", "Simple and Compound Interest", "Average", "Number System",
            "Algebra", "Geometry", "Mensuration", "Trigonometry",
        ],
        "reasoning": [
            "Coding Decoding", "Number Series", "Analogy", "Syllogism",
            "Classification", "Blood Relation", "Direction Sense", "Ranking",
            "Venn Diagram", "Calendar and Clock", "Non Verbal Reasoning", "Statement Conclusion",
        ],
    },
    "banking": {
        "quant": [
            "Data Interpretation", "Simplification and Approximation", "Number Series",
            "Quadratic Equation", "Percentage", "Profit and Loss", "Ratio and Proportion",
            "Time and Work", "Time Speed Distance", "Simple and Compound Interest",
            "Partnership", "Arithmetic Word Problems",
        ],
        "reasoning": [
            "Puzzles", "Seating Arrangement", "Syllogism", "Coded Inequality",
            "Coding Decoding", "Blood Relation", "Direction and Distance", "Order and Ranking",
            "Input Output", "Data Sufficiency", "Logical Reasoning", "Alphanumeric Series",
        ],
    },
    "railway": {
        "quant": [
            "Number System", "Simplification", "Percentage", "Ratio and Proportion",
            "Profit and Loss", "Time and Work", "Time Speed Distance", "Simple Interest",
            "Algebra", "Geometry", "Mensuration", "Data Interpretation",
        ],
        "reasoning": [
            "Coding Decoding", "Blood Relation", "Number and Alphabet Series", "Direction Sense",
            "Analogy", "Classification", "Syllogism", "Venn Diagram", "Ranking",
            "Mathematical Operations", "Calendar and Clock", "Non Verbal Reasoning",
        ],
    },
    "defence": {
        "quant": [
            "Algebra", "Trigonometry", "Geometry", "Mensuration", "Statistics",
            "Probability", "Matrices and Determinants", "Calculus", "Number System",
            "Percentage", "Time Speed Distance", "Data Interpretation",
        ],
        "reasoning": [
            "Non Verbal Reasoning", "Analogy", "Series", "Spatial Reasoning",
            "Coding Decoding", "Blood Relation", "Direction Sense", "Syllogism",
            "Classification", "Venn Diagram", "Statement Conclusion", "Logical Reasoning",
        ],
    },
    "teaching": {
        "quant": [
            "Number System", "Simplification", "Percentage", "Ratio and Proportion",
            "Profit and Loss", "Average", "Time and Work", "Time Speed Distance",
            "Algebra", "Geometry", "Mensuration", "Data Interpretation",
        ],
        "reasoning": [
            "Logical Reasoning", "Syllogism", "Coding Decoding", "Series", "Analogy",
            "Classification", "Blood Relation", "Direction Sense", "Ranking",
            "Venn Diagram", "Statement Conclusion", "Non Verbal Reasoning",
        ],
    },
    "general": {
        "quant": [
            "Percentage", "Ratio and Proportion", "Profit and Loss", "Average",
            "Time and Work", "Time Speed Distance", "Simple and Compound Interest",
            "Number System", "Algebra", "Geometry", "Mensuration", "Data Interpretation",
        ],
        "reasoning": [
            "Seating Arrangement", "Puzzles", "Coding Decoding", "Syllogism", "Series",
            "Analogy", "Blood Relation", "Direction Sense", "Ranking", "Venn Diagram",
            "Statement Conclusion", "Non Verbal Reasoning",
        ],
    },
}


def _exam_key(exam):
    text = (exam or "").lower()
    if any(x in text for x in ("ssc", "cgl", "chsl", "cpo", "mts")):
        return "ssc"
    if any(x in text for x in ("bank", "sbi", "ibps", "rrb po", "clerk")):
        return "banking"
    if any(x in text for x in ("rail", "rrb ntpc", "group d")):
        return "railway"
    if any(x in text for x in ("defence", "nda", "cds", "afcat")):
        return "defence"
    if any(x in text for x in ("teaching", "ctet", "tet", "dsssb")):
        return "teaching"
    return "general"


def topic_plan(exam, subject="both", custom_topics=None, limit=8):
    """Return a compact, quota-conscious topic basket for one scan."""
    custom = []
    if isinstance(custom_topics, str):
        custom = [x.strip() for x in re.split(r"[,\n;]+", custom_topics) if x.strip()]
    elif custom_topics:
        custom = [str(x).strip() for x in custom_topics if str(x).strip()]
    if custom:
        return list(dict.fromkeys(custom))[:limit]

    basket = TOPIC_BASKETS[_exam_key(exam)]
    subject = (subject or "both").lower()
    if subject == "quant":
        return basket["quant"][:limit]
    if subject == "reasoning":
        return basket["reasoning"][:limit]
    # Balance a combined-team scan across Quant and Reasoning.
    quant_n = (limit + 1) // 2
    reasoning_n = limit // 2
    return (basket["quant"][:quant_n] + basket["reasoning"][:reasoning_n])[:limit]


def subject_for_topic(topic):
    reasoning_words = {
        "seating", "puzzle", "syllogism", "coding", "analogy", "series",
        "relation", "direction", "inequality", "reasoning", "spatial", "verbal",
    }
    words = set(re.findall(r"[a-z]+", (topic or "").lower()))
    return "Reasoning" if words & reasoning_words else "Quant"


def _age_days(published_at, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(str(published_at).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max((now - dt).total_seconds() / 86400, 1.0)
    except Exception:
        return 1.0


def enrich_videos(videos, now=None):
    out = []
    for video in videos or []:
        row = dict(video)
        row["age_days"] = round(_age_days(row.get("published_at"), now), 1)
        row["views_per_day"] = round((row.get("views", 0) or 0) / row["age_days"])
        out.append(row)
    return out


def topic_matches_title(topic, title):
    ignore = {"and", "or", "the", "for", "of", "questions", "class"}
    keys = [x for x in re.findall(r"[a-z0-9]+", (topic or "").lower())
            if len(x) > 2 and x not in ignore]
    hay = set(re.findall(r"[a-z0-9]+", (title or "").lower()))
    if not keys:
        return False
    needed = 1 if len(keys) <= 2 else 2
    return len(set(keys) & hay) >= needed


def own_coverage(topic, own_videos):
    matches = [v for v in (own_videos or []) if topic_matches_title(topic, v.get("title", ""))]
    return {
        "known": own_videos is not None,
        "count": len(matches),
        "examples": [v.get("title", "") for v in matches[:3]],
    }


def collect_signal(topic, videos, comments, own_videos=None, inventory=0):
    """Summarise raw public evidence for one topic before cross-topic scoring."""
    vids = enrich_videos(videos)
    velocities = [v["views_per_day"] for v in vids]
    avg_velocity = sum(velocities) / len(velocities) if velocities else 0
    max_velocity = max(velocities, default=0)
    median_velocity = sorted(velocities)[len(velocities) // 2] if velocities else 0
    engagement = sum(v.get("engagement", 0) for v in vids) / len(vids) if vids else 0
    comments = comments or []
    doubts = [c for c in comments if c.get("kind") == "doubt"]
    requests = [c for c in comments if c.get("kind") == "request"]
    top_videos = sorted(vids, key=lambda v: v["views_per_day"], reverse=True)[:3]
    channels = {v.get("channel_id") or v.get("channel_title") for v in vids}
    channels.discard(None)
    coverage = own_coverage(topic, own_videos)
    outlier_ratio = max_velocity / max(median_velocity, 1)
    return {
        "topic": topic,
        "subject": subject_for_topic(topic),
        "video_count": len(vids),
        "channel_count": len(channels),
        "avg_views_per_day": round(avg_velocity),
        "max_views_per_day": round(max_velocity),
        "avg_engagement": round(engagement, 2),
        "outlier_ratio": round(outlier_ratio, 1),
        "comments_sampled": len(comments),
        "doubt_count": len(doubts),
        "request_count": len(requests),
        "doubt_examples": [c.get("text", "")[:240] for c in doubts[:3]],
        "request_examples": [c.get("text", "")[:240] for c in requests[:3]],
        "own_coverage": coverage,
        "inventory": int(inventory or 0),
        "top_videos": top_videos,
    }


def _relative(value, maximum, log=False):
    if maximum <= 0 or value <= 0:
        return 0
    if log:
        return round(math.log1p(value) / math.log1p(maximum) * 100)
    return round(value / maximum * 100)


def recommend_product(row, exam_days=None):
    """Translate evidence into a test product and an immediately usable blueprint."""
    doubts = row.get("doubt_count", 0)
    requests = row.get("request_count", 0)
    coverage = row.get("own_coverage", {})
    inventory = row.get("inventory", 0)
    heat = row.get("market_heat", 0)

    if exam_days is not None and 0 <= exam_days <= 21:
        product, count, minutes = "Rapid Revision Mini Mock", 25, 20
        reason = "Exam is close; convert the signal into timed revision practice."
    elif doubts >= 12 and row.get("score_components", {}).get("doubts", 0) >= 90:
        product, count, minutes = "Misconception Diagnostic Quiz", 15, 12
        reason = "Repeated student confusion is stronger than generic content demand."
    elif heat >= 70 and coverage.get("known") and coverage.get("count", 0) == 0:
        product, count, minutes = "Rapid Sectional Test", 20, 18
        reason = "Market heat is high and your recent channel coverage is missing."
    elif requests >= 3:
        product, count, minutes = "Demand-led Practice Set", 20, 15
        reason = "Students are explicitly asking for more practice or tests."
    elif inventory < 20:
        product, count, minutes = "Question Bank Booster", 25, 20
        reason = "The topic signal exists, but the reusable question inventory is thin."
    else:
        product, count, minutes = "Speed Challenge", 20, 15
        reason = "Use the active topic to repackage existing content into timed practice."

    return {
        "product": product,
        "reason": reason,
        "questions": count,
        "duration_minutes": minutes,
        "difficulty": {"easy": 30, "medium": 50, "hard": 20},
        "review_gate": "Faculty review required before publishing",
        "cta": "Generate draft",
        "inventory_ready": inventory >= count,
    }


def rank_signals(signals, exam_days=None):
    """Score a scan relative to its peer topics and return ranked actions."""
    if not signals:
        return []
    max_velocity = max((x.get("avg_views_per_day", 0) for x in signals), default=1)
    max_doubts = max((x.get("doubt_count", 0) for x in signals), default=1)
    max_requests = max((x.get("request_count", 0) for x in signals), default=1)
    max_engagement = max((x.get("avg_engagement", 0) for x in signals), default=1)
    max_outlier = max((x.get("outlier_ratio", 0) for x in signals), default=1)
    max_channels = max((x.get("channel_count", 0) for x in signals), default=1)

    ranked = []
    for signal in signals:
        row = dict(signal)
        components = {
            "velocity": _relative(row.get("avg_views_per_day", 0), max_velocity, log=True),
            "doubts": _relative(row.get("doubt_count", 0), max_doubts),
            "requests": _relative(row.get("request_count", 0), max_requests),
            "outliers": _relative(row.get("outlier_ratio", 0), max_outlier),
            "engagement": _relative(row.get("avg_engagement", 0), max_engagement),
        }
        heat = round(components["velocity"] * .30 + components["doubts"] * .25 +
                     components["requests"] * .15 + components["outliers"] * .20 +
                     components["engagement"] * .10)
        coverage = row.get("own_coverage", {})
        if coverage.get("known"):
            coverage_gap = 100 if coverage.get("count", 0) == 0 else max(15, 70 - coverage["count"] * 15)
        else:
            coverage_gap = 50
        saturation = _relative(row.get("channel_count", 0), max_channels)
        # Saturation is evidence of a market, but lowers the whitespace available.
        opportunity = round(heat * .65 + coverage_gap * .25 + (100 - saturation) * .10)
        row.update({
            "market_heat": heat,
            "opportunity_score": opportunity,
            "coverage_gap": coverage_gap,
            "market_saturation": saturation,
            "score_components": components,
        })
        row["recommendation"] = recommend_product(row, exam_days)
        ranked.append(row)
    ranked.sort(key=lambda x: (x["opportunity_score"], x["market_heat"]), reverse=True)
    for index, row in enumerate(ranked, 1):
        row["rank"] = index
    return ranked


def executive_summary(ranked, exam, days, own_channel_title=""):
    if not ranked:
        return {}
    top = ranked[0]
    return {
        "headline": f"Build {top['recommendation']['product']} on {top['topic']} next",
        "why": top["recommendation"]["reason"],
        "exam": exam,
        "window_days": days,
        "own_channel": own_channel_title,
        "topics_scanned": len(ranked),
        "top_heat": top["market_heat"],
        "top_opportunity": top["opportunity_score"],
        "disclaimer": "Directional market signal from public YouTube results; not YouTube search-volume data.",
    }


def demo_scan(exam="SSC CGL", days=30, exam_days=45, limit=8):
    """A transparent, offline-safe sample for a presentation walkthrough."""
    samples = [
        ("Percentage", "Quant", 18400, 38, 9, 4.8, 3.9, 7, 0, 12,
         ["20% increase ke baad 20% decrease same kyu nahi hota?",
          "Successive percentage ka short method samajh nahi aaya"],
         ["Please make a timed percentage test"]),
        ("Circular Seating", "Reasoning", 13900, 31, 7, 5.4, 4.1, 6, 1, 42,
         ["Facing centre aur outside mein left right confuse hota hai"],
         ["Sir circular seating ka sectional mock chahiye"]),
        ("Ratio and Proportion", "Quant", 9200, 24, 5, 3.2, 3.5, 8, 0, 8,
         ["Partnership ratio mein time kab multiply karna hai?"],
         ["Ratio PYQ practice set upload karo"]),
        ("Coding Decoding", "Reasoning", 7100, 17, 3, 2.7, 3.2, 9, 3, 65,
         ["New pattern coding ka logic kaise identify kare?"], [],),
        ("Time and Work", "Quant", 5400, 12, 2, 2.1, 2.9, 10, 4, 87,
         ["Efficiency method mein LCM selection doubt hai"], [],),
        ("Syllogism", "Reasoning", 3800, 9, 1, 1.8, 2.5, 11, 5, 103,
         ["Only a few aur some not ka conclusion confuse karta hai"], [],),
        ("Number Series", "Quant", 3200, 8, 2, 2.0, 2.7, 9, 2, 34,
         ["Missing number pattern identify kaise kare?"],
         ["Number series speed test chahiye"]),
        ("Seating Arrangement", "Reasoning", 2900, 11, 2, 2.4, 3.0, 10, 2, 56,
         ["Double row arrangement mein position confuse hoti hai"],
         ["Seating arrangement mini mock banao"]),
        ("Profit and Loss", "Quant", 2700, 10, 2, 2.2, 2.8, 8, 1, 44,
         ["Marked price aur discount ke baad profit percent ka base confuse hota hai"],
         ["Profit loss mixed level quiz chahiye"]),
        ("Puzzles", "Reasoning", 2500, 14, 3, 2.8, 3.1, 11, 3, 71,
         ["Floor puzzle mein negative clues ko place kaise kare?"],
         ["Daily puzzle practice set start karo"]),
        ("Time Speed Distance", "Quant", 2200, 9, 1, 2.0, 2.6, 9, 2, 39,
         ["Relative speed mein direction ka sign confuse hota hai"],
         ["Train questions ka sectional test chahiye"]),
        ("Coded Inequality", "Reasoning", 1900, 8, 1, 1.9, 2.5, 7, 1, 28,
         ["Either-or conclusion kab valid hota hai?"],
         ["Coded inequality rapid quiz banao"]),
    ]
    signals = []
    for topic, subject, velocity, doubts, requests, outlier, engagement, channels, coverage, inventory, doubt_ex, request_ex in samples:
        signals.append({
            "topic": topic, "subject": subject, "video_count": 12,
            "channel_count": channels, "avg_views_per_day": velocity,
            "max_views_per_day": round(velocity * outlier),
            "avg_engagement": engagement, "outlier_ratio": outlier,
            "comments_sampled": 200, "doubt_count": doubts,
            "request_count": requests, "doubt_examples": doubt_ex,
            "request_examples": request_ex,
            "own_coverage": {"known": True, "count": coverage, "examples": []},
            "inventory": inventory, "top_videos": [{
                "title": f"Sample market evidence — {topic}",
                "views_per_day": round(velocity * outlier), "url": "",
            }],
        })
    signals = signals[:max(1, min(int(limit or 8), len(signals)))]
    ranked = rank_signals(signals, exam_days=exam_days)
    summary = executive_summary(ranked, exam, days, "Your 3.2M channel (sample)")
    return {"summary": summary, "opportunities": ranked,
            "topics": [x["topic"] for x in ranked]}
