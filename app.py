"""
YouTube Analyzer — Flask backend.

Run:  python app.py   (then open http://127.0.0.1:5000)

API key: put it in a .env file as  YOUTUBE_API_KEY=xxxx
         OR paste it in the app's sidebar (sent with each request).
Transcript features work WITHOUT any key.
"""
import os
import json
import glob
import copy
import time
from io import BytesIO
from datetime import datetime, timezone, timedelta
from flask import Flask, render_template, request, jsonify, send_file
from dotenv import load_dotenv, dotenv_values

from core import transcript as tr
from core import yt_api as yt
from core import analysis as an
from core import llm
from core import store
from core import market
from core import exports

load_dotenv()

HERE = os.path.dirname(os.path.abspath(__file__))


def _current_key():
    """
    Read the API key FRESH on every call (no restart needed if .env changes):
      1) real environment variable
      2) the .env file in this folder
      3) any *.json file in the folder that contains an AIza... key
    Returns the key string, or "" if none found.
    """
    # 1) real environment
    k = os.getenv("YOUTUBE_API_KEY", "").strip()
    if k:
        return k

    # 2) .env file (read live so a newly-created .env works without restart)
    try:
        vals = dotenv_values(os.path.join(HERE, ".env"))
        k = (vals.get("YOUTUBE_API_KEY") or "").strip()
        if k:
            return k
    except Exception:
        pass

    # 3) a known credential json (not every *.json in the folder — that could
    #    accidentally pick up a key-like string from an unrelated file)
    key_fields = ("api_key", "apiKey", "key", "YOUTUBE_API_KEY", "youtube_api_key")
    cred_globs = ("client_secret_*.json", "credentials.json",
                  "youtube_key.json", "api_key.json")
    cred_paths = []
    for pat in cred_globs:
        cred_paths.extend(glob.glob(os.path.join(HERE, pat)))
    for path in cred_paths:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if isinstance(data, dict):
            for fld in key_fields:
                val = data.get(fld)
                if isinstance(val, str) and val.strip().startswith("AIza"):
                    return val.strip()
    return ""


app = Flask(__name__)
RADAR_CACHE = {}
RADAR_CACHE_TTL = 30 * 60


def _key(payload=None):
    """The API key, always read fresh from .env / environment."""
    return _current_key()


@app.route("/")
def index():
    # The Faculty Review Bank is intentionally a scratch workspace. A fresh
    # page starts a fresh pitch/review session; users can export before reload.
    store.init()
    store.clear_qbank()
    return render_template("index.html", has_env_key=bool(_current_key()))


# ------------------------------------------------------------------ transcript
@app.route("/api/transcript", methods=["POST"])
def api_transcript():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "Please enter a YouTube URL"})
    try:
        result = tr.get_transcript(url)
        result.pop("entries", None)  # drop heavy field for the plain text call
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------------------------ video analyze
@app.route("/api/video", methods=["POST"])
def api_video():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()
    key = _key(data)
    vid = tr.extract_video_id(url)
    if not vid:
        return jsonify({"ok": False, "error": "Invalid YouTube URL"})

    out = {"video_id": vid}

    # transcript (no key needed)
    try:
        t = tr.get_transcript(url)
        out["transcript"] = {
            "language": t["language"],
            "language_code": t["language_code"],
            "is_generated": t["is_generated"],
            "char_count": t["char_count"],
            "text": t["text"],
            "word_freq": an.word_frequency(t["text"], top=25),
        }
    except Exception as e:
        out["transcript_error"] = str(e)

    # stats + comments (need key)
    if key:
        try:
            out["details"] = yt.video_details(key, vid)
            out["seo"] = an.seo_audit(out["details"])
        except Exception as e:
            out["details_error"] = str(e)
        try:
            comments = yt.video_comments(key, vid, max_n=200)
            out["comment_count_fetched"] = len(comments)
            out["doubts"] = an.extract_doubts(comments, limit=40)
            out["requests"] = an.extract_requests(comments, limit=20)
            out["sentiment"] = an.comment_sentiment_rough(comments)
            out["top_comments"] = sorted(
                comments, key=lambda c: c["likes"], reverse=True)[:15]
        except Exception as e:
            out["comments_error"] = str(e)
    else:
        out["no_key"] = True

    return jsonify({"ok": True, "data": out})


