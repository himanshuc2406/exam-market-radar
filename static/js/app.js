/* ---------------- YouTube Analyzer frontend ---------------- */

// API key is read on the server from .env; the frontend never handles it.
function apiKey() { return ''; }

// ---- tabs ----
document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  });
});

// ---- helpers ----
function fmt(n) {
  n = Number(n) || 0;
  if (n >= 1e7) return (n / 1e7).toFixed(2) + ' Cr';
  if (n >= 1e5) return (n / 1e5).toFixed(2) + ' L';
  if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
  return n.toLocaleString('en-IN');
}
function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
function dateShort(iso) {
  if (!iso) return '';
  try { return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: '2-digit' }); }
  catch { return iso; }
}
function loading(el, msg) {
  el.innerHTML = `<div class="loading"><div class="spinner"></div>${esc(msg || 'Working...')}</div>`;
}
function errorBox(el, msg) {
  el.innerHTML = `<div class="card"><div class="error">❌ ${esc(msg)}</div></div>`;
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return r.json();
}
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2200);
}
function downloadText(filename, text) {
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
function safeName(s) { return (s || 'file').replace(/[\\/:*?"<>|]/g, '').slice(0, 100); }

function metric(val, label, cls) {
  return `<div class="metric ${cls || ''}"><div class="metric-val">${val}</div><div class="metric-label">${esc(label)}</div></div>`;
}
function barChart(rows, maxVal) {
  const mx = maxVal || Math.max(...rows.map(r => r.value), 1);
  return `<div class="bars">${rows.map(r => `
    <div class="bar-row">
      <div class="bar-label" title="${esc(r.label)}">${esc(r.label)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, r.value / mx * 100)}%"></div></div>
      <div class="bar-val">${r.display != null ? r.display : fmt(r.value)}</div>
    </div>`).join('')}</div>`;
}

/* =================== MARKET COMMAND CENTER =================== */
let lastRadar = null;
document.getElementById('runRadar').addEventListener('click', () => runMarketRadar(false));
document.getElementById('runRadarDemo').addEventListener('click', () => runMarketRadar(true));
document.getElementById('radarScanMode').addEventListener('change', updateRadarQuotaHint);

function updateRadarQuotaHint() {
  const mode = document.getElementById('radarScanMode').value;
  const meta = {
    quick: ['Quick', 4, 408], standard: ['Standard', 8, 816], deep: ['Deep', 12, 1224],
  }[mode];
  document.getElementById('radarQuotaHint').textContent =
    `${meta[0]} scan: ${meta[1]} topics · approximately ${meta[2].toLocaleString('en-IN')} API units · repeat scan cached for 30 minutes`;
}

async function runMarketRadar(demo = false) {
  const el = document.getElementById('radarResult');
  const body = {
    exam: document.getElementById('radarExam').value,
    subject: document.getElementById('radarSubject').value,
    days: Number(document.getElementById('radarDays').value),
    scan_mode: document.getElementById('radarScanMode').value,
    exam_days: document.getElementById('radarExamDays').value,
    own_channel: document.getElementById('radarChannel').value.trim(),
    custom_topics: document.getElementById('radarTopics').value.trim(),
    demo,
  };
  loading(el, demo ? 'Loading the offline pitch walkthrough...' : 'Scanning recent videos, student doubts and test demand... this can take about a minute.');
  document.getElementById('runRadar').disabled = true;
  document.getElementById('runRadarDemo').disabled = true;
  try {
    const res = await postJSON('/api/market-radar', body);
    if (!res.ok) return errorBox(el, res.error);
    lastRadar = res.data;
    renderMarketRadar(res.data);
  } catch (err) {
    errorBox(el, err.message || 'Market scan failed');
  } finally {
    document.getElementById('runRadar').disabled = false;
    document.getElementById('runRadarDemo').disabled = false;
  }
}

function heatClass(score) {
  if (score >= 70) return 'hot';
  if (score >= 45) return 'warm';
  return 'cool';
}

function renderMarketRadar(data) {
  const el = document.getElementById('radarResult');
  const s = data.summary;
  const rows = data.opportunities || [];
  const comments = rows.reduce((n, r) => n + (r.comments_sampled || 0), 0);
  const top = rows[0];
  let html = `
    ${data.demo ? '<div class="demo-banner"><b>PITCH DEMO</b> Sample data for a reliable offline walkthrough. Use “Scan market” for live evidence.</div>' : ''}
    ${data.cache_hit ? `<div class="cache-banner"><b>CACHE HIT</b> Same scan reused from ${data.cached_age_seconds || 0}s ago · no extra YouTube quota used.</div>` : ''}
    <div class="command-hero">
      <div class="command-copy">
        <span class="eyebrow">#1 RECOMMENDED ACTION · ${esc(top.subject)}</span>
        <h2>${esc(s.headline)}</h2>
        <p>${esc(s.why)}</p>
        <div class="command-actions">
          <button class="btn radar-factory" data-radar-index="0">${data.demo ? 'Preview Test Factory' : 'Build test from top source video'}</button>
          <button class="btn-ghost" id="exportRadar">Export decision brief</button>
        </div>
      </div>
      <div class="score-dial ${heatClass(top.opportunity_score)}">
        <strong>${top.opportunity_score}</strong><span>Opportunity</span>
      </div>
    </div>
    <div class="metrics radar-metrics">
      ${metric(rows.length, 'Topics scanned', 'blue')}
      ${metric(fmt(comments), 'Signal comments', 'green')}
      ${metric(top.market_heat + '/100', 'Top market heat', 'accent')}
      ${metric(fmt(data.quota_estimate), 'API units this run', 'yellow')}
    </div>
    <div class="decision-strip">
      <span><b>Exam:</b> ${esc(s.exam)}</span>
      <span><b>Window:</b> ${s.window_days} days</span>
      <span><b>Depth:</b> ${esc(data.scan_mode || 'standard')} · ${rows.length}/${data.topic_limit || rows.length} topics</span>
      <span><b>Own coverage:</b> ${s.own_channel ? esc(s.own_channel) : 'Not connected'}</span>
      <span class="signal-note">Directional signal · not search-volume data</span>
    </div>
    <div class="scan-scope"><b>Scanned syllabus basket:</b>${(data.topics || []).map(t => `<span>${esc(t)}</span>`).join('')}</div>
    <div class="section-title">Ranked build queue</div>`;

  html += `<div class="opportunity-grid">${rows.map((r, i) => opportunityCard(r, i, data.demo)).join('')}</div>`;
  if (data.own_channel_error) {
    html += `<div class="card"><div class="empty">Own-channel coverage could not be loaded: ${esc(data.own_channel_error)}</div></div>`;
  }
  if (data.errors && data.errors.length) {
    html += `<div class="card"><div class="empty">Partial scan: ${esc(data.errors.join(' | '))}</div></div>`;
  }
  el.innerHTML = html;
  el.querySelectorAll('.radar-factory').forEach(btn => btn.addEventListener('click', () => {
    sendRadarToFactory(rows[Number(btn.dataset.radarIndex)]);
  }));
  document.getElementById('exportRadar').addEventListener('click', exportRadarBrief);
}

function opportunityCard(r, index, demo) {
  const rec = r.recommendation;
  const cov = r.own_coverage || {};
  const coverageLabel = cov.known ? `${cov.count} recent matching video${cov.count === 1 ? '' : 's'}` : 'channel not connected';
  const topVideo = (r.top_videos || [])[0];
  const evidence = [...(r.doubt_examples || []), ...(r.request_examples || [])].slice(0, 2);
  return `<article class="opportunity-card ${index === 0 ? 'top' : ''}">
    <div class="opp-head">
      <div class="opp-rank">#${r.rank}</div>
      <div class="opp-title"><span>${esc(r.subject)}</span><h3>${esc(r.topic)}</h3></div>
      <div class="heat-pill ${heatClass(r.market_heat)}">Heat ${r.market_heat}</div>
    </div>
    <div class="opp-scores">
      <div><span>Opportunity</span><b>${r.opportunity_score}</b></div>
      <div><span>Views/day</span><b>${fmt(r.avg_views_per_day)}</b></div>
      <div><span>Doubts</span><b>${r.doubt_count}</b></div>
      <div><span>Test asks</span><b>${r.request_count}</b></div>
    </div>
    <div class="opp-recommendation">
      <span>BUILD NEXT</span>
      <h4>${esc(rec.product)}</h4>
      <p>${esc(rec.reason)}</p>
    </div>
    <div class="blueprint-row">
      <span><b>${rec.questions}</b> questions</span>
      <span><b>${rec.duration_minutes}</b> minutes</span>
      <span><b>30/50/20</b> E/M/H</span>
      <span><b>${r.inventory}</b> in bank</span>
    </div>
    <div class="evidence-line"><b>Coverage:</b> ${esc(coverageLabel)} · <b>Market:</b> ${r.channel_count} channels / ${r.video_count} videos</div>
    ${topVideo ? (topVideo.url
      ? `<a class="market-video" href="${esc(topVideo.url)}" target="_blank">↗ Evidence: ${esc(topVideo.title)} · ${fmt(topVideo.views_per_day)} views/day</a>`
      : `<div class="market-video">Evidence: ${esc(topVideo.title)} · ${fmt(topVideo.views_per_day)} views/day</div>`) : ''}
    ${evidence.length ? `<details class="market-evidence"><summary>Real student signal examples</summary>${evidence.map(x => `<p>“${esc(x)}”</p>`).join('')}</details>` : ''}
    <details class="score-explain"><summary>Why these scores?</summary>
      <div>${Object.entries(r.score_components || {}).map(([k, v]) => `<span>${esc(k)} <b>${v}</b></span>`).join('')}</div>
      <p>Market Heat combines velocity, genuine doubts, explicit test requests, outliers and engagement. Opportunity also considers your coverage gap and market saturation.</p>
    </details>
    <div class="opp-actions">
      <button class="btn radar-factory" data-radar-index="${index}">${demo ? 'Preview factory' : 'Use source video'}</button>
      <span>${esc(rec.review_gate)}</span>
    </div>
  </article>`;
}

function sendRadarToFactory(row) {
  if (!row) return;
  const nav = document.querySelector('.nav-btn[data-tab="qbank"]');
  nav.click();
  const source = (row.top_videos || []).find(v => v.url) || null;
  const note = document.getElementById('factorySourceNote');
  document.getElementById('qbCount').value = row.recommendation.questions;
  document.getElementById('qbMaxVideos').value = 1;
  document.getElementById('qbDiff').value = 'mixed';
  document.getElementById('qbExam').value = document.getElementById('radarExam').value;
  note.style.display = 'block';
  if (source) {
    document.getElementById('qbInput').value = source.url;
    note.innerHTML = `<b>Market source selected:</b> ${esc(source.title)}<br>` +
      `<span>${esc(row.topic)} · ${esc(row.recommendation.product)} · ${row.recommendation.questions} questions · faculty-review draft</span>`;
    toast('Source video selected · fetching transcript and building the test draft');
    runQbank();
  } else {
    document.getElementById('qbInput').value = '';
    note.innerHTML = `<b>Pitch-demo blueprint:</b> ${esc(row.topic)} → ${esc(row.recommendation.product)}<br>` +
      `<span>A live scan inserts the top evidence video URL here automatically. Demo mode does not invent a source URL.</span>`;
    document.getElementById('qbInput').focus();
    toast('Factory preview ready · live scan will insert the source video URL');
  }
}

function exportRadarBrief() {
  if (!lastRadar) return;
  const s = lastRadar.summary;
  const lines = [
    'EXAM MARKET RADAR — DAILY DECISION BRIEF',
    `Generated: ${new Date(lastRadar.scanned_at).toLocaleString('en-IN')}`,
    `Exam: ${s.exam} | Window: ${s.window_days} days`,
    '', `TOP ACTION: ${s.headline}`, s.why, '', 'RANKED BUILD QUEUE',
  ];
  lastRadar.opportunities.forEach(r => {
    const b = r.recommendation;
    lines.push(`${r.rank}. ${r.topic} — Opportunity ${r.opportunity_score}, Heat ${r.market_heat}`);
    lines.push(`   Build: ${b.product} | ${b.questions} questions | ${b.duration_minutes} minutes | 30/50/20 easy/medium/hard`);
    lines.push(`   Evidence: ${r.avg_views_per_day} avg views/day, ${r.doubt_count} doubts, ${r.request_count} test requests, ${r.inventory} questions in bank`);
    lines.push(`   Why: ${b.reason}`, '');
  });
  lines.push(s.disclaimer, 'All drafts require faculty review before publishing.');
  downloadText(`market_radar_${safeName(s.exam)}.txt`, lines.join('\n'));
}

/* =================== VIDEO ANALYZER =================== */
document.getElementById('analyzeVideo').addEventListener('click', analyzeVideo);
document.getElementById('videoUrl').addEventListener('keydown', e => { if (e.key === 'Enter') analyzeVideo(); });

async function analyzeVideo() {
  const url = document.getElementById('videoUrl').value.trim();
  const el = document.getElementById('videoResult');
  if (!url) return toast('Paste a video URL first');
  loading(el, 'Fetching video, transcript & comments...');

  const res = await postJSON('/api/video', { url, api_key: apiKey() });
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data;
  let html = '';

  // stats
  if (d.details) {
    const v = d.details;
    html += `<div class="card"><div class="video-head">
      <img src="${esc(v.thumbnail)}" alt="">
      <div>
        <div class="vh-title">${esc(v.title)}</div>
        <div class="vh-meta">${esc(v.channel_title)} · ${dateShort(v.published_at)} · ${esc(v.duration)}</div>
      </div></div></div>`;
    html += `<div class="metrics">
      ${metric(fmt(v.views), 'Views', 'blue')}
      ${metric(fmt(v.likes), 'Likes', 'green')}
      ${metric(fmt(v.comments), 'Comments', 'accent')}
      ${metric(v.engagement + '%', 'Engagement', 'yellow')}
    </div>`;
  } else if (d.details_error) {
    html += `<div class="card"><div class="error">Stats: ${esc(d.details_error)}</div></div>`;
  } else if (d.no_key) {
    html += `<div class="card"><div class="empty">API key not found in .env — showing transcript only. Add YOUTUBE_API_KEY to the .env file for views, likes and comment analysis.</div></div>`;
  }

  // SEO audit
  if (d.seo) {
    const s = d.seo;
    html += `<div class="card"><h2>SEO Audit <span class="count">score ${s.score}/100</span></h2>
      <div class="seo-score"><div class="seo-bar"><div class="seo-fill" style="width:${s.score}%"></div></div><span class="seo-num">${s.score}</span></div>
      <div class="seo-checks">${s.checks.map(ch =>
        `<div class="seo-check"><span class="seo-dot ${ch.ok ? 'ok' : 'bad'}"></span>${esc(ch.label)}</div>`).join('')}</div>
      ${s.tags && s.tags.length
        ? `<div class="mini-label">Tags (${s.tags.length})</div><div class="chips">${s.tags.map(t => `<span class="chip">${esc(t)}</span>`).join('')}</div>`
        : `<div class="mini-label">No tags on this video — a quick SEO win</div>`}
    </div>`;
  }

  // sentiment
  if (d.sentiment) {
    const s = d.sentiment;
    html += `<div class="metrics">
      ${metric(s.positive, 'Positive', 'green')}
      ${metric(s.neutral, 'Neutral')}
      ${metric(s.negative, 'Negative', 'accent')}
      ${metric(d.comment_count_fetched, 'Comments scanned', 'blue')}
    </div>`;
  }

  // doubts
  if (d.doubts && d.doubts.length) {
    html += `<div class="card"><h2>Student Doubts <span class="count">${d.doubts.length} found</span></h2>
      <div class="list">${d.doubts.map(c => `
        <div class="list-item">
          ${(c.timestamps || []).map(t => `<span class="badge ts">${esc(t)}</span>`).join('')}
          ${esc(c.text)}
          <div class="li-meta"><span>${esc(c.author)}</span><span class="badge like">${c.likes} likes</span></div>
        </div>`).join('')}</div></div>`;
  }

  // content requests
  if (d.requests && d.requests.length) {
    html += `<div class="card"><h2>Content Requests <span class="count">what viewers are asking for</span></h2>
      <div class="list">${d.requests.map(c => `
        <div class="list-item">${esc(c.text)}
          <div class="li-meta"><span>${esc(c.author)}</span><span class="badge like">${c.likes} likes</span></div>
        </div>`).join('')}</div></div>`;
  }

  // top comments
  if (d.top_comments && d.top_comments.length) {
    html += `<div class="card"><h2>Top Comments</h2>
      <div class="list">${d.top_comments.map(c => `
        <div class="list-item">${esc(c.text)}
          <div class="li-meta"><span>${esc(c.author)}</span><span class="badge like">${c.likes} likes</span></div>
        </div>`).join('')}</div></div>`;
  }

  // transcript + keywords
  if (d.transcript) {
    const t = d.transcript;
    html += `<div class="card"><h2>Top Keywords <span class="count">from transcript</span></h2>
      <div class="chips">${t.word_freq.map(w => `<span class="chip">${esc(w[0])}<b>${w[1]}</b></span>`).join('')}</div></div>`;
    html += `<div class="card"><h2>Transcript <span class="count">${t.language} · ${fmt(t.char_count)} chars</span></h2>
      <div class="transcript-box" id="vTranscript">${esc(t.text)}</div>
      <div class="row-actions">
        <button class="btn-ghost" onclick="copyEl('vTranscript')">Copy</button>
        <button class="btn-ghost" onclick="downloadText('${safeName(d.details ? d.details.title : d.video_id)}.txt', document.getElementById('vTranscript').innerText)">Download .txt</button>
      </div></div>`;
  } else if (d.transcript_error) {
    html += `<div class="card"><div class="empty">📝 Transcript: ${esc(d.transcript_error)}</div></div>`;
  }

  el.innerHTML = html || `<div class="card"><div class="empty">No data.</div></div>`;
}

/* =================== CHANNEL TRACKER =================== */
document.getElementById('analyzeChannel').addEventListener('click', analyzeChannel);
document.getElementById('channelQuery').addEventListener('keydown', e => { if (e.key === 'Enter') analyzeChannel(); });

let channelVideos = [], channelSort = { key: 'views', dir: -1 };

async function analyzeChannel() {
  const q = document.getElementById('channelQuery').value.trim();
  const max_n = document.getElementById('channelCount').value;
  const el = document.getElementById('channelResult');
  if (!q) return toast('Enter a channel');
  loading(el, 'Fetching channel & videos...');

  const res = await postJSON('/api/channel', { channel: q, max_n, api_key: apiKey() });
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data, c = d.channel, s = d.summary;
  channelVideos = d.videos;

  let html = `<div class="card"><div class="video-head">
    <img src="${esc(c.thumbnail)}" alt="">
    <div>
      <div class="vh-title">${esc(c.title)}</div>
      <div class="vh-meta">${fmt(c.subscribers)} subscribers · ${fmt(c.video_count)} videos · ${fmt(c.total_views)} total views</div>
    </div></div></div>`;

  html += `<div class="metrics">
    ${metric(fmt(s.avg_views), 'Avg views / video', 'blue')}
    ${metric(s.avg_engagement + '%', 'Avg engagement', 'yellow')}
    ${metric(fmt(s.best.views), 'Best video views', 'green')}
    ${metric(s.count, 'Videos analyzed', 'accent')}
  </div>`;

  // best / most engaging
  html += `<div class="metrics">
    <div class="metric green"><div class="metric-label">Best performer</div><div style="font-size:14px;margin-top:6px">${esc(s.best.title)}</div><div class="metric-label" style="margin-top:6px">${fmt(s.best.views)} views</div></div>
    <div class="metric blue"><div class="metric-label">Most engaging</div><div style="font-size:14px;margin-top:6px">${esc(s.most_engaging.title)}</div><div class="metric-label" style="margin-top:6px">${s.most_engaging.engagement}% engagement</div></div>
  </div>`;

  // top 10 by views bar chart
  const top = [...channelVideos].sort((a, b) => b.views - a.views).slice(0, 10);
  html += `<div class="card"><h2>Top videos by views</h2>${barChart(top.map(v => ({ label: v.title, value: v.views })))}</div>`;

  // deep-dive analytics
  if (d.deepdive) html += deepDiveHTML(d.deepdive);

  // table
  html += `<div class="card"><h2>All videos <span class="count">click a column to sort</span></h2>
    <div class="tbl-wrap"><table id="chanTable"></table></div></div>`;

  el.innerHTML = html;
  renderChannelTable();
}

function renderChannelTable() {
  const t = document.getElementById('chanTable');
  if (!t) return;
  const cols = [
    { k: 'title', label: 'Title', num: false },
    { k: 'published_at', label: 'Date', num: false },
    { k: 'views', label: 'Views', num: true },
    { k: 'likes', label: 'Likes', num: true },
    { k: 'comments', label: 'Comments', num: true },
    { k: 'engagement', label: 'Eng %', num: true },
  ];
  const rows = [...channelVideos].sort((a, b) => {
    const av = a[channelSort.key], bv = b[channelSort.key];
    if (av < bv) return -channelSort.dir;
    if (av > bv) return channelSort.dir;
    return 0;
  });
  t.innerHTML = `<thead><tr>${cols.map(c =>
    `<th data-k="${c.k}" class="${c.num ? 'num' : ''}">${c.label}${channelSort.key === c.k ? (channelSort.dir < 0 ? ' ↓' : ' ↑') : ''}</th>`).join('')}</tr></thead>
    <tbody>${rows.map(v => `<tr>
      <td><a href="${esc(v.url)}" target="_blank">${esc(v.title)}</a></td>
      <td>${dateShort(v.published_at)}</td>
      <td class="num">${fmt(v.views)}</td>
      <td class="num">${fmt(v.likes)}</td>
      <td class="num">${fmt(v.comments)}</td>
      <td class="num">${v.engagement}%</td>
    </tr>`).join('')}</tbody>`;
  t.querySelectorAll('th').forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.k;
    if (channelSort.key === k) channelSort.dir *= -1;
    else channelSort = { key: k, dir: -1 };
    renderChannelTable();
  }));
}

