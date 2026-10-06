"""
Lightweight analysis helpers — no external ML, pure Python.
Used to turn raw comments / transcripts into insights.
"""
import re
from collections import Counter
from datetime import datetime, timezone

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Words that signal a student doubt / question (Hindi + English)
DOUBT_MARKERS = [
    "doubt", "confuse", "confusing", "not clear", "please explain",
    "kaise", "kaese", "kese", "kyu", "kyun", "kyon", "kaha", "kahan",
    "samajh nahi", "samjh nahi", "samajh nhi", "samjh nhi",
    "nahi aaya", "nahi aya", "nhi aaya", "clear nahi",
    "समझ", "कैसे", "क्यों", "कहां", "नहीं आया", "डाउट", "how ", "why ", "what is",
    "plz explain", "solve kaise", "solve nahi", "solution batao", "batao", "bataye", "sikhao",
]

# Praise-only comments must not become "misconceptions" merely because they
# contain words such as question/samajh.  These are ignored unless a clear
# question/pain signal is also present.
PRAISE_MARKERS = [
    "thank", "thanks", "thank you", "badiya", "badhiya", "best class",
    "best tha", "bahut acha", "bahut achha", "bahut ache", "mast", "great",
    "excellent", "easy way", "samajh aa raha", "samjh aa raha", "samajh aaya",
    "samjh aaya", "love you", "❤", "❤️",
]

PAIN_MARKERS = [
    "nahi", "nhi", "not ", "confus", "doubt", "galat", "wrong", "problem",
    "atak", "dikkat", "clear nahi", "समझ नहीं", "नहीं आया",
]

# Words that signal a content request ("make a video on ...")
REQUEST_MARKERS = [
    "please make", "plz make", "video banao", "video banaye", "banado",
    "request", "cover", "upload", "next video", "chahiye", "ka video",
    "series banao", "playlist", "topic pe",
]

# Basic stopwords (Hindi romanised + English) for word-frequency
STOPWORDS = set("""
a an the is are was were be been being to of in on for and or but if then so
this that these those it its he she they we you i me my your our their with as
at by from up down out about very can will just not no do does did has have had
he's i'm it's ki ka ke ko hai hain ho na ne se me mein aur ya bhi to par pe kya
jo wo ye yeh hi bas ab tak sab kar karo kare kiya hua tha the bahut bhai sir
""".split())

TIMESTAMP_RE = re.compile(r'\b\d{1,2}:\d{2}(?::\d{2})?\b')


def _matches_any(text, markers):
    t = text.lower()
    return any(m in t for m in markers)


def looks_like_doubt(text):
    """High-precision doubt filter for Hindi/Hinglish/English comments."""
    text = (text or "").strip()
    if not text:
        return False
    lower = text.lower()
    has_question = "?" in text or "？" in text
    has_doubt_language = _matches_any(lower, DOUBT_MARKERS)
    has_pain = _matches_any(lower, PAIN_MARKERS)
    praise_only = _matches_any(lower, PRAISE_MARKERS) and not (has_question or has_pain)
    if praise_only:
        return False
    # A timestamp is evidence location, not evidence of confusion by itself.
    return has_question or has_doubt_language or has_pain


def extract_doubts(comments, limit=40):
    """
    From a list of comment dicts, pull out those that look like doubts/questions.
    Ranked by like count (most-upvoted doubts first).
    """
    doubts = []
    for c in comments:
        text = c.get("text", "")
        if looks_like_doubt(text):
            item = dict(c)
            item["timestamps"] = TIMESTAMP_RE.findall(text)
            doubts.append(item)
    doubts.sort(key=lambda x: x.get("likes", 0), reverse=True)
    return doubts[:limit]


def extract_requests(comments, limit=25):
    """Comments where the audience is asking for specific content."""
    reqs = [c for c in comments if _matches_any(c.get("text", ""), REQUEST_MARKERS)]
    reqs.sort(key=lambda x: x.get("likes", 0), reverse=True)
    return reqs[:limit]


