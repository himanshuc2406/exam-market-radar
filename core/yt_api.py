"""
YouTube Data API v3 wrapper (uses plain HTTP requests — no heavy client lib).
All functions take api_key as the first argument.

Quota notes (free tier = 10,000 units/day):
  search       = 100 units per call   (expensive — use sparingly)
  videos       = 1 unit
  channels     = 1 unit
  commentThreads = 1 unit
  playlistItems  = 1 unit
"""
import re
import requests

BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeAPIError(Exception):
    pass


def _get(endpoint, api_key, **params):
    params["key"] = api_key
    r = requests.get(f"{BASE}/{endpoint}", params=params, timeout=20)
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        raise YouTubeAPIError(f"API error ({r.status_code}): {msg}")
    return r.json()


# ---------------------------------------------------------------- channel resolve
def resolve_channel_id(api_key, query):
    """
    Accepts a channel URL, @handle, UC... id, or a plain channel name.
    Returns the UC... channel id.
    """
    q = str(query).strip()

    # Direct channel id
    m = re.search(r'(UC[a-zA-Z0-9_-]{22})', q)
    if m:
        return m.group(1)

    # @handle (from URL or typed)
    handle = None
    m = re.search(r'youtube\.com/@([a-zA-Z0-9_.-]+)', q)
    if m:
        handle = m.group(1)
    elif q.startswith('@'):
        handle = q[1:]

    if handle:
        data = _get("channels", api_key, part="id", forHandle=handle)
        items = data.get("items", [])
        if items:
            return items[0]["id"]

    # /c/name or /user/name or plain text → search
    name = q
    m = re.search(r'youtube\.com/(?:c|user)/([a-zA-Z0-9_.-]+)', q)
    if m:
        name = m.group(1)

    data = _get("search", api_key, part="snippet", q=name,
                type="channel", maxResults=1)
    items = data.get("items", [])
    if items:
        return items[0]["snippet"]["channelId"]

    raise YouTubeAPIError(f"Could not resolve channel: {query}")