/* =================== TOPIC RESEARCH =================== */
document.getElementById('runResearch').addEventListener('click', runResearch);
document.getElementById('researchQuery').addEventListener('keydown', e => { if (e.key === 'Enter') runResearch(); });

async function runResearch() {
  const query = document.getElementById('researchQuery').value.trim();
  const order = document.getElementById('researchOrder').value;
  const el = document.getElementById('researchResult');
  if (!query) return toast('Enter a topic');
  loading(el, 'Searching YouTube...');

  const res = await postJSON('/api/search', { query, order, max_n: 30, api_key: apiKey() });
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data, vids = d.videos;

  const totalViews = vids.reduce((a, v) => a + v.views, 0);
  const avgViews = vids.length ? Math.round(totalViews / vids.length) : 0;

  let html = `<div class="metrics">
    ${metric(vids.length, 'Videos found', 'accent')}
    ${metric(fmt(avgViews), 'Avg views', 'blue')}
    ${metric(fmt(Math.max(...vids.map(v => v.views), 0)), 'Top video views', 'green')}
    ${metric(d.top_channels.length, 'Channels competing', 'yellow')}
  </div>`;

  // dominant channels
  html += `<div class="card"><h2>Channels dominating this topic</h2>
    ${barChart(d.top_channels.map(c => ({ label: c[0], value: c[1], display: c[1] + ' vids' })))}</div>`;

  // results table
  html += `<div class="card"><h2>Search results <span class="count">sorted by ${esc(order)}</span></h2>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Title</th><th>Channel</th><th class="num">Views</th><th class="num">Eng %</th><th>Date</th></tr></thead>
      <tbody>${vids.map(v => `<tr>
        <td><a href="${esc(v.url)}" target="_blank">${esc(v.title)}</a></td>
        <td>${esc(v.channel_title)}</td>
        <td class="num">${fmt(v.views)}</td>
        <td class="num">${v.engagement}%</td>
        <td>${dateShort(v.published_at)}</td>
      </tr>`).join('')}</tbody></table></div></div>`;

  el.innerHTML = html;
}