# ------------------------------------------------------------------ channel track
@app.route("/api/channel", methods=["POST"])
def api_channel():
    data = request.get_json(force=True)
    query = (data.get("channel") or "").strip()
    key = _key(data)
    max_n = int(data.get("max_n", 25))
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    if not query:
        return jsonify({"ok": False, "error": "Enter a channel URL, @handle or name"})
    try:
        cid = yt.resolve_channel_id(key, query)
        result = yt.channel_videos(key, cid, max_n=max_n)
        result["summary"] = an.channel_summary(result["videos"])
        result["deepdive"] = an.channel_deepdive(result["videos"])
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------------------------ search / research
@app.route("/api/search", methods=["POST"])
def api_search():
    data = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    key = _key(data)
    order = data.get("order", "relevance")
    max_n = int(data.get("max_n", 25))
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    if not query:
        return jsonify({"ok": False, "error": "Enter a topic / keyword to research"})
    try:
        videos = yt.search_videos(key, query, max_n=max_n, order=order)
        # dominant channels
        from collections import Counter
        chan = Counter(v.get("channel_title", "") for v in videos)
        return jsonify({"ok": True, "data": {
            "videos": videos,
            "top_channels": chan.most_common(10),
        }})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ----------------------------------------------------------- market command center
@app.route("/api/market-radar", methods=["POST"])
def api_market_radar():
    """Turn public market evidence into a ranked test-production action list."""
    data = request.get_json(force=True) or {}
    exam = (data.get("exam") or "SSC CGL").strip()[:80]
    subject = (data.get("subject") or "both").strip().lower()
    if subject not in ("quant", "reasoning", "both"):
        subject = "both"
    try:
        days = min(max(int(data.get("days", 30) or 30), 7), 365)
    except (TypeError, ValueError):
        days = 30
    try:
        exam_days_raw = data.get("exam_days")
        exam_days = None if exam_days_raw in (None, "") else min(max(int(exam_days_raw), 0), 365)
    except (TypeError, ValueError):
        exam_days = None

    scan_mode = (data.get("scan_mode") or "standard").strip().lower()
    topic_limits = {"quick": 4, "standard": 8, "deep": 12}
    if scan_mode not in topic_limits:
        scan_mode = "standard"
    topic_limit = topic_limits[scan_mode]

    if bool(data.get("demo")):
        result = market.demo_scan(exam, days, exam_days, limit=topic_limit)
        result.update({
            "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "quota_estimate": 0, "comment_calls": 0, "errors": [],
            "own_channel_error": "", "demo": True, "cache_hit": False,
            "scan_mode": scan_mode, "topic_limit": topic_limit,
        })
        return jsonify({"ok": True, "data": result})

    key = _key(data)
    if not key:
        return jsonify({"ok": False, "error": "Market scan needs YOUTUBE_API_KEY in the .env file."})

    topics = market.topic_plan(exam, subject, data.get("custom_topics"), limit=topic_limit)
    if not topics:
        return jsonify({"ok": False, "error": "Add at least one topic to scan."})

    own_query = (data.get("own_channel") or os.getenv("YOUR_CHANNEL", "")).strip()
    cache_key = (exam.lower(), subject, days, exam_days, tuple(x.lower() for x in topics),
                 own_query.lower(), scan_mode)
    now_ts = time.time()
    cached_entry = RADAR_CACHE.get(cache_key)
    if cached_entry and now_ts - cached_entry["ts"] <= RADAR_CACHE_TTL:
        cached = copy.deepcopy(cached_entry["data"])
        cached["cache_hit"] = True
        cached["cached_age_seconds"] = round(now_ts - cached_entry["ts"])
        cached["original_quota_estimate"] = cached.get("quota_estimate", 0)
        cached["quota_estimate"] = 0
        return jsonify({"ok": True, "data": cached})
    # Discard expired entries while the cache is small and local.
    for old_key, entry in list(RADAR_CACHE.items()):
        if now_ts - entry["ts"] > RADAR_CACHE_TTL:
            RADAR_CACHE.pop(old_key, None)

    own_videos, own_title, own_error = None, "", ""
    if own_query:
        try:
            own_id = yt.resolve_channel_id(key, own_query)
            own_data = yt.channel_videos(key, own_id, max_n=50)
            own_videos = own_data["videos"]
            own_title = own_data["channel"]["title"]
        except Exception as e:
            own_error = str(e)

    published_after = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds").replace("+00:00", "Z")
    store.init()
    signals, errors, comment_calls = [], [], 0
    for topic in topics:
        query = f"{exam} {topic} questions"
        try:
            videos = yt.search_videos(
                key, query, max_n=12, order="viewCount",
                published_after=published_after, region_code="IN")
            enriched = market.enrich_videos(videos)
            comment_targets = sorted(
                enriched, key=lambda v: v.get("views_per_day", 0), reverse=True)[:2]
            classified = []
            for video in comment_targets:
                try:
                    comments = yt.video_comments(key, video["video_id"], max_n=100)
                    comment_calls += 1
                except Exception:
                    continue
                doubt_texts = {c.get("text", "") for c in an.doubt_candidates(comments)}
                request_texts = {c.get("text", "") for c in an.extract_requests(comments, limit=100)}
                for comment in comments:
                    text_value = comment.get("text", "")
                    base = {"text": text_value, "likes": comment.get("likes", 0),
                            "video_title": video.get("title", ""),
                            "video_url": video.get("url", "")}
                    if text_value in doubt_texts:
                        classified.append(dict(base, kind="doubt"))
                    if text_value in request_texts:
                        classified.append(dict(base, kind="request"))
            inventory = store.count_questions_for_topic(topic)
            signals.append(market.collect_signal(
                topic, videos, classified, own_videos=own_videos, inventory=inventory))
        except Exception as e:
            errors.append(f"{topic}: {str(e)[:180]}")

    ranked = market.rank_signals(signals, exam_days=exam_days)
    if not ranked:
        detail = " | ".join(errors[:3])
        return jsonify({"ok": False, "error": "No market results were available. " + detail})

    summary = market.executive_summary(ranked, exam, days, own_title)
    quota_estimate = len(topics) * 100 + comment_calls + (3 if own_query else 0)
    result_data = {
        "summary": summary,
        "opportunities": ranked,
        "topics": topics,
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "quota_estimate": quota_estimate,
        "comment_calls": comment_calls,
        "errors": errors,
        "own_channel_error": own_error,
        "cache_hit": False,
        "scan_mode": scan_mode,
        "topic_limit": topic_limit,
    }
    RADAR_CACHE[cache_key] = {"ts": time.time(), "data": copy.deepcopy(result_data)}
    return jsonify({"ok": True, "data": result_data})