def doubt_candidates(comments):
    """
    Cheap pre-filter for Doubt Radar: keep only comments that look like a
    student doubt (a '?', a timestamp, or a doubt marker) so we don't pay to
    send every comment to the LLM. Returns light dicts the clusterer needs.
    """
    out = []
    for c in comments:
        text = (c.get("text") or "").strip()
        if not text:
            continue
        ts = TIMESTAMP_RE.findall(text)
        if looks_like_doubt(text):
            out.append({
                "text": text,
                "likes": int(c.get("likes", 0) or 0),
                "timestamps": ts,
            })
    return out


def word_frequency(text, top=30, min_len=3):
    """Top keywords in a block of text (transcript or joined comments)."""
    words = re.findall(r'[a-zA-Zऀ-ॿ]+', text.lower())
    words = [w for w in words if len(w) >= min_len and w not in STOPWORDS]
    return Counter(words).most_common(top)


def comment_sentiment_rough(comments):
    """
    Very rough positive/negative tally based on keyword lists.
    Not a real sentiment model — just a directional signal.
    """
    pos = ["thank", "thanks", "great", "best", "amazing", "helpful", "love",
           "shukriya", "dhanyavad", "badhiya", "mast", "zabardast", "helpful",
           "clear ho gaya", "samajh aa gaya", "wonderful", "excellent", "op"]
    neg = ["worst", "bad", "boring", "waste", "useless", "confus", "galat",
           "bekar", "bakwas", "samajh nahi", "clear nahi", "wrong", "poor"]
    p = n = 0
    for c in comments:
        t = c.get("text", "").lower()
        if any(w in t for w in pos):
            p += 1
        if any(w in t for w in neg):
            n += 1
    total = len(comments) or 1
    return {
        "positive": p,
        "negative": n,
        "neutral": total - p - n,
        "positive_pct": round(p / total * 100, 1),
        "negative_pct": round(n / total * 100, 1),
    }


def channel_summary(videos):
    """Aggregate insight over a channel's recent videos."""
    if not videos:
        return {}
    total_views = sum(v["views"] for v in videos)
    avg_views = total_views / len(videos)
    avg_engagement = sum(v["engagement"] for v in videos) / len(videos)
    best = max(videos, key=lambda v: v["views"])
    worst = min(videos, key=lambda v: v["views"])
    most_engaging = max(videos, key=lambda v: v["engagement"])
    return {
        "count": len(videos),
        "total_views": total_views,
        "avg_views": int(avg_views),
        "avg_engagement": round(avg_engagement, 2),
        "best": best,
        "worst": worst,
        "most_engaging": most_engaging,
    }


# ---------------------------------------------------------------- deep dive
def _parse_dt(iso):
    try:
        return datetime.strptime(str(iso)[:19], "%Y-%m-%dT%H:%M:%S")
    except Exception:
        return None


def _median(nums):
    s = sorted(nums)
    n = len(s)
    if n == 0:
        return 0
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def title_keyword_impact(videos, avg_views=None, min_videos=3, top=12):
    """
    Which title words appear with above/below-average views.
    'lift' = how much a word's videos beat the channel average (%).
    """
    if not videos:
        return []
    if avg_views is None:
        avg_views = sum(v["views"] for v in videos) / len(videos)
    word_views = {}
    for v in videos:
        words = set(w for w in re.findall(r'[a-zA-Z0-9ऀ-ॿ]+', v["title"].lower())
                    if len(w) >= 3 and w not in STOPWORDS)
        for w in words:
            word_views.setdefault(w, []).append(v["views"])
    rows = []
    for w, vs in word_views.items():
        if len(vs) >= min_videos:
            wavg = sum(vs) / len(vs)
            lift = round((wavg / avg_views - 1) * 100) if avg_views else 0
            rows.append({"word": w, "count": len(vs),
                         "avg_views": int(wavg), "lift": lift})
    rows.sort(key=lambda r: r["avg_views"], reverse=True)
    return rows[:top]