/* =================== DOUBT RADAR =================== */
document.getElementById('runDoubts').addEventListener('click', runDoubts);
document.getElementById('doubtQuery').addEventListener('keydown', e => { if (e.key === 'Enter') runDoubts(); });

let lastDoubts = null;

async function runDoubts() {
  const query = document.getElementById('doubtQuery').value.trim();
  const max_videos = parseInt(document.getElementById('doubtVideos').value, 10) || 12;
  const el = document.getElementById('doubtResult');
  if (!query) return toast('Enter a topic');
  loading(el, 'Scanning student comments across videos… clustering doubts (can take a bit)');

  const res = await postJSON('/api/doubts', { query, max_videos, api_key: apiKey() });
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data;
  lastDoubts = d;
  const clusters = d.clusters || [];
  if (!clusters.length) return el.innerHTML = `<div class="card"><div class="empty">No clear doubt clusters found. Try a broader topic.</div></div>`;

  const pill = p => `<span class="pri pri-${esc(p)}">${esc(p)}</span>`;
  const totalLikes = clusters.reduce((a, c) => a + (c.total_likes || 0), 0);

  let html = `<div class="metrics">
    ${metric(clusters.length, 'Doubt clusters', 'accent')}
    ${metric(d.doubts_found, 'Doubt comments', 'blue')}
    ${metric(d.videos_scanned, 'Videos scanned', 'green')}
    ${metric(fmt(totalLikes), 'Student upvotes', 'yellow')}
  </div>`;

  html += `<div class="card"><h2>Content brief <span class="count">ranked by student demand</span>
    <button class="btn-ghost" onclick="downloadDoubtCSV()" style="float:right">Export brief CSV</button></h2>`;

  html += clusters.map((c, i) => `
    <div class="doubt-cluster">
      <div class="dc-head">
        <span class="dc-rank">#${i + 1}</span>
        <span class="dc-concept">${esc(c.concept)}</span>
        ${pill(c.priority)}
      </div>
      <div class="dc-stats">${c.count} doubt${c.count > 1 ? 's' : ''} · ${fmt(c.total_likes)} upvotes · ${c.video_count} video${c.video_count > 1 ? 's' : ''}${(c.timestamps && c.timestamps.length) ? ' · students stall at ' + c.timestamps.slice(0, 4).map(esc).join(', ') : ''}</div>
      <div class="dc-summary">${esc(c.summary)}</div>
      <div class="dc-idea">🎯 <b>Make:</b> ${esc(c.content_idea)}</div>
      ${(c.examples && c.examples.length) ? `<details class="dc-examples"><summary>${c.examples.length} example comment${c.examples.length > 1 ? 's' : ''}</summary>
        ${c.examples.map(e => `<div class="list-item">${esc(e.text)}<span class="li-meta">${fmt(e.likes)} 👍 · ${esc(e.video_title)}</span></div>`).join('')}
      </details>` : ''}
    </div>`).join('');

  html += `</div>`;
  el.innerHTML = html;
}