# ------------------------------------------------------------------ doubt radar
@app.route("/api/doubts", methods=["POST"])
def api_doubts():
    """
    Topic → scan top videos' comments → cluster into concept-level student
    doubts → a demand-ranked 'make this next' content brief.
    """
    data = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    key = _key(data)
    max_videos = min(max(int(data.get("max_videos", 12) or 12), 1), 25)
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    if not query:
        return jsonify({"ok": False, "error": "Enter a topic to scan for student doubts."})
    if not llm.any_key():
        return jsonify({"ok": False, "error": "Doubt clustering needs an AI key. Add GEMINI_API_KEY (free) to the .env file."})
    try:
        vids = yt.search_videos(key, query, max_n=max_videos, order="relevance")
        candidates, scanned = [], 0
        for v in vids:
            try:
                comments = yt.video_comments(key, v["video_id"], max_n=100)
            except Exception:
                continue  # comments disabled / transient — skip this video
            scanned += 1
            for c in an.doubt_candidates(comments):
                c["video_title"] = v.get("title", "")
                c["video_url"] = v.get("url", "")
                candidates.append(c)
        if not candidates:
            return jsonify({"ok": False, "error": "No doubt-like comments found. Try a broader topic (or comments may be disabled on these videos)."})
        clusters = llm.cluster_doubts(candidates, topic=query)
        return jsonify({"ok": True, "data": {
            "clusters": clusters,
            "videos_scanned": scanned,
            "doubts_found": len(candidates),
            "topic": query,
        }})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------------------------ content generator