def channel_deepdive(videos):
    """Deeper analytics: cadence, best day, length vs views, outliers, title impact."""
    if not videos:
        return {}
    n = len(videos)
    view_list = [v["views"] for v in videos]
    avg = sum(view_list) / n
    median = _median(view_list)

    # day-of-week performance
    agg = {d: {"count": 0, "views": 0} for d in WEEKDAYS}
    dates = []
    for v in videos:
        dt = _parse_dt(v.get("published_at", ""))
        if not dt:
            continue
        dates.append(dt)
        d = WEEKDAYS[dt.weekday()]
        agg[d]["count"] += 1
        agg[d]["views"] += v["views"]
    dow_rows = [{"day": d, "count": agg[d]["count"],
                 "avg_views": int(agg[d]["views"] / agg[d]["count"]) if agg[d]["count"] else 0}
                for d in WEEKDAYS]
    active = [r for r in dow_rows if r["count"]]
    best_day = max(active, key=lambda r: r["avg_views"]) if active else None

    # cadence
    cadence = per_week = None
    if len(dates) >= 2:
        dates.sort()
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        gaps = [g for g in gaps if g >= 0]
        if gaps:
            cadence = round(sum(gaps) / len(gaps), 1)
            if cadence > 0:
                per_week = round(7 / cadence, 1)

    # length buckets
    buckets = [("< 5 min", 0, 300), ("5–15 min", 300, 900),
               ("15–30 min", 900, 1800), ("30–60 min", 1800, 3600),
               ("60 min +", 3600, 10 ** 9)]
    len_rows = []
    for label, lo, hi in buckets:
        grp = [v for v in videos if lo <= v.get("duration_seconds", 0) < hi]
        if grp:
            len_rows.append({"label": label, "count": len(grp),
                             "avg_views": int(sum(x["views"] for x in grp) / len(grp))})
    best_length = max(len_rows, key=lambda r: r["avg_views"]) if len_rows else None

    # outliers (>= 1.5x median)
    over = [v for v in videos if median and v["views"] >= 1.5 * median]
    over.sort(key=lambda v: v["views"], reverse=True)
    outliers = [{"title": v["title"], "views": v["views"], "url": v["url"],
                 "ratio": round(v["views"] / median, 1) if median else 0}
                for v in over[:8]]

    return {
        "avg_views": int(avg),
        "median_views": int(median),
        "dow": dow_rows,
        "best_day": best_day,
        "cadence_days": cadence,
        "per_week": per_week,
        "length": len_rows,
        "best_length": best_length,
        "outliers": outliers,
        "title_keywords": title_keyword_impact(videos, avg),
    }


def velocity_momentum(videos):
    """
    Is the channel heating up? Compare views-per-day of the 5 newest videos
    vs the rest. Positive % = recent videos are gathering views faster.
    (views-per-day avoids the bias that older videos had more time to rack up views.)
    """
    # naive UTC (matches _parse_dt output; utcnow() is deprecated in 3.12+)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    def vel(v):
        dt = _parse_dt(v.get("published_at", ""))
        if not dt:
            return None
        days = max((now - dt).days, 1)
        return v["views"] / days

    vels = [x for x in (vel(v) for v in videos) if x is not None]
    if len(vels) < 6:
        return None
    recent = vels[:5]                      # videos come newest-first
    older = vels[5:]
    r = sum(recent) / len(recent)
    o = sum(older) / len(older)
    if o == 0:
        return None
    return round((r / o - 1) * 100)


def _title_keyword_views(videos):
    """Map title word -> list of views of videos containing it."""
    wv = {}
    for v in videos:
        words = set(w for w in re.findall(r'[a-zA-Z0-9ऀ-ॿ]+', v.get("title", "").lower())
                    if len(w) >= 3 and w not in STOPWORDS)
        for w in words:
            wv.setdefault(w, []).append(v.get("views", 0))
    return wv