function downloadDoubtCSV() {
  if (!lastDoubts || !lastDoubts.clusters || !lastDoubts.clusters.length) return;
  const q = s => `"${String(s == null ? '' : s).replace(/"/g, '""')}"`;
  const header = ['Rank', 'Concept', 'Priority', 'Doubts', 'Upvotes', 'Videos', 'Summary', 'Content idea', 'Timestamps'];
  const rows = lastDoubts.clusters.map((c, i) =>
    [i + 1, c.concept, c.priority, c.count, c.total_likes, c.video_count,
     c.summary, c.content_idea, (c.timestamps || []).join(' ')].map(q).join(','));
  const csv = '﻿' + header.map(q).join(',') + '\n' + rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = safeName('doubt-brief-' + (lastDoubts.topic || 'topic')) + '.csv';
  a.click();
  URL.revokeObjectURL(a.href);
  toast('Brief exported');
}

/* =================== TRANSCRIPT TOOLS =================== */
document.getElementById('getTranscript').addEventListener('click', getTranscript);
document.getElementById('transcriptUrl').addEventListener('keydown', e => { if (e.key === 'Enter') getTranscript(); });

async function getTranscript() {
  const url = document.getElementById('transcriptUrl').value.trim();
  const el = document.getElementById('transcriptResult');
  if (!url) return toast('Paste a video URL');
  loading(el, 'Extracting transcript...');

  const res = await postJSON('/api/transcript', { url });
  if (!res.ok) return errorBox(el, res.error);
  const t = res.data;

  el.innerHTML = `<div class="card">
    <h2>Transcript <span class="count">${esc(t.language)} (${esc(t.language_code)}) · ${t.is_generated ? 'auto-generated' : 'manual'} · ${fmt(t.char_count)} chars</span></h2>
    <div class="transcript-box" id="tOut">${esc(t.text)}</div>
    <div class="row-actions">
      <button class="btn-ghost" onclick="copyEl('tOut')">Copy</button>
      <button class="btn-ghost" onclick="downloadText('transcript_${esc(t.video_id)}.txt', document.getElementById('tOut').innerText)">Download .txt</button>
    </div></div>`;
}

/* =================== CONTENT GENERATOR =================== */
let genMode = 'topic';
let genStyle = 'fresh';
let lastQuiz = null;
let lastQuizContext = null;

document.querySelectorAll('#genStyle .seg-btn').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('#genStyle .seg-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    genStyle = b.dataset.style;
  });
});

document.querySelectorAll('#genMode .seg-btn').forEach(b => {
  b.addEventListener('click', () => {
    document.querySelectorAll('#genMode .seg-btn').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    genMode = b.dataset.mode;
    const input = document.getElementById('genInput');
    const ta = document.getElementById('genTextarea');
    if (genMode === 'text') {
      input.style.display = 'none'; ta.style.display = 'block';
    } else {
      input.style.display = 'block'; ta.style.display = 'none';
      input.placeholder = genMode === 'url'
        ? 'https://www.youtube.com/watch?v=...'
        : 'e.g. Simple Interest & Compound Interest for SBI Clerk';
    }
  });
});

document.getElementById('runGenerate').addEventListener('click', runGenerate);