@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json(force=True)
    mode = data.get("mode", "topic")          # topic | url | text
    raw = (data.get("input") or "").strip()
    try:
        n = min(max(int(data.get("count", 10) or 10), 1), 100)   # cap 1..100
    except Exception:
        n = 10
    difficulty = data.get("difficulty", "mixed")
    language = data.get("language", "English")
    exam = (data.get("exam") or "general competitive exam").strip()
    make_notes = bool(data.get("notes", True))
    style = data.get("style", "fresh")        # fresh | mirror

    if not llm.any_key():
        return jsonify({"ok": False, "error": "No AI key found. Add GEMINI_API_KEY (free) or OPENAI_API_KEY to the .env file."})
    if not raw:
        return jsonify({"ok": False, "error": "Enter a topic, video URL, or paste some text."})

    # resolve the content
    src_label = ""
    if mode == "url":
        try:
            t = tr.get_transcript(raw)
            content = t["text"]
            gen_mode = "transcript"
            src_label = f'{t["language"]} transcript · {t["char_count"]} chars'
        except Exception as e:
            return jsonify({"ok": False, "error": f"Transcript failed: {e}"})
    elif mode == "text":
        content = raw
        gen_mode = "text"
        src_label = f"{len(raw)} chars of pasted text"
    else:
        content = raw
        gen_mode = "topic"
        src_label = f'topic: {raw}'

    try:
        result = llm.generate_quiz(
            content, mode=gen_mode, n=n, difficulty=difficulty,
            language=language, exam=exam, make_notes=make_notes, style=style)
        result["source"] = src_label
        result["count"] = len(result["questions"])
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------------------------ compare
@app.route("/api/compare", methods=["POST"])
def api_compare():
    data = request.get_json(force=True)
    channels = data.get("channels", [])
    key = _key(data)
    max_n = int(data.get("max_n", 25))
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    channels = [c.strip() for c in channels if c and c.strip()]
    if len(channels) < 2:
        return jsonify({"ok": False, "error": "Enter at least 2 channels to compare."})

    rows, errors = [], []
    for q in channels[:5]:
        try:
            cid = yt.resolve_channel_id(key, q)
            cv = yt.channel_videos(key, cid, max_n=max_n)
            rows.append(an.compare_metrics(cv["channel"], cv["videos"]))
        except Exception as e:
            errors.append(f"{q}: {e}")
    if not rows:
        return jsonify({"ok": False, "error": "Could not load any channel. " + " | ".join(errors)})
    return jsonify({"ok": True, "data": {"rows": rows, "errors": errors}})