def seo_audit(video):
    """Rate a video's title/description/tags for basic SEO and give tips."""
    title = video.get("title", "") or ""
    desc = video.get("description", "") or ""
    tags = video.get("tags", []) or []
    tl, dl, tc = len(title), len(desc), len(tags)

    score, maxp, checks = 0, 0, []

    def add(ok, pts, good, bad):
        nonlocal score, maxp
        maxp += pts
        if ok:
            score += pts
        checks.append({"ok": bool(ok), "label": good if ok else bad})

    add(30 <= tl <= 70, 20, f"Title length is good ({tl} chars)",
        f"Title is {tl} chars — aim for 30–70")
    add(dl >= 200, 20, f"Description is detailed ({dl} chars)",
        f"Description is short ({dl} chars) — add 200+ with keywords")
    add(tc >= 5, 20, f"{tc} tags added", f"Only {tc} tags — add 8–15 relevant tags")
    add(tc >= 10, 15, "Rich tag set (10+ tags)", "Fewer than 10 tags — add more variants")
    add(any(ch.isdigit() for ch in title), 10, "Title has a number/hook",
        "Consider adding a number or hook to the title")
    add(dl > 0 and any(t.lower() in desc.lower() for t in tags[:5]) if tags else False,
        15, "Top tags also appear in description",
        "Repeat your main tags/keywords in the description")

    pct = round(score / maxp * 100) if maxp else 0
    return {"score": pct, "checks": checks, "tags": tags,
            "title_len": tl, "desc_len": dl, "tag_count": tc}


def find_outliers(videos, subs_map, min_ratio=2.0, limit=20):
    """
    Viral finder: videos whose views hugely exceed their channel's subscriber
    count (small channel, big hit). vps = views per subscriber.
    """
    rows = []
    for v in videos:
        subs = subs_map.get(v.get("channel_id"))
        if not subs:
            continue
        ratio = v["views"] / subs
        if ratio >= min_ratio:
            row = dict(v)
            row["subscribers"] = subs
            row["vps"] = round(ratio, 1)
            rows.append(row)
    rows.sort(key=lambda x: x["vps"], reverse=True)
    return rows[:limit]


def score_keywords(items):
    """
    Given per-keyword {keyword, avg_views, floor_views, count}, score
    demand / competition / opportunity (each 0–100).
    """
    if not items:
        return []
    max_demand = max((i["avg_views"] for i in items), default=1) or 1
    max_floor = max((i["floor_views"] for i in items), default=1) or 1
    out = []
    for i in items:
        demand = round(i["avg_views"] / max_demand * 100)
        competition = round(i["floor_views"] / max_floor * 100)
        opportunity = max(0, round(demand - competition * 0.6))
        row = dict(i)
        row.update(demand=demand, competition=competition, opportunity=opportunity)
        out.append(row)
    out.sort(key=lambda x: x["opportunity"], reverse=True)
    return out


def content_gap(your_videos, comp_videos, top=25):
    """Title keywords the competitor uses (with views) that you don't."""
    yours = set(_title_keyword_views(your_videos).keys())
    comp = _title_keyword_views(comp_videos)
    rows = []
    for w, views in comp.items():
        if len(views) >= 2 and w not in yours:
            rows.append({"word": w, "count": len(views),
                         "avg_views": int(sum(views) / len(views))})
    rows.sort(key=lambda r: r["avg_views"], reverse=True)
    return rows[:top]


def compare_metrics(info, videos):
    """One row of side-by-side comparison for a channel + 'what's working' insight."""
    s = channel_summary(videos)
    dd = channel_deepdive(videos)
    return {
        "channel_id": info["channel_id"],
        "title": info["title"],
        "thumbnail": info["thumbnail"],
        "subscribers": info["subscribers"],
        "total_views": info["total_views"],
        "video_count": info["video_count"],
        "avg_views": s.get("avg_views", 0),
        "avg_engagement": s.get("avg_engagement", 0),
        "per_week": dd.get("per_week"),
        "best_day": dd.get("best_day", {}).get("day") if dd.get("best_day") else None,
        "best_length": dd.get("best_length", {}).get("label") if dd.get("best_length") else None,
        "momentum": velocity_momentum(videos),
        "winning": dd.get("outliers", [])[:3],           # their best-performing videos
        "keywords": dd.get("title_keywords", [])[:6],     # title words that drive views
    }