async function runGenerate() {
  const el = document.getElementById('generateResult');
  const input = (genMode === 'text'
    ? document.getElementById('genTextarea').value
    : document.getElementById('genInput').value).trim();
  if (!input) return toast('Enter a topic / URL / text first');

  const body = {
    mode: genMode,
    input,
    style: genStyle,
    count: document.getElementById('genCount').value,
    difficulty: document.getElementById('genDiff').value,
    language: document.getElementById('genLang').value,
    exam: document.getElementById('genExam').value.trim(),
    notes: true,
  };
  loading(el, genMode === 'url'
    ? 'Fetching transcript & generating questions... (may take 15-30s)'
    : 'Generating questions with AI... (may take 10-20s)');

  const res = await postJSON('/api/generate', body);
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data;
  lastQuiz = d;
  lastQuizContext = body;

  let html = `<div class="metrics">
    ${metric(d.count, 'Questions generated', 'accent')}
    ${d.source_count ? metric(d.source_count, 'Detected in video', 'green') : metric(esc(body.difficulty), 'Difficulty', 'yellow')}
    ${d.source_count ? metric(Math.max(0, d.count - d.source_count), 'Extra (same pattern)', 'blue') : metric(esc(body.language), 'Language', 'blue')}
  </div>`;

  // capture summary for mirror mode
  if (d.source_count) {
    const extra = Math.max(0, d.count - d.source_count);
    const msg = extra > 0
      ? `Captured all <b>${d.source_count}</b> questions from the video, plus <b>${extra}</b> extra in the same pattern.`
      : `Mirrored <b>${d.count}</b> of the <b>${d.source_count}</b> questions found in the video.`;
    html += `<div class="card" style="padding:14px 18px"><div class="gap-why" style="margin:0">${msg}</div></div>`;
  }

  if (d.notes) {
    html += `<div class="card"><h2>Key Notes</h2><div style="font-size:14px;line-height:1.7">${esc(d.notes)}</div></div>`;
  }

  html += `<div class="card">
    <h2>Generated MCQs <span class="count">${d.source ? esc(d.source) : ''}</span></h2>
    <div class="row-actions" style="margin-bottom:14px;margin-top:0">
      <button class="btn-ghost" onclick="downloadQuizCSV()">Download CSV</button>
      <button class="btn-ghost" onclick="downloadQuizTxt()">Download TXT</button>
      <button class="btn-ghost" onclick="saveQuizDraft()">Save as draft in Question Bank</button>
    </div>
    ${d.questions.map((q, i) => `
      <div class="quiz-q">
        <div class="q-text"><span class="q-num">Q${i + 1}.</span>${esc(q.question)}</div>
        ${q.options.map((o, oi) => `<div class="quiz-opt ${oi === q.answer_index ? 'correct' : ''}">${String.fromCharCode(65 + oi)}) ${esc(o)}${oi === q.answer_index ? '<span class="opt-tag">Correct</span>' : ''}</div>`).join('')}
        ${q.explanation ? `<div class="quiz-exp"><b>Explanation:</b> ${esc(q.explanation)}</div>` : ''}
        <div class="quiz-tags">${q.topic ? `<span class="badge">${esc(q.topic)}</span>` : ''}${q.difficulty ? `<span class="badge ts">${esc(q.difficulty)}</span>` : ''}</div>
      </div>`).join('')}
  </div>`;

  el.innerHTML = html;
}

async function saveQuizDraft() {
  if (!lastQuiz || !lastQuiz.questions || !lastQuiz.questions.length) return toast('Generate a quiz first');
  const res = await postJSON('/api/qbank/save-generated', {
    questions: lastQuiz.questions,
    exam: (lastQuizContext && lastQuizContext.exam) || '',
    source_topic: (lastQuizContext && lastQuizContext.input) || lastQuiz.source || 'Market Radar draft',
  });
  if (!res.ok) return toast(res.error || 'Could not save draft');
  toast(`${res.data.added} saved as faculty-review drafts · ${res.data.skipped} duplicates skipped`);
}

function downloadQuizCSV() {
  if (!lastQuiz) return;
  const esc = s => `"${String(s == null ? '' : s).replace(/"/g, '""')}"`;
  const header = ['No', 'Question', 'Option A', 'Option B', 'Option C', 'Option D', 'Answer', 'Explanation', 'Topic', 'Difficulty'];
  const rows = lastQuiz.questions.map((q, i) => {
    const o = q.options;
    const ans = String.fromCharCode(65 + q.answer_index);
    return [i + 1, q.question, o[0] || '', o[1] || '', o[2] || '', o[3] || '', ans, q.explanation, q.topic, q.difficulty].map(esc).join(',');
  });
  const csv = '﻿' + header.map(esc).join(',') + '\n' + rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'quiz.csv';
  a.click();
  URL.revokeObjectURL(a.href);
  toast('CSV downloaded');
}

function downloadQuizTxt() {
  if (!lastQuiz) return;
  let out = '';
  lastQuiz.questions.forEach((q, i) => {
    out += `Q${i + 1}. ${q.question}\n`;
    q.options.forEach((o, oi) => { out += `   ${String.fromCharCode(65 + oi)}) ${o}\n`; });
    out += `   Answer: ${String.fromCharCode(65 + q.answer_index)}\n`;
    if (q.explanation) out += `   Explanation: ${q.explanation}\n`;
    out += '\n';
  });
  downloadText('quiz.txt', out);
}

/* =================== DEEP-DIVE (inside Channel Tracker) =================== */
function deepDiveHTML(dd) {
  let h = `<div class="section-title">Deep-Dive Analytics</div>`;
  const cadence = dd.per_week != null
    ? (dd.per_week >= 1 ? `${dd.per_week}/week` : `every ${dd.cadence_days}d`)
    : '—';
  h += `<div class="metrics">
    ${metric(fmt(dd.median_views), 'Median views', 'blue')}
    ${metric(dd.best_day ? dd.best_day.day : '—', 'Best day to post', 'green')}
    ${metric(cadence, 'Upload cadence', 'yellow')}
    ${metric(dd.best_length ? dd.best_length.label : '—', 'Best length', 'accent')}
  </div>`;

  const days = (dd.dow || []).filter(x => x.count > 0);
  if (days.length) {
    h += `<div class="card"><h2>Average views by day of week</h2>
      ${barChart(days.map(x => ({ label: `${x.day} (${x.count})`, value: x.avg_views })))}</div>`;
  }
  if (dd.length && dd.length.length) {
    h += `<div class="card"><h2>Video length vs average views</h2>
      ${barChart(dd.length.map(x => ({ label: `${x.label} (${x.count})`, value: x.avg_views })))}</div>`;
  }
  if (dd.title_keywords && dd.title_keywords.length) {
    h += `<div class="card"><h2>Title keywords that perform <span class="count">avg views · lift vs channel avg</span></h2>
      ${barChart(dd.title_keywords.map(k => ({
        label: `${k.word} (${k.count})`, value: k.avg_views,
        display: `${fmt(k.avg_views)} · ${k.lift >= 0 ? '+' : ''}${k.lift}%`
      })))}</div>`;
  }
  if (dd.outliers && dd.outliers.length) {
    h += `<div class="card"><h2>Overperformers <span class="count">above 1.5× median</span></h2>
      <div class="list">${dd.outliers.map(o => `
        <div class="list-item"><a href="${esc(o.url)}" target="_blank" style="color:inherit;text-decoration:none">${esc(o.title)}</a>
          <div class="li-meta"><span class="badge like">${fmt(o.views)} views</span><span class="badge ts">${o.ratio}× median</span></div>
        </div>`).join('')}</div></div>`;
  }
  return h;
}

/* =================== MULTI-CHANNEL COMPARE =================== */
document.getElementById('runCompare').addEventListener('click', runCompare);

