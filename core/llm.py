"""
Gemini (Google AI) wrapper — generates quiz MCQs / notes from a
transcript, a topic, or pasted text. Uses the REST API (no heavy SDK).

Get a free key: https://aistudio.google.com/apikey
Put it in .env as  GEMINI_API_KEY=xxxx   (optionally GEMINI_MODEL=...)
"""
import os
import re
import json
import time
import requests
from dotenv import dotenv_values

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MODEL = "gemini-2.5-flash"
# how many transcript characters to send. Large enough to capture a full
# ~2 hr solving session's questions without truncating.
MAX_CHARS = 150000
# seconds to wait for the model (big generations are slow); override via LLM_TIMEOUT
DEFAULT_TIMEOUT = 240


class LLMError(Exception):
    pass


def gemini_key():
    """Read GEMINI_API_KEY fresh from environment or the .env file."""
    k = os.getenv("GEMINI_API_KEY", "").strip()
    if k:
        return k
    try:
        vals = dotenv_values(os.path.join(HERE, ".env"))
        return (vals.get("GEMINI_API_KEY") or "").strip()
    except Exception:
        return ""


def _model():
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def gemini_generate(prompt, key=None, model=None, temperature=0.4, json_mode=True):
    """Low-level call: send a prompt to Gemini, return the text response."""
    key = key or gemini_key()
    if not key:
        raise LLMError("No Gemini API key. Add GEMINI_API_KEY to the .env file.")
    model = model or _model()

    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    gen_cfg = {"temperature": temperature}
    if json_mode:
        gen_cfg["response_mime_type"] = "application/json"

    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": gen_cfg,
    }

    # Retry transient overloads (503 high demand / 429 rate limit). A read
    # timeout means the model is just taking very long — retrying wastes time,
    # so fail fast with a helpful message instead.
    timeout = int(_env("LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    r = None
    for i in range(3):
        try:
            r = requests.post(url, json=body, timeout=timeout)
        except requests.exceptions.Timeout:
            raise LLMError(f"Gemini took longer than {timeout}s. Try fewer questions "
                           f"or a shorter source (very long videos + 50–100 questions are heavy).")
        except requests.RequestException as e:
            if i == 2:
                raise LLMError(f"Network error contacting Gemini: {e}")
            time.sleep(1.5 * (i + 1)); continue
        if r.status_code in (429, 500, 503) and i < 2:
            time.sleep(1.5 * (i + 1)); continue
        break

    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        if r.status_code == 503:
            msg = ("Gemini is busy right now (high demand). Wait a few seconds "
                   "and try again.")
        elif r.status_code == 429:
            msg = ("Gemini free-tier quota reached. Wait a minute and retry, use a "
                   "smaller question count, or in .env either enable billing on the key "
                   "or set LLM_PROVIDER=openai (with OPENAI_API_KEY).")
        elif "not found" in msg.lower() or "not supported" in msg.lower():
            msg += f"  (try a different GEMINI_MODEL in .env; current: {model})"
        raise LLMError(f"Gemini error ({r.status_code}): {msg}")

    data = r.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        # blocked / empty
        fb = data.get("promptFeedback", {})
        raise LLMError(f"Gemini returned no text. Feedback: {fb}")


# ================================================================
#   PROVIDER LAYER — pick Gemini / OpenAI / a custom {prompt} endpoint
# ================================================================
def _env(name):
    """Read a var fresh from environment or the .env file."""
    v = os.getenv(name, "").strip()
    if v:
        return v
    try:
        return (dotenv_values(os.path.join(HERE, ".env")).get(name) or "").strip()
    except Exception:
        return ""


def openai_key():
    return _env("OPENAI_API_KEY")


def custom_url():
    return _env("CUSTOM_GPT_URL")


def active_provider():
    """
    Which AI backend to use. Set LLM_PROVIDER in .env (openai|gemini|custom),
    else auto-pick the first one that has a key/url (gemini preferred as default).
    """
    p = _env("LLM_PROVIDER").lower()
    if p in ("openai", "gemini", "custom"):
        return p
    if gemini_key():
        return "gemini"
    if openai_key():
        return "openai"
    if custom_url():
        return "custom"
    return "gemini"


def any_key():
    """True if ANY provider is configured."""
    return bool(gemini_key() or openai_key() or custom_url())


def openai_generate(prompt, key=None, model=None, temperature=0.4, json_mode=True):
    """Call OpenAI Chat Completions (GPT-4o / GPT-5 / etc.)."""
    key = key or openai_key()
    if not key:
        raise LLMError("No OpenAI key. Add OPENAI_API_KEY to the .env file.")
    model = model or _env("OPENAI_MODEL") or "gpt-4o-mini"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/json"}

    timeout = int(_env("LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    for i in range(3):
        try:
            r = requests.post("https://api.openai.com/v1/chat/completions",
                             json=body, headers=headers, timeout=timeout)
        except requests.exceptions.Timeout:
            raise LLMError(f"OpenAI took longer than {timeout}s. Try fewer questions or a shorter source.")
        except requests.RequestException as e:
            if i == 2:
                raise LLMError(f"Network error contacting OpenAI: {e}")
            time.sleep(1.5 * (i + 1)); continue
        if r.status_code in (429, 500, 503) and i < 2:
            time.sleep(1.5 * (i + 1)); continue
        break

    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", r.text)
        except Exception:
            msg = r.text
        raise LLMError(f"OpenAI error ({r.status_code}): {msg}")
    try:
        return r.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError):
        raise LLMError("OpenAI returned no text.")


def custom_generate(prompt):
    """POST {prompt} to a custom endpoint that returns the model's text (like a company GPT proxy)."""
    url = custom_url()
    if not url:
        raise LLMError("No CUSTOM_GPT_URL set in the .env file.")
    timeout = int(_env("LLM_TIMEOUT") or DEFAULT_TIMEOUT)
    for i in range(3):
        try:
            r = requests.post(url, json={"prompt": prompt}, timeout=timeout)
        except requests.exceptions.Timeout:
            raise LLMError(f"Custom endpoint took longer than {timeout}s. Try fewer questions.")
        except requests.RequestException as e:
            if i == 2:
                raise LLMError(f"Network error contacting custom endpoint: {e}")
            time.sleep(1.5 * (i + 1)); continue
        if r.status_code in (429, 500, 502, 503) and i < 2:
            time.sleep(1.5 * (i + 1)); continue
        break
    if r.status_code != 200:
        raise LLMError(f"Custom endpoint error ({r.status_code}): {r.text[:200]}")
    return r.text


def generate_text(prompt, json_mode=True):
    """Dispatch a prompt to whichever provider is active."""
    prov = active_provider()
    if prov == "openai":
        return openai_generate(prompt, json_mode=json_mode)
    if prov == "custom":
        return custom_generate(prompt)
    return gemini_generate(prompt, json_mode=json_mode)


def _extract_json(text):
    """Pull a JSON object out of the model's reply (handles code fences)."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?', '', text).strip()
    text = re.sub(r'```$', '', text).strip()
    try:
        return json.loads(text)
    except Exception:
        # find the first {...} block
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            return json.loads(m.group(0))
        raise LLMError("Could not parse AI response as JSON")


def content_gap_analysis(your_titles, comp_items, your_name="my channel",
                         comp_name="the competitor", key=None):
    """
    Use Gemini to find real CONTENT TOPICS the competitor covers that the user
    doesn't — clustering titles into themes, ignoring presenter names & filler.
    comp_items: list of {title, views}.  Returns {"gaps": [ {...} ]}.
    """
    comp_items = sorted(comp_items, key=lambda x: x.get("views", 0), reverse=True)[:60]
    comp_lines = "\n".join(f"- {c['title']}  ({c.get('views', 0)} views)" for c in comp_items)
    your_lines = "\n".join(f"- {t}" for t in your_titles[:80]) or "(no videos)"

    prompt = f"""You are a YouTube content strategist analysing two channels in the same niche.

COMPETITOR "{comp_name}" — their videos (title, views):
{comp_lines}

MY CHANNEL "{your_name}" — my videos:
{your_lines}

Task: find the main CONTENT TOPICS / THEMES the competitor covers that MY channel
does NOT cover (or barely covers). These are my content gaps / opportunities.

Rules:
- Output real, actionable topics — exam names, subjects, question types, recurring
  series, formats. NEVER output presenter/teacher names, generic filler
  (today, live, part, all, new, latest) or dates as a "topic".
- Merge similar titles into ONE topic.
- Rank by opportunity: competitor's audience interest (views) AND how uncovered it is on my channel.
- Max 12 gaps. If coverage overlaps heavily, return fewer.

Return ONLY JSON:
{{
  "gaps": [
    {{"topic": "short topic name",
      "why": "one line on why it's an opportunity",
      "examples": ["a competitor title", "another competitor title"],
      "priority": "high|medium|low"}}
  ]
}}"""

    raw = generate_text(prompt, json_mode=True)
    data = _extract_json(raw)
    gaps = []
    for g in data.get("gaps", []):
        topic = str(g.get("topic", "")).strip()
        if not topic:
            continue
        gaps.append({
            "topic": topic,
            "why": str(g.get("why", "")).strip(),
            "examples": [str(x).strip() for x in (g.get("examples") or [])][:3],
            "priority": (str(g.get("priority", "")).strip().lower() or "medium"),
        })
    return {"gaps": gaps}


def cluster_doubts(candidates, topic="this topic", max_items=250, key=None):
    """
    Doubt Radar core: cluster student doubt-comments into concept-level pain
    points. The LLM only does the SEMANTIC grouping (assigns each comment to a
    cluster); frequency, upvotes and video-spread are computed HERE from the
    real data — never taken from the model — so the numbers are trustworthy.

    candidates: list of {text, likes, timestamps, video_title, video_url}
    Returns a demand-ranked list of cluster dicts.
    """
    # keep the most-upvoted doubts within a budget (keeps the prompt sane/cheap)
    items = sorted(candidates, key=lambda c: c.get("likes", 0), reverse=True)[:max_items]
    if not items:
        return []

    lines = []
    for i, c in enumerate(items):
        txt = re.sub(r'\s+', ' ', c.get("text", "")).strip()[:240]
        lines.append(f'[{i}] ({c.get("likes", 0)} likes) {txt}')
    listing = "\n".join(lines)

    prompt = f"""You are an EdTech content strategist for Indian competitive-exam prep.
Below are student comments (each with an [id]) from YouTube videos about "{topic}".
They are the questions, doubts and confusions students posted.

Group them into DISTINCT concept-level doubts — the specific things students struggle with.
Rules:
- A cluster = ONE concept/sub-topic students are confused about
  (e.g. "Boats & Streams: when to add vs subtract the stream speed"),
  NEVER a generic bucket like "questions" or "doubts".
- Assign each id to at most one cluster. Leave out pure spam / thanks / off-topic.
- Merge near-duplicates. Aim for 5-15 meaningful clusters, most important first.
- For each cluster give: a short specific "concept", a one-line "summary" of the
  confusion, a concrete "content_idea" (the exact video/notes to make to fix it),
  and "priority" (high|medium|low).

Return ONLY valid JSON:
{{"clusters":[
  {{"concept":"...","summary":"...","content_idea":"...","priority":"high","member_ids":[0,3,7]}}
]}}

Comments:
{listing}"""

    raw = generate_text(prompt, json_mode=True)
    data = _extract_json(raw)

    clusters = []
    for cl in data.get("clusters", []):
        ids = []
        for x in (cl.get("member_ids") or []):
            try:
                ix = int(x)
            except Exception:
                continue
            if 0 <= ix < len(items):
                ids.append(ix)
        ids = sorted(set(ids))
        if not ids:
            continue
        members = [items[i] for i in ids]
        total_likes = sum(m.get("likes", 0) for m in members)
        videos = {m.get("video_title", "") for m in members if m.get("video_title")}
        tstamps = []
        for m in members:
            tstamps.extend(m.get("timestamps", []))
        examples = sorted(members, key=lambda m: m.get("likes", 0), reverse=True)[:3]
        clusters.append({
            "concept": str(cl.get("concept", "")).strip(),
            "summary": str(cl.get("summary", "")).strip(),
            "content_idea": str(cl.get("content_idea", "")).strip(),
            "priority": (str(cl.get("priority", "")).strip().lower() or "medium"),
            "count": len(members),
            "total_likes": total_likes,
            "video_count": len(videos),
            "timestamps": tstamps[:6],
            "examples": [{"text": e.get("text", "")[:300], "likes": e.get("likes", 0),
                          "video_title": e.get("video_title", ""),
                          "video_url": e.get("video_url", "")} for e in examples],
        })

    # demand = how many students (frequency, weighted) + how hard they upvoted
    for c in clusters:
        c["demand"] = c["count"] * 2 + c["total_likes"]
    clusters.sort(key=lambda c: c["demand"], reverse=True)
    return clusters


def generate_quiz(content, mode="transcript", n=10, difficulty="mixed",
                  language="English", exam="general competitive exam",
                  make_notes=True, style="fresh", key=None):
    """
    Generate MCQs (and optional notes) from a transcript / topic / text.

    mode:  'transcript' | 'topic' | 'text'
    style: 'fresh'  -> brand-new questions on the topic
           'mirror' -> PARALLEL versions of the questions found in the source
                       (same concept & difficulty, changed numbers/names/values)
    Returns dict: {"questions": [...], "notes": "..."}
    """
    content = (content or "").strip()
    if not content:
        raise LLMError("Nothing to generate from — provide a topic, transcript, or text.")

    if mode == "topic":
        source_desc = f'the topic: "{content}"'
        style = "fresh"  # nothing to mirror from a bare topic
    else:
        if len(content) > MAX_CHARS:
            content = content[:MAX_CHARS]
        source_desc = "the following content (a lecture transcript or a set of questions)"

    notes_line = ('Also add a "notes" field: a 4-6 line summary of the key concepts. '
                  if make_notes else 'Set "notes" to an empty string. ')

    if style == "mirror":
        task = f"""You are an expert question-setter for Indian {exam} exams.
The content below contains existing exam questions (often inside a spoken solving transcript).
Target number of questions to produce: {n}.

Mirror rules (very important):
- FIRST, scan the ENTIRE content and identify how many DISTINCT questions exist. Put that
  number in "source_count". Do not miss any — the content may contain many questions.
- Create a PARALLEL / MIRROR version of EVERY source question (aim to cover all of them).
- If the target {n} is GREATER than source_count, generate ADDITIONAL parallel questions in the
  SAME patterns, sub-topics and difficulty as the source, until you reach {n} total.
- If the target {n} is LESS than source_count, mirror the {n} most representative questions.
- Mirroring = keep the SAME concept, logic, structure, question type and difficulty, but CHANGE
  every specific value: all numbers, names, people/place/entity names (e.g. "Ram" -> "A" or a
  different name), currencies and quantities — so nothing is a verbatim copy and the answers differ.
- Never reproduce a source sentence word-for-word. Rephrase in your own words.
- Each question: EXACTLY 4 options, one correct answer, a 1-2 line explanation, a short "topic"."""
    else:
        task = f"""You are an expert question-setter for Indian {exam} exams.
Generate {n} high-quality, original multiple-choice questions (MCQs) based on {source_desc}.

Rules:
- Each question must have EXACTLY 4 options and exactly one correct answer.
- Vary the sub-topics; avoid trivial or repetitive questions.
- If observed student misconceptions are provided, convert their mistaken logic
  into plausible distractors; never copy a student's sentence or identity.
- Independently solve every question and verify that the marked option is correct.
- Add a concise 1-2 line explanation and a short "topic" for each."""

    prompt = f"""{task}

- Difficulty level: {difficulty}.
- Write questions and options in {language}.
{notes_line}

Return ONLY valid JSON in exactly this shape:
{{
  "source_count": 0,
  "questions": [
    {{
      "question": "...",
      "options": ["...", "...", "...", "..."],
      "answer_index": 0,
      "explanation": "...",
      "topic": "...",
      "difficulty": "easy|medium|hard"
    }}
  ],
  "notes": "..."
}}
("source_count" = number of distinct questions detected in the source; 0 for topic-based.)

{"Content:" if mode != "topic" else ""}
{content if mode != "topic" else ""}"""

    raw = generate_text(prompt, json_mode=True)
    data = _extract_json(raw)

    try:
        source_count = int(data.get("source_count", 0) or 0)
    except Exception:
        source_count = 0

    # normalise
    questions = []
    for q in data.get("questions", []):
        opts = q.get("options", [])
        if len(opts) != 4:
            continue
        ai = q.get("answer_index", 0)
        try:
            ai = int(ai)
        except Exception:
            ai = 0
        ai = max(0, min(ai, len(opts) - 1))
        questions.append({
            "question": str(q.get("question", "")).strip(),
            "options": [str(o).strip() for o in opts],
            "answer_index": ai,
            "explanation": str(q.get("explanation", "")).strip(),
            "topic": str(q.get("topic", "")).strip(),
            "difficulty": str(q.get("difficulty", "")).strip(),
        })

    return {"questions": questions, "notes": str(data.get("notes", "")).strip(),
            "source_count": source_count}
