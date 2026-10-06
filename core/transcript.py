"""
Transcript extraction — works with both old (0.6.x) and new (1.x)
versions of youtube-transcript-api. No API key needed.

Resilient to YouTube's occasional 502 / transient errors: retries each
fetch a few times and falls back to other available transcripts.
"""
import re
import time


def extract_video_id(url):
    """Extract 11-char YouTube video ID from any URL format (or return the ID)."""
    url = str(url).strip()
    if re.match(r'^[a-zA-Z0-9_-]{11}$', url):
        return url
    patterns = [
        r'[?&]v=([a-zA-Z0-9_-]{11})',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/embed/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/live/([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _is_transient(err):
    """Detect YouTube's transient errors (502/503/timeout) worth retrying."""
    s = str(err).lower()
    return any(x in s for x in (
        '502', '503', '500', 'bad gateway', 'service unavailable',
        'timed out', 'timeout', 'connection', 'temporarily'))


def _retry(fn, tries=4, delay=1.2):
    """Call fn(), retrying on transient errors with a growing delay."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if not _is_transient(e) or i == tries - 1:
                raise
            time.sleep(delay * (i + 1))
    raise last


def _get_transcript_list(video_id):
    """Return a TranscriptList, handling both old and new library APIs."""
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi

    def _call():
        if hasattr(api, 'list_transcripts'):      # old API (<=0.6.x)
            return api.list_transcripts(video_id)
        return api().list(video_id)               # new API (>=1.0 instance method)

    return _retry(_call)


def _to_entries(fetched):
    """Normalise a fetched transcript into a list of {text, start, duration} dicts."""
    if hasattr(fetched, 'to_raw_data'):
        try:
            return fetched.to_raw_data()
        except Exception:
            pass
    out = []
    for it in fetched:
        if isinstance(it, dict):
            out.append({
                'text': it.get('text', ''),
                'start': it.get('start', 0),
                'duration': it.get('duration', 0),
            })
        else:
            out.append({
                'text': getattr(it, 'text', ''),
                'start': getattr(it, 'start', 0),
                'duration': getattr(it, 'duration', 0),
            })
    return out


def format_time(seconds):
    """Convert seconds to MM:SS or H:MM:SS."""
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h > 0:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m:02d}:{s:02d}'


def _ordered_candidates(transcript_list, preferred):
    """
    Build an ordered list of transcript objects to try:
      manual(preferred) > generated(preferred) > every other available one.
    So if the first choice 502s, we can fall back to another track.
    """
    candidates = []
    for finder in ('find_manually_created_transcript', 'find_generated_transcript'):
        try:
            candidates.append(getattr(transcript_list, finder)(preferred))
        except Exception:
            pass
    # append everything else (dedup by language_code)
    seen = {c.language_code for c in candidates}
    for t in transcript_list:
        if t.language_code not in seen:
            candidates.append(t)
            seen.add(t.language_code)
    return candidates


def get_transcript(url, preferred_langs=('hi', 'en')):
    """
    Fetch the transcript for a video.
    Priority: manual (hi>en) > auto-generated (hi>en) > any available.
    Retries transient (502) errors and falls back across languages.
    Returns a dict; raises on hard failure.
    """
    video_id = extract_video_id(url)
    if not video_id:
        raise ValueError('Invalid YouTube URL')

    preferred = list(preferred_langs)
    transcript_list = _get_transcript_list(video_id)
    candidates = _ordered_candidates(transcript_list, preferred)
    if not candidates:
        raise RuntimeError('No captions available for this video')

    last_err = None
    for transcript in candidates:
        try:
            fetched = _retry(lambda: transcript.fetch())
        except Exception as e:
            last_err = e
            continue  # this track failed (e.g. 502) — try the next one

        entries = _to_entries(fetched)
        text = ' '.join(e['text'].replace('\n', ' ').strip()
                        for e in entries if e['text'].strip())
        if not text:
            continue

        return {
            'video_id': video_id,
            'language': transcript.language,
            'language_code': transcript.language_code,
            'is_generated': transcript.is_generated,
            'text': text,
            'entries': entries,
            'char_count': len(text),
            'line_count': len(entries),
        }

    # everything failed
    if last_err and _is_transient(last_err):
        raise RuntimeError(
            "YouTube temporarily refused the transcript (502). "
            "Try again in a few seconds — this usually clears on retry.")
    raise last_err or RuntimeError('Could not retrieve transcript')