async function runCompare() {
  const raw = document.getElementById('compareInput').value.trim();
  const el = document.getElementById('compareResult');
  const channels = raw.split('\n').map(s => s.trim()).filter(Boolean);
  if (channels.length < 2) return toast('Enter at least 2 channels (one per line)');
  loading(el, `Loading ${channels.length} channels...`);

  const res = await postJSON('/api/compare', { channels, max_n: document.getElementById('compareCount').value });
  if (!res.ok) return errorBox(el, res.error);
  const rows = res.data.rows;

  const defs = [
    { k: 'subscribers', label: 'Subscribers', fmt: fmt, better: 'max' },
    { k: 'avg_views', label: 'Avg views / video', fmt: fmt, better: 'max' },
    { k: 'avg_engagement', label: 'Avg engagement', fmt: v => v + '%', better: 'max' },
    { k: 'total_views', label: 'Total views', fmt: fmt, better: 'max' },
    { k: 'video_count', label: 'Total videos', fmt: fmt, better: 'max' },
    { k: 'per_week', label: 'Uploads / week', fmt: v => v == null ? '—' : v, better: 'max' },
    { k: 'best_day', label: 'Best day', fmt: v => v || '—', better: 'none' },
  ];
  const best = {};
  defs.forEach(m => {
    if (m.better === 'max') {
      const nums = rows.map(r => typeof r[m.k] === 'number' ? r[m.k] : -Infinity);
      best[m.k] = Math.max(...nums);
    }
  });

  let html = `<div class="card"><h2>Comparison <span class="count">${rows.length} channels</span></h2>
    <div class="tbl-wrap"><table class="compare-tbl">
      <thead><tr><th>Metric</th>${rows.map(r => `<th>${esc(r.title)}</th>`).join('')}</tr></thead>
      <tbody>${defs.map(m => `<tr>
        <td class="metric-name">${m.label}</td>
        ${rows.map(r => {
          const val = r[m.k];
          const isBest = best[m.k] != null && typeof val === 'number' && val === best[m.k] && best[m.k] !== -Infinity;
          return `<td class="num ${isBest ? 'best' : ''}">${m.fmt(val)}</td>`;
        }).join('')}
      </tr>`).join('')}</tbody></table></div></div>`;

  html += `<div class="card"><h2>Subscribers</h2>${barChart(rows.map(r => ({ label: r.title, value: r.subscribers })))}</div>`;
  html += `<div class="card"><h2>Average views per video</h2>${barChart(rows.map(r => ({ label: r.title, value: r.avg_views })))}</div>`;

  // ---- what's working per channel ----
  html += `<div class="section-title">What's working for each channel</div>`;
  rows.forEach(r => {
    const mom = r.momentum == null ? '' :
      `<span class="badge ${r.momentum >= 0 ? 'like' : ''}">${r.momentum >= 0 ? '▲ heating up' : '▼ cooling'} ${r.momentum >= 0 ? '+' : ''}${r.momentum}%</span>`;
    let c = `<div class="card"><h2>${esc(r.title)} ${mom}</h2>`;

    // format line
    const fmtBits = [];
    if (r.best_length) fmtBits.push(`Best length: <b>${esc(r.best_length)}</b>`);
    if (r.best_day) fmtBits.push(`Best day: <b>${esc(r.best_day)}</b>`);
    if (r.per_week != null) fmtBits.push(`~<b>${r.per_week}</b> uploads/week`);
    if (fmtBits.length) c += `<div class="fmt-line">${fmtBits.join('&nbsp;&nbsp;·&nbsp;&nbsp;')}</div>`;

    // winning videos
    if (r.winning && r.winning.length) {
      c += `<div class="mini-label">Top-performing content</div>
        <div class="list">${r.winning.map(w => `
          <div class="list-item win-item">
            <div class="win-title"><a href="${esc(w.url)}" target="_blank">${esc(w.title)}</a></div>
            <div class="li-meta">
              <span class="badge like">${fmt(w.views)} views</span>
              <span class="badge ts">${w.ratio}× their avg</span>
              <button class="btn-mini" onclick="useForQuiz('${esc(w.url)}')">Make my quiz</button>
            </div>
          </div>`).join('')}</div>`;
    }

    // winning title keywords
    if (r.keywords && r.keywords.length) {
      c += `<div class="mini-label">Title words driving their views</div>
        <div class="chips">${r.keywords.map(k =>
          `<span class="chip">${esc(k.word)}<b>${k.lift >= 0 ? '+' : ''}${k.lift}%</b></span>`).join('')}</div>`;
    }
    c += `</div>`;
    html += c;
  });

  if (res.data.errors && res.data.errors.length) {
    html += `<div class="card"><div class="empty">Skipped: ${esc(res.data.errors.join(' | '))}</div></div>`;
  }
  el.innerHTML = html;
}

// Send any benchmark winner into the same source-video Test Factory workflow.
function useForQuiz(url) {
  document.querySelector('.nav-btn[data-tab="qbank"]').click();
  const input = document.getElementById('qbInput');
  input.value = url;
  document.getElementById('qbMaxVideos').value = 1;
  const note = document.getElementById('factorySourceNote');
  note.style.display = 'block';
  note.innerHTML = '<b>Benchmark source selected.</b><br><span>The Factory will fetch this video transcript and create a faculty-review draft.</span>';
  input.focus();
  window.scrollTo({ top: 0, behavior: 'smooth' });
  toast('Source video loaded in Test Factory');
}

/* =================== TRENDS =================== */
document.getElementById('addTrack').addEventListener('click', addTrack);
document.getElementById('captureSnap').addEventListener('click', captureSnap);
document.getElementById('trackInput').addEventListener('keydown', e => { if (e.key === 'Enter') addTrack(); });
document.querySelector('.nav-btn[data-tab="trends"]').addEventListener('click', loadTrends);

async function addTrack() {
  const q = document.getElementById('trackInput').value.trim();
  if (!q) return toast('Enter a channel');
  toast('Adding...');
  const res = await postJSON('/api/watchlist/add', { channel: q });
  if (!res.ok) return toast(res.error);
  document.getElementById('trackInput').value = '';
  toast('Added to watchlist');
  loadTrends();
}

async function captureSnap() {
  toast('Capturing snapshot...');
  const res = await postJSON('/api/snapshot', {});
  if (!res.ok) return toast(res.error);
  toast(`Snapshot saved for ${res.data.captured} channel(s)`);
  loadTrends();
}

async function removeTrack(cid) {
  await postJSON('/api/watchlist/remove', { channel_id: cid });
  toast('Removed from watchlist');
  loadTrends();
}

async function loadTrends() {
  const el = document.getElementById('trendsResult');
  loading(el, 'Loading watchlist...');
  const res = await fetch('/api/watchlist').then(r => r.json());
  if (!res.ok) return errorBox(el, res.error);
  const watch = res.data;
  if (!watch.length) {
    el.innerHTML = `<div class="card"><div class="empty">No channels tracked yet. Add one above, then hit "Capture snapshot" each day to build a growth trend.</div></div>`;
    return;
  }
  let html = '';
  for (const w of watch) {
    const tr = await postJSON('/api/trends', { channel_id: w.channel_id });
    const snaps = (tr.ok && tr.data.snapshots) ? tr.data.snapshots : [];
    html += trendCard(w, snaps);
  }
  el.innerHTML = html;
}

function trendCard(w, snaps) {
  const latest = snaps.length ? snaps[snaps.length - 1] : null;
  const first = snaps.length ? snaps[0] : null;
  const subDelta = (latest && first) ? latest.subscribers - first.subscribers : 0;
  const viewDelta = (latest && first) ? latest.total_views - first.total_views : 0;

  let h = `<div class="card">
    <div class="video-head" style="align-items:center">
      <img src="${esc(w.thumbnail)}" alt="" style="width:60px;height:60px;border-radius:12px">
      <div style="flex:1">
        <div class="vh-title">${esc(w.title)}</div>
        <div class="vh-meta">${w.snapshots} snapshot(s)${latest ? ' · ' + fmt(latest.subscribers) + ' subs · ' + fmt(latest.total_views) + ' views' : ''}</div>
      </div>
      <button class="btn-ghost" onclick="removeTrack('${w.channel_id}')">Remove</button>
    </div>`;

  if (snaps.length >= 2) {
    h += `<div class="metrics" style="margin-top:16px">
      ${metric((subDelta >= 0 ? '+' : '') + fmt(subDelta), 'Subscribers gained', 'green')}
      ${metric((viewDelta >= 0 ? '+' : '') + fmt(viewDelta), 'Views gained', 'blue')}
    </div>
    <div style="margin-top:18px">${lineChart(snaps.map(s => ({ t: s.ts, v: s.subscribers })), 'Subscribers')}</div>
    <div style="margin-top:18px">${lineChart(snaps.map(s => ({ t: s.ts, v: s.total_views })), 'Total views')}</div>`;
  } else {
    h += `<div class="empty" style="margin-top:12px">Only ${snaps.length} snapshot so far — capture again later (e.g. tomorrow) to draw the trend line.</div>`;
  }
  return h + `</div>`;
}