# ---------------------------------------------------------------- channel info
def channel_info(api_key, channel_id):
    data = _get("channels", api_key,
                part="snippet,statistics,contentDetails", id=channel_id)
    items = data.get("items", [])
    if not items:
        raise YouTubeAPIError("Channel not found")
    it = items[0]
    stats = it.get("statistics", {})
    return {
        "channel_id": channel_id,
        "title": it["snippet"]["title"],
        "description": it["snippet"].get("description", ""),
        "thumbnail": it["snippet"]["thumbnails"]["medium"]["url"],
        "published_at": it["snippet"].get("publishedAt", ""),
        "subscribers": int(stats.get("subscriberCount", 0)),
        "total_views": int(stats.get("viewCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "uploads_playlist": it["contentDetails"]["relatedPlaylists"]["uploads"],
    }


# ---------------------------------------------------------------- channel videos
def channel_videos(api_key, channel_id, max_n=25):
    """Return most-recent videos of a channel with full stats."""
    info = channel_info(api_key, channel_id)
    uploads = info["uploads_playlist"]

    # 1) collect video ids from the uploads playlist
    video_ids, token = [], None
    while len(video_ids) < max_n:
        data = _get("playlistItems", api_key, part="contentDetails",
                    playlistId=uploads, maxResults=50, pageToken=token or "")
        for it in data.get("items", []):
            video_ids.append(it["contentDetails"]["videoId"])
        token = data.get("nextPageToken")
        if not token:
            break
    video_ids = video_ids[:max_n]

    # 2) fetch stats in batches of 50
    videos = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        data = _get("videos", api_key,
                    part="snippet,statistics,contentDetails", id=",".join(batch))
        for it in data.get("items", []):
            videos.append(_video_row(it))

    return {"channel": info, "videos": videos}


def _video_row(it):
    stats = it.get("statistics", {})
    views = int(stats.get("viewCount", 0))
    likes = int(stats.get("likeCount", 0))
    comments = int(stats.get("commentCount", 0))
    engagement = round((likes + comments) / views * 100, 2) if views else 0.0
    iso_dur = it.get("contentDetails", {}).get("duration", "")
    return {
        "video_id": it["id"],
        "title": it["snippet"]["title"],
        "published_at": it["snippet"]["publishedAt"],
        "thumbnail": it["snippet"]["thumbnails"]["medium"]["url"],
        "duration": _parse_duration(iso_dur),
        "duration_seconds": _duration_seconds(iso_dur),
        "views": views,
        "likes": likes,
        "comments": comments,
        "engagement": engagement,
        "url": f"https://www.youtube.com/watch?v={it['id']}",
    }


# ---------------------------------------------------------------- playlist
def extract_playlist_id(url):
    """Pull a playlist id (PL... / UU... / etc.) from a URL, or None."""
    m = re.search(r'[?&]list=([a-zA-Z0-9_-]+)', str(url))
    return m.group(1) if m else None


def playlist_video_basics(api_key, playlist_id, max_n=50):
    """Return [{video_id, title}] for a playlist (cheap: 1 unit / 50 items)."""
    out, token = [], None
    while len(out) < max_n:
        data = _get("playlistItems", api_key, part="snippet,contentDetails",
                    playlistId=playlist_id, maxResults=50, pageToken=token or "")
        for it in data.get("items", []):
            out.append({
                "video_id": it["contentDetails"]["videoId"],
                "title": it["snippet"].get("title", ""),
            })
        token = data.get("nextPageToken")
        if not token:
            break
    return out[:max_n]


# ---------------------------------------------------------------- single video
def video_details(api_key, video_id):
    data = _get("videos", api_key,
                part="snippet,statistics,contentDetails", id=video_id)
    items = data.get("items", [])
    if not items:
        raise YouTubeAPIError("Video not found")
    it = items[0]
    row = _video_row(it)
    row["channel_title"] = it["snippet"]["channelTitle"]
    row["channel_id"] = it["snippet"]["channelId"]
    row["description"] = it["snippet"].get("description", "")
    row["tags"] = it["snippet"].get("tags", [])
    return row


# ---------------------------------------------------------------- comments
def video_comments(api_key, video_id, max_n=100):
    comments, token = [], None
    while len(comments) < max_n:
        try:
            data = _get("commentThreads", api_key, part="snippet",
                        videoId=video_id, maxResults=100, order="relevance",
                        pageToken=token or "", textFormat="plainText")
        except YouTubeAPIError as e:
            # comments disabled → return what we have (empty)
            if "disabled" in str(e).lower() or "commentsDisabled" in str(e):
                break
            raise
        for it in data.get("items", []):
            sn = it["snippet"]["topLevelComment"]["snippet"]
            comments.append({
                "author": sn.get("authorDisplayName", ""),
                "text": sn.get("textDisplay", ""),
                "likes": int(sn.get("likeCount", 0)),
                "published_at": sn.get("publishedAt", ""),
            })
        token = data.get("nextPageToken")
        if not token:
            break
    return comments[:max_n]


# ---------------------------------------------------------------- search
def search_videos(api_key, query, max_n=25, order="relevance",
                  published_after=None, region_code="IN", relevance_language=None):
    """Search public videos, optionally constrained to a recent market window.

    ``published_after`` must be an RFC-3339 timestamp.  Region/language filters
    keep an Indian exam scan relevant without changing older callers.
    """
    ids, token = [], None
    while len(ids) < max_n:
        params = {"part": "snippet", "q": query, "type": "video",
                  "maxResults": min(50, max_n), "order": order,
                  "pageToken": token or ""}
        if published_after:
            params["publishedAfter"] = published_after
        if region_code:
            params["regionCode"] = region_code
        if relevance_language:
            params["relevanceLanguage"] = relevance_language
        data = _get("search", api_key, **params)
        for it in data.get("items", []):
            ids.append(it["id"]["videoId"])
        token = data.get("nextPageToken")
        if not token:
            break
    ids = ids[:max_n]

    videos = []
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        if not batch:
            continue
        data = _get("videos", api_key,
                    part="snippet,statistics,contentDetails", id=",".join(batch))
        for it in data.get("items", []):
            row = _video_row(it)
            row["channel_title"] = it["snippet"]["channelTitle"]
            row["channel_id"] = it["snippet"]["channelId"]
            videos.append(row)
    return videos


# ---------------------------------------------------------------- suggestions
def search_suggestions(seed, lang="en"):
    """
    Related search queries from Google's YouTube autocomplete (no API key,
    no quota). This is what VidIQ/TubeBuddy use for keyword ideas.
    """
    import json as _json
    try:
        r = requests.get("https://suggestqueries.google.com/complete/search",
                         params={"client": "firefox", "ds": "yt", "q": seed, "hl": lang},
                         timeout=10)
        if r.status_code != 200:
            return []
        try:
            data = r.json()
        except Exception:
            data = _json.loads(r.content.decode("utf-8", "ignore"))
        return data[1] if isinstance(data, list) and len(data) > 1 else []
    except Exception:
        return []


# ---------------------------------------------------------------- subs bulk
def channel_subs_bulk(api_key, channel_ids):
    """Map {channel_id: subscriber_count} for a list of channel ids."""
    out = {}
    ids = list(dict.fromkeys([c for c in channel_ids if c]))
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        data = _get("channels", api_key, part="statistics", id=",".join(batch))
        for it in data.get("items", []):
            out[it["id"]] = int(it.get("statistics", {}).get("subscriberCount", 0))
    return out


# ---------------------------------------------------------------- helpers
def _parse_duration(iso):
    """Convert ISO-8601 duration (PT1H2M3S) to H:MM:SS / MM:SS."""
    if not iso:
        return ""
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not m:
        return ""
    h = int(m.group(1) or 0)
    mnt = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    if h:
        return f"{h}:{mnt:02d}:{s:02d}"
    return f"{mnt}:{s:02d}"


def _duration_seconds(iso):
    """ISO-8601 duration (PT1H2M3S) → total seconds."""
    if not iso:
        return 0
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def get_video_title_no_key(video_id):
    """Fetch a video title via oEmbed (no API key needed)."""
    import urllib.parse
    try:
        u = ("https://www.youtube.com/oembed?url=" +
             urllib.parse.quote(f"https://www.youtube.com/watch?v={video_id}") +
             "&format=json")
        r = requests.get(u, timeout=10)
        if r.status_code == 200:
            return r.json().get("title", video_id)
    except Exception:
        pass
    return video_id
