"""
Tiny SQLite store for Trend Tracking:
  - watchlist: channels the user follows
  - snapshots: point-in-time (subs / views / video count) for each channel

YouTube's API only returns *current* numbers, so to see trends we save our
own snapshots over time. Run "Capture snapshot" (daily) to build history.
"""
import os
import re
import sqlite3
import hashlib
from datetime import datetime, timezone


def _utcnow():
    """Naive UTC timestamp (utcnow() is deprecated in Python 3.12+)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(HERE, "data")
DB_PATH = os.path.join(DATA_DIR, "trends.db")


def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS watchlist (
            channel_id TEXT PRIMARY KEY,
            title      TEXT,
            thumbnail  TEXT,
            added_at   TEXT
        )""")
        c.execute("""CREATE TABLE IF NOT EXISTS snapshots (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id   TEXT,
            ts           TEXT,
            subscribers  INTEGER,
            total_views  INTEGER,
            video_count  INTEGER
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_snap_chan ON snapshots(channel_id, ts)")
        # ---- Question Bank (the Factory) ----
        c.execute("""CREATE TABLE IF NOT EXISTS qbank (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            qhash        TEXT UNIQUE,
            question     TEXT,
            opt_a        TEXT, opt_b TEXT, opt_c TEXT, opt_d TEXT,
            answer_index INTEGER,
            explanation  TEXT,
            topic        TEXT,
            difficulty   TEXT,
            exam         TEXT,
             source_title TEXT,
             source_url   TEXT,
             review_status TEXT DEFAULT 'draft',
             created_at   TEXT
         )""")
        columns = {r[1] for r in c.execute("PRAGMA table_info(qbank)").fetchall()}
        if "review_status" not in columns:
            c.execute("ALTER TABLE qbank ADD COLUMN review_status TEXT DEFAULT 'draft'")
        c.execute("CREATE INDEX IF NOT EXISTS idx_qbank_topic ON qbank(topic)")


# ================================================================ Question Bank
def _qhash(text):
    """Fingerprint a question (normalised) to dedupe near-identical entries."""
    norm = re.sub(r'\s+', '', (text or '').lower())
    return hashlib.sha1(norm.encode('utf-8')).hexdigest()


def add_questions(items):
    """Insert a list of question dicts. Returns (added, skipped_duplicates)."""
    added = skipped = 0
    with _conn() as c:
        for q in items:
            opts = list(q.get("options") or []) + ["", "", "", ""]
            try:
                c.execute("""INSERT INTO qbank
                    (qhash, question, opt_a, opt_b, opt_c, opt_d, answer_index,
                     explanation, topic, difficulty, exam, source_title, source_url,
                     review_status, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (_qhash(q.get("question", "")), q.get("question", ""),
                     opts[0], opts[1], opts[2], opts[3],
                     int(q.get("answer_index", 0) or 0), q.get("explanation", ""),
                     q.get("topic", ""), q.get("difficulty", ""), q.get("exam", ""),
                     q.get("source_title", ""), q.get("source_url", ""),
                     q.get("review_status", "draft"),
                     _utcnow().isoformat()))
                added += 1
            except sqlite3.IntegrityError:
                skipped += 1
    return added, skipped


def list_questions(topic=None, difficulty=None, exam=None, limit=1000):
    q = "SELECT * FROM qbank WHERE 1=1"
    args = []
    if topic:
        q += " AND topic=?"; args.append(topic)
    if difficulty:
        q += " AND difficulty=?"; args.append(difficulty)
    if exam:
        q += " AND exam=?"; args.append(exam)
    q += " ORDER BY id DESC LIMIT ?"; args.append(int(limit))
    with _conn() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def qbank_stats():
    with _conn() as c:
        total = c.execute("SELECT COUNT(*) n FROM qbank").fetchone()["n"]
        topics = [dict(r) for r in c.execute(
            "SELECT topic, COUNT(*) n FROM qbank WHERE topic!='' "
            "GROUP BY topic ORDER BY n DESC LIMIT 25").fetchall()]
        diffs = [dict(r) for r in c.execute(
            "SELECT difficulty, COUNT(*) n FROM qbank WHERE difficulty!='' "
            "GROUP BY difficulty ORDER BY n DESC").fetchall()]
        sources = c.execute(
            "SELECT COUNT(DISTINCT source_url) n FROM qbank").fetchone()["n"]
    return {"total": total, "topics": topics, "difficulties": diffs, "sources": sources}


def count_questions_for_topic(topic):
    """Best-effort inventory count used by the Market Command Center.

    Generated topic labels are not yet tied to a syllabus taxonomy, so this
    counts case-insensitive topic/question mentions instead of pretending the
    inventory mapping is exact.
    """
    words = [w for w in re.findall(r'[a-zA-Z0-9]+', topic or '') if len(w) >= 4]
    if not words:
        return 0
    clauses = []
    args = []
    for word in words[:3]:
        clauses.append("(LOWER(topic) LIKE ? OR LOWER(question) LIKE ?)")
        needle = f"%{word.lower()}%"
        args.extend([needle, needle])
    sql = "SELECT COUNT(*) n FROM qbank WHERE " + " OR ".join(clauses)
    with _conn() as c:
        return int(c.execute(sql, args).fetchone()["n"])


def clear_qbank():
    with _conn() as c:
        c.execute("DELETE FROM qbank")


def add_watch(channel_id, title, thumbnail):
    with _conn() as c:
        c.execute("""INSERT OR REPLACE INTO watchlist
                     (channel_id, title, thumbnail, added_at)
                     VALUES (?,?,?,?)""",
                  (channel_id, title, thumbnail, _utcnow().isoformat()))


def remove_watch(channel_id):
    with _conn() as c:
        c.execute("DELETE FROM watchlist WHERE channel_id=?", (channel_id,))
        c.execute("DELETE FROM snapshots WHERE channel_id=?", (channel_id,))


def list_watch():
    with _conn() as c:
        rows = c.execute("SELECT * FROM watchlist ORDER BY title").fetchall()
        return [dict(r) for r in rows]


def add_snapshot(channel_id, subs, total_views, video_count):
    with _conn() as c:
        c.execute("""INSERT INTO snapshots
                     (channel_id, ts, subscribers, total_views, video_count)
                     VALUES (?,?,?,?,?)""",
                  (channel_id, _utcnow().isoformat(),
                   subs, total_views, video_count))


def get_snapshots(channel_id):
    with _conn() as c:
        rows = c.execute("""SELECT ts, subscribers, total_views, video_count
                            FROM snapshots WHERE channel_id=? ORDER BY ts""",
                         (channel_id,)).fetchall()
        return [dict(r) for r in rows]


def snapshot_counts():
    """How many snapshots exist per channel (for the UI)."""
    with _conn() as c:
        rows = c.execute("""SELECT channel_id, COUNT(*) n, MAX(ts) last
                            FROM snapshots GROUP BY channel_id""").fetchall()
        return {r["channel_id"]: {"n": r["n"], "last": r["last"]} for r in rows}