function lineChart(points, label) {
  if (!points.length) return '';
  const W = 640, H = 160, pad = 30;
  const vals = points.map(p => p.v);
  let min = Math.min(...vals), max = Math.max(...vals);
  if (min === max) { min = min - 1; max = max + 1; }
  const n = points.length;
  const x = i => pad + (n === 1 ? (W - 2 * pad) / 2 : (i / (n - 1)) * (W - 2 * pad));
  const y = v => H - pad - ((v - min) / (max - min)) * (H - 2 * pad);
  const line = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join(' ');
  const area = `${line} L${x(n - 1).toFixed(1)},${H - pad} L${x(0).toFixed(1)},${H - pad} Z`;
  const dots = points.map((p, i) => `<circle cx="${x(i).toFixed(1)}" cy="${y(p.v).toFixed(1)}" r="3.2" fill="#ff7a5c"/>`).join('');
  return `<div class="linechart">
    <div class="lc-head"><span class="lc-label">${esc(label)}</span><span class="lc-now">${fmt(vals[n - 1])}</span></div>
    <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" style="width:100%;height:150px">
      <defs><linearGradient id="lcfill" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="rgba(255,68,56,0.30)"/><stop offset="100%" stop-color="rgba(255,68,56,0)"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#lcfill)"/>
      <path d="${line}" fill="none" stroke="#ff4438" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>
      ${dots}
    </svg>
    <div class="lc-axis"><span>${dateShort(points[0].t)}</span><span>${dateShort(points[n - 1].t)}</span></div>
  </div>`;
}

/* =================== KEYWORD RESEARCH =================== */
document.getElementById('runKeywords').addEventListener('click', runKeywords);
document.getElementById('keywordSeed').addEventListener('keydown', e => { if (e.key === 'Enter') runKeywords(); });

function scorePill(v, invert) {
  const hi = invert ? v < 40 : v >= 60;
  const lo = invert ? v >= 60 : v < 40;
  const cls = hi ? 'green' : (lo ? 'accent' : 'yellow');
  return `<span class="score-pill ${cls}">${v}</span>`;
}

async function runKeywords() {
  const seed = document.getElementById('keywordSeed').value.trim();
  const el = document.getElementById('keywordResult');
  if (!seed) return toast('Enter a keyword');
  loading(el, 'Researching related keywords... (10–20s)');
  const res = await postJSON('/api/keywords', { seed });
  if (!res.ok) return errorBox(el, res.error);
  const rows = res.data.rows;
  if (!rows.length) return el.innerHTML = `<div class="card"><div class="empty">No keyword data found. Try a broader seed.</div></div>`;

  let html = `<div class="card"><h2>Keyword opportunities <span class="count">seed: ${esc(res.data.seed)} · ${res.data.checked} checked</span></h2>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Keyword</th><th class="num">Avg views</th><th class="num">Demand</th><th class="num">Competition</th><th class="num">Opportunity</th></tr></thead>
      <tbody>${rows.map(k => `<tr>
        <td>${esc(k.keyword)}</td>
        <td class="num">${fmt(k.avg_views)}</td>
        <td class="num">${scorePill(k.demand)}</td>
        <td class="num">${scorePill(k.competition, true)}</td>
        <td class="num">${scorePill(k.opportunity)}</td>
      </tr>`).join('')}</tbody></table></div>
      <div class="mini-label" style="margin-top:14px">Demand = interest · Competition = how hard to rank (lower is better) · Opportunity = best bets first</div>
    </div>`;
  html += `<div class="card"><h2>Opportunity ranking</h2>${barChart(rows.map(k => ({ label: k.keyword, value: k.opportunity, display: k.opportunity + '/100' })))}</div>`;
  el.innerHTML = html;
}

/* =================== VIRAL FINDER =================== */
document.getElementById('runViral').addEventListener('click', runViral);
document.getElementById('viralQuery').addEventListener('keydown', e => { if (e.key === 'Enter') runViral(); });

async function runViral() {
  const query = document.getElementById('viralQuery').value.trim();
  const el = document.getElementById('viralResult');
  if (!query) return toast('Enter a topic');
  loading(el, 'Scanning niche for viral outliers...');
  const res = await postJSON('/api/viral', { query });
  if (!res.ok) return errorBox(el, res.error);
  const o = res.data.outliers;
  if (!o.length) return el.innerHTML = `<div class="card"><div class="empty">No strong outliers found. Try a broader topic.</div></div>`;

  el.innerHTML = `<div class="card"><h2>Viral outliers <span class="count">${o.length} hits · scanned ${res.data.scanned} · views ÷ subscribers</span></h2>
    <div class="tbl-wrap"><table>
      <thead><tr><th>Video</th><th>Channel</th><th class="num">Views</th><th class="num">Subs</th><th class="num">Views/Sub</th></tr></thead>
      <tbody>${o.map(v => `<tr>
        <td><a href="${esc(v.url)}" target="_blank">${esc(v.title)}</a></td>
        <td>${esc(v.channel_title)}</td>
        <td class="num">${fmt(v.views)}</td>
        <td class="num">${fmt(v.subscribers)}</td>
        <td class="num"><span class="score-pill green">${v.vps}×</span></td>
      </tr>`).join('')}</tbody></table></div></div>`;
}

/* =================== CONTENT GAP =================== */
document.getElementById('runGap').addEventListener('click', runGap);

async function runGap() {
  const yours = document.getElementById('gapYours').value.trim();
  const comp = document.getElementById('gapComp').value.trim();
  const el = document.getElementById('gapResult');
  if (!yours || !comp) return toast('Enter both channels');
  loading(el, 'Comparing coverage & finding gaps...');
  const res = await postJSON('/api/gap', { your_channel: yours, competitor: comp });
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data;
  const head = `${esc(d.competitor_title)} covers these · ${esc(d.your_title)} doesn't`;

  // AI mode — real topic gaps as cards
  if (d.mode === 'ai') {
    const gaps = d.gaps || [];
    if (!gaps.length) return el.innerHTML = `<div class="card"><div class="empty">No clear content gaps — your coverage overlaps well with theirs.</div></div>`;
    el.innerHTML = `<div class="card"><h2>Content gaps <span class="count">${head}</span></h2>
      <div class="gap-list">${gaps.map(g => `
        <div class="gap-item">
          <div class="gap-head">
            <span class="gap-topic">${esc(g.topic)}</span>
            <span class="prio ${esc(g.priority)}">${esc(g.priority)}</span>
          </div>
          ${g.why ? `<div class="gap-why">${esc(g.why)}</div>` : ''}
          ${g.examples && g.examples.length ? `<div class="gap-ex">${g.examples.map(e => `<span class="gap-ex-item">${esc(e)}</span>`).join('')}</div>` : ''}
        </div>`).join('')}</div>
      <div class="mini-label" style="margin-top:14px">AI-clustered topics the competitor's audience engages with — your best untapped content ideas.</div>
    </div>`;
    return;
  }

  // basic fallback (no Gemini key)
  const g = d.gap || [];
  if (!g.length) return el.innerHTML = `<div class="card"><div class="empty">No clear gaps — your coverage overlaps well.</div></div>`;
  el.innerHTML = `<div class="card"><h2>Content gaps <span class="count">${head}</span></h2>
    ${barChart(g.slice(0, 15).map(x => ({ label: x.word, value: x.avg_views, display: fmt(x.avg_views) + ' · ' + x.count + ' vids' })))}
    <div class="mini-label" style="margin-top:14px">Add a Gemini key in .env for smarter topic-level gaps instead of keywords.</div>
  </div>`;
}