# ------------------------------------------------------------------ keyword research
@app.route("/api/keywords", methods=["POST"])
def api_keywords():
    data = request.get_json(force=True)
    seed = (data.get("seed") or "").strip()
    key = _key(data)
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    if not seed:
        return jsonify({"ok": False, "error": "Enter a seed keyword / topic."})
    try:
        suggestions = yt.search_suggestions(seed)
        # keyword set: seed first, then suggestions, deduped, capped (quota: 100 units each)
        keywords, seen = [], set()
        for kw in [seed] + suggestions:
            k = kw.strip().lower()
            if k and k not in seen:
                seen.add(k)
                keywords.append(kw.strip())
            if len(keywords) >= 8:
                break

        items = []
        for kw in keywords:
            try:
                vids = yt.search_videos(key, kw, max_n=12, order="viewCount")
            except Exception:
                continue
            if not vids:
                continue
            views = sorted((v["views"] for v in vids), reverse=True)[:10]
            avg_views = int(sum(views) / len(views))
            floor_views = min(views)          # how strong the weakest top result is
            items.append({"keyword": kw, "avg_views": avg_views,
                          "floor_views": floor_views, "count": len(vids)})
        rows = an.score_keywords(items)
        return jsonify({"ok": True, "data": {"rows": rows, "seed": seed,
                                             "checked": len(items)}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------------------------ viral finder
@app.route("/api/viral", methods=["POST"])
def api_viral():
    data = request.get_json(force=True)
    query = (data.get("query") or "").strip()
    key = _key(data)
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    if not query:
        return jsonify({"ok": False, "error": "Enter a topic / niche to scan."})
    try:
        vids = yt.search_videos(key, query, max_n=45, order="viewCount")
        subs = yt.channel_subs_bulk(key, [v.get("channel_id") for v in vids])
        outliers = an.find_outliers(vids, subs, min_ratio=1.5, limit=25)
        return jsonify({"ok": True, "data": {"outliers": outliers,
                                             "scanned": len(vids)}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------------------------ content gap
@app.route("/api/gap", methods=["POST"])
def api_gap():
    data = request.get_json(force=True)
    yours = (data.get("your_channel") or "").strip()
    comp = (data.get("competitor") or "").strip()
    key = _key(data)
    max_n = int(data.get("max_n", 40))
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    if not yours or not comp:
        return jsonify({"ok": False, "error": "Enter both your channel and the competitor channel."})
    try:
        ycid = yt.resolve_channel_id(key, yours)
        ccid = yt.resolve_channel_id(key, comp)
        yv = yt.channel_videos(key, ycid, max_n=max_n)
        cv = yt.channel_videos(key, ccid, max_n=max_n)
        y_title = yv["channel"]["title"]
        c_title = cv["channel"]["title"]

        # Preferred: AI clusters titles into real topic gaps (ignores names/filler)
        if llm.any_key():
            your_titles = [v["title"] for v in yv["videos"]]
            comp_items = [{"title": v["title"], "views": v["views"]} for v in cv["videos"]]
            result = llm.content_gap_analysis(your_titles, comp_items, y_title, c_title)
            return jsonify({"ok": True, "data": {
                "mode": "ai",
                "gaps": result["gaps"],
                "your_title": y_title,
                "competitor_title": c_title,
            }})

        # Fallback: basic title-word diff (no Gemini key)
        gap = an.content_gap(yv["videos"], cv["videos"])
        return jsonify({"ok": True, "data": {
            "mode": "basic",
            "gap": gap,
            "your_title": y_title,
            "competitor_title": c_title,
        }})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ------------------------------------------------------------------ trends
@app.route("/api/watchlist", methods=["GET"])
def api_watchlist():
    store.init()
    watch = store.list_watch()
    counts = store.snapshot_counts()
    for w in watch:
        c = counts.get(w["channel_id"], {})
        w["snapshots"] = c.get("n", 0)
        w["last_snapshot"] = c.get("last")
    return jsonify({"ok": True, "data": watch})


@app.route("/api/watchlist/add", methods=["POST"])
def api_watchlist_add():
    data = request.get_json(force=True)
    key = _key(data)
    query = (data.get("channel") or "").strip()
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    if not query:
        return jsonify({"ok": False, "error": "Enter a channel to track."})
    try:
        store.init()
        cid = yt.resolve_channel_id(key, query)
        info = yt.channel_info(key, cid)
        store.add_watch(cid, info["title"], info["thumbnail"])
        # take a first snapshot immediately
        store.add_snapshot(cid, info["subscribers"], info["total_views"], info["video_count"])
        return jsonify({"ok": True, "data": {"channel_id": cid, "title": info["title"]}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/watchlist/remove", methods=["POST"])
def api_watchlist_remove():
    data = request.get_json(force=True)
    cid = (data.get("channel_id") or "").strip()
    store.init()
    store.remove_watch(cid)
    return jsonify({"ok": True})


@app.route("/api/snapshot", methods=["POST"])
def api_snapshot():
    """Capture a fresh snapshot for every watched channel."""
    key = _key()
    if not key:
        return jsonify({"ok": False, "error": "No API key found. Add YOUTUBE_API_KEY to the .env file."})
    store.init()
    watch = store.list_watch()
    if not watch:
        return jsonify({"ok": False, "error": "Watchlist is empty — add a channel first."})
    done, errors = 0, []
    for w in watch:
        try:
            info = yt.channel_info(key, w["channel_id"])
            store.add_snapshot(w["channel_id"], info["subscribers"],
                               info["total_views"], info["video_count"])
            done += 1
        except Exception as e:
            errors.append(f'{w["title"]}: {e}')
    return jsonify({"ok": True, "data": {"captured": done, "errors": errors}})


@app.route("/api/trends", methods=["POST"])
def api_trends():
    data = request.get_json(force=True)
    cid = (data.get("channel_id") or "").strip()
    store.init()
    return jsonify({"ok": True, "data": {"snapshots": store.get_snapshots(cid)}})


# ============================================================ QUESTION BANK
@app.route("/api/qbank/build", methods=["POST"])
def api_qbank_build():
    """
    Turn a video OR a whole playlist into mirrored questions, saved to the bank.
    Body: input (url), count (per video), difficulty, language, exam, max_videos.
    """
    data = request.get_json(force=True)
    src = (data.get("input") or "").strip()
    per_video = min(max(int(data.get("count", 15) or 15), 1), 100)
    difficulty = data.get("difficulty", "mixed")
    language = data.get("language", "English")
    exam = (data.get("exam") or "general competitive exam").strip()
    max_videos = min(max(int(data.get("max_videos", 5) or 5), 1), 15)

    if not src:
        return jsonify({"ok": False, "error": "Enter a video or playlist URL."})
    if not llm.any_key():
        return jsonify({"ok": False, "error": "No AI key found. Add GEMINI_API_KEY (or OPENAI_API_KEY) to .env."})

    store.init()
    key = _current_key()

    # resolve the source into a list of videos
    pid = yt.extract_playlist_id(src)
    videos = []
    try:
        if pid:
            if not key:
                return jsonify({"ok": False, "error": "Playlist needs YOUTUBE_API_KEY in .env."})
            for b in yt.playlist_video_basics(key, pid, max_n=max_videos):
                videos.append({"video_id": b["video_id"], "title": b["title"],
                               "url": f"https://www.youtube.com/watch?v={b['video_id']}"})
        else:
            vid = tr.extract_video_id(src)
            if not vid:
                return jsonify({"ok": False, "error": "Invalid video/playlist URL."})
            videos.append({"video_id": vid, "title": yt.get_video_title_no_key(vid),
                           "url": f"https://www.youtube.com/watch?v={vid}"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Could not read source: {e}"})

    results, total_added, total_skipped = [], 0, 0
    for v in videos:
        entry = {"title": v["title"], "url": v["url"]}
        try:
            t = tr.get_transcript(v["url"])
            gen = llm.generate_quiz(t["text"], mode="transcript", n=per_video,
                                    difficulty=difficulty, language=language,
                                    exam=exam, make_notes=False, style="mirror")
            items = []
            for q in gen["questions"]:
                q["exam"] = exam
                q["source_title"] = v["title"]
                q["source_url"] = v["url"]
                items.append(q)
            added, skipped = store.add_questions(items)
            total_added += added
            total_skipped += skipped
            entry.update({"ok": True, "detected": gen.get("source_count", 0),
                          "generated": len(items), "added": added, "skipped": skipped})
        except Exception as e:
            entry.update({"ok": False, "error": str(e)[:180]})
        results.append(entry)

    return jsonify({"ok": True, "data": {
        "results": results,
        "added": total_added,
        "skipped": total_skipped,
        "stats": store.qbank_stats(),
    }})


@app.route("/api/qbank/list", methods=["POST"])
def api_qbank_list():
    data = request.get_json(force=True)
    store.init()
    rows = store.list_questions(
        topic=(data.get("topic") or None),
        difficulty=(data.get("difficulty") or None),
        limit=int(data.get("limit", 500) or 500))
    return jsonify({"ok": True, "data": {
        "questions": rows, "stats": store.qbank_stats()}})


@app.route("/api/qbank/save-generated", methods=["POST"])
def api_qbank_save_generated():
    """Save an AI draft as review-gated inventory; never mark it publish-ready."""
    data = request.get_json(force=True) or {}
    raw_questions = data.get("questions") or []
    if not isinstance(raw_questions, list) or not raw_questions:
        return jsonify({"ok": False, "error": "No generated questions to save."})
    exam = (data.get("exam") or "general competitive exam").strip()[:100]
    source_topic = (data.get("source_topic") or "Market Radar draft").strip()[:180]
    items = []
    for raw in raw_questions[:200]:
        if not isinstance(raw, dict) or not str(raw.get("question", "")).strip():
            continue
        item = dict(raw)
        item.update({
            "exam": exam,
            "source_title": source_topic,
            "source_url": "",
            "review_status": "draft",
        })
        items.append(item)
    if not items:
        return jsonify({"ok": False, "error": "No valid generated questions to save."})
    store.init()
    added, skipped = store.add_questions(items)
    return jsonify({"ok": True, "data": {
        "added": added, "skipped": skipped, "review_status": "draft",
        "stats": store.qbank_stats(),
    }})


@app.route("/api/qbank/clear", methods=["POST"])
def api_qbank_clear():
    store.init()
    store.clear_qbank()
    return jsonify({"ok": True, "data": {"stats": store.qbank_stats()}})


@app.route("/api/qbank/export/<file_format>", methods=["GET"])
def api_qbank_export(file_format):
    """Download the currently filtered review bank as a polished PDF/XLSX."""
    file_format = (file_format or "").strip().lower()
    if file_format not in ("pdf", "xlsx"):
        return jsonify({"ok": False, "error": "Use pdf or xlsx export format."}), 404
    store.init()
    rows = store.list_questions(
        topic=(request.args.get("topic") or None),
        difficulty=(request.args.get("difficulty") or None),
        limit=5000,
    )
    if not rows:
        return jsonify({"ok": False, "error": "Question bank is empty."}), 400
    try:
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        if file_format == "xlsx":
            payload = exports.build_question_bank_xlsx(rows)
            return send_file(
                BytesIO(payload), as_attachment=True,
                download_name=f"faculty_review_bank_{stamp}.xlsx",
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        payload = exports.build_question_bank_pdf(rows)
        return send_file(
            BytesIO(payload), as_attachment=True,
            download_name=f"faculty_review_bank_{stamp}.pdf",
            mimetype="application/pdf",
        )
    except ImportError as exc:
        return jsonify({
            "ok": False,
            "error": f"Export dependency missing ({exc.name}). Run pip install -r requirements.txt.",
        }), 500


if __name__ == "__main__":
    store.init()
    # Debug (Werkzeug interactive debugger) is OFF by default — it allows
    # arbitrary code execution if the port is ever reachable. Turn it on
    # only for local dev via  FLASK_DEBUG=1  in the environment / .env.
    debug = os.getenv("FLASK_DEBUG", "").strip().lower() in ("1", "true", "yes", "on")
    print("\n  YouTube Analyzer running at  http://127.0.0.1:5002\n")
    app.run(host="127.0.0.1", port=5002, debug=debug)