/* =================== QUESTION BANK (the Factory) =================== */
let bankQuestions = [];

document.getElementById('runQbank').addEventListener('click', runQbank);

async function runQbank() {
  const input = document.getElementById('qbInput').value.trim();
  const el = document.getElementById('qbankBuildResult');
  if (!input) return toast('Paste a video or playlist URL');
  const body = {
    input,
    count: document.getElementById('qbCount').value,
    max_videos: document.getElementById('qbMaxVideos').value,
    difficulty: document.getElementById('qbDiff').value,
    language: document.getElementById('qbLang').value,
    exam: document.getElementById('qbExam').value.trim(),
  };
  loading(el, 'Extracting & mirroring questions… playlists can take a few minutes.');
  const res = await postJSON('/api/qbank/build', body);
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data;

  let html = `<div class="metrics">
    ${metric(d.added, 'Added to bank', 'green')}
    ${metric(d.skipped, 'Duplicates skipped', 'yellow')}
    ${metric(d.results.length, 'Videos processed', 'blue')}
    ${metric(d.stats.total, 'Bank total', 'accent')}
  </div>`;
  html += `<div class="card"><h2>Build results</h2><div class="list">${d.results.map(r => `
    <div class="list-item">
      <div class="win-title">${r.ok ? '' : '⚠ '}<a href="${esc(r.url)}" target="_blank">${esc(r.title)}</a></div>
      <div class="li-meta">${r.ok
        ? `<span class="badge like">+${r.added} added</span><span class="badge ts">${r.detected || 0} detected in video</span>${r.skipped ? `<span class="badge">${r.skipped} dup</span>` : ''}`
        : `<span class="badge" style="background:rgba(255,68,56,.16);color:var(--accent-2)">${esc(r.error)}</span>`}</div>
    </div>`).join('')}</div></div>`;
  el.innerHTML = html;
  toast(`${d.added} questions added to bank`);
  loadBank();
}

async function loadBank(topic, diff) {
  const el = document.getElementById('qbankView');
  const res = await postJSON('/api/qbank/list', { topic: topic || '', difficulty: diff || '', limit: 500 });
  if (!res.ok) return errorBox(el, res.error);
  const d = res.data, s = d.stats;
  bankQuestions = d.questions;

  if (!s.total) {
    el.innerHTML = `<div class="card"><div class="empty">Your bank is empty. Add a video or playlist above to start building it.</div></div>`;
    return;
  }

  let html = `<div class="metrics">
    ${metric(s.total, 'Total questions', 'accent')}
    ${metric(s.sources, 'Source videos', 'blue')}
    ${metric(s.topics.length, 'Topics', 'green')}
    ${metric(s.difficulties.length, 'Difficulty levels', 'yellow')}
  </div>`;

  html += `<div class="card"><div class="bank-toolbar">
    <select id="qbTopicFilter" class="main-select"><option value="">All topics</option>${s.topics.map(t => `<option value="${esc(t.topic)}" ${t.topic === topic ? 'selected' : ''}>${esc(t.topic)} (${t.n})</option>`).join('')}</select>
    <select id="qbDiffFilter" class="main-select"><option value="">All difficulty</option>${s.difficulties.map(x => `<option value="${esc(x.difficulty)}" ${x.difficulty === diff ? 'selected' : ''}>${esc(x.difficulty)} (${x.n})</option>`).join('')}</select>
    <div class="bank-export-group"><span>Download</span>
      <button class="btn-ghost" id="qbExportExcel">Excel</button>
      <button class="btn-ghost" id="qbExportPdf">PDF</button>
      <button class="btn-ghost" id="qbExportCsv">CSV</button>
    </div>
    <button class="btn-ghost" id="qbClear">Clear bank</button>
    <span class="bank-count">${bankQuestions.length} shown</span>
  </div>`;

  html += `<div class="qb-list">${bankQuestions.map((q, i) => `
    <div class="quiz-q">
      <div class="q-text"><span class="q-num">${i + 1}.</span>${esc(q.question)}</div>
      ${['opt_a', 'opt_b', 'opt_c', 'opt_d'].map((k, oi) => `<div class="quiz-opt ${oi === q.answer_index ? 'correct' : ''}">${String.fromCharCode(65 + oi)}) ${esc(q[k])}${oi === q.answer_index ? ' ✓' : ''}</div>`).join('')}
      ${q.explanation ? `<div class="quiz-exp"><b>Explanation:</b> ${esc(q.explanation)}</div>` : ''}
      <div class="quiz-tags">${q.topic ? `<span class="badge">${esc(q.topic)}</span>` : ''}${q.difficulty ? `<span class="badge ts">${esc(q.difficulty)}</span>` : ''}${q.review_status ? `<span class="badge review-${esc(q.review_status)}">${esc(q.review_status)} · faculty review</span>` : ''}${q.source_url ? `<a class="badge like" href="${esc(q.source_url)}" target="_blank" style="text-decoration:none">source ↗</a>` : ''}</div>
    </div>`).join('')}</div></div>`;

  el.innerHTML = html;

  document.getElementById('qbTopicFilter').addEventListener('change', e =>
    loadBank(e.target.value, document.getElementById('qbDiffFilter').value));
  document.getElementById('qbDiffFilter').addEventListener('change', e =>
    loadBank(document.getElementById('qbTopicFilter').value, e.target.value));
  document.getElementById('qbExportExcel').addEventListener('click', () => exportBankFile('xlsx'));
  document.getElementById('qbExportPdf').addEventListener('click', () => exportBankFile('pdf'));
  document.getElementById('qbExportCsv').addEventListener('click', exportBankCSV);
  document.getElementById('qbClear').addEventListener('click', clearBank);
}

function exportBankFile(format) {
  if (!bankQuestions.length) return toast('Nothing to export');
  const topic = document.getElementById('qbTopicFilter')?.value || '';
  const difficulty = document.getElementById('qbDiffFilter')?.value || '';
  const params = new URLSearchParams({ topic, difficulty });
  const a = document.createElement('a');
  a.href = `/api/qbank/export/${format}?${params.toString()}`;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
  toast(`${format === 'xlsx' ? 'Excel' : 'PDF'} download started`);
}

function exportBankCSV() {
  if (!bankQuestions.length) return toast('Nothing to export');
  const q2 = s => `"${String(s == null ? '' : s).replace(/"/g, '""')}"`;
  const header = ['No', 'Question', 'Option A', 'Option B', 'Option C', 'Option D', 'Answer', 'Explanation', 'Topic', 'Difficulty', 'Exam', 'Source'];
  const rows = bankQuestions.map((q, i) => [i + 1, q.question, q.opt_a, q.opt_b, q.opt_c, q.opt_d,
    String.fromCharCode(65 + q.answer_index), q.explanation, q.topic, q.difficulty, q.exam, q.source_url].map(q2).join(','));
  const csv = '﻿' + header.map(q2).join(',') + '\n' + rows.join('\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'question_bank.csv';
  a.click();
  URL.revokeObjectURL(a.href);
  toast('Question bank exported');
}

async function clearBank() {
  if (!confirm('Clear the entire question bank? This cannot be undone.')) return;
  const res = await postJSON('/api/qbank/clear', {});
  if (res.ok) { toast('Bank cleared'); loadBank(); }
}

// A browser refresh is a new review session. Explicitly restore form defaults
// as some browsers otherwise preserve field values across reloads.
document.getElementById('qbInput').value = '';
document.getElementById('qbCount').value = 20;
document.getElementById('qbMaxVideos').value = 5;
document.getElementById('qbDiff').value = 'mixed';
document.getElementById('qbLang').value = 'English';
document.getElementById('qbExam').value = '';

// Load the freshly reset bank on first paint.
loadBank();

/* ---- shared ---- */
function copyEl(id) {
  const text = document.getElementById(id).innerText;
  navigator.clipboard.writeText(text).then(() => toast('Copied to clipboard'));
}
