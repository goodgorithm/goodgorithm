import type { FastifyInstance } from "fastify";

// The whole page is one static shell — all data comes from the API at
// runtime via fetch(), so this file never needs the DB or per-request
// server-side rendering. Porting the review UX validated in the original
// Civic Tone Review artifact (category grid pre-highlighting the AI
// suggestion, keyboard shortcuts, progress bar, unreviewed/flagged/all
// filter) onto plain fetch() calls instead of that artifact's
// self-publish-the-whole-document mechanism.

const PICKER_HTML = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Labeling studies</title>
<style>
  body { font-family: -apple-system, sans-serif; background: #F7F5F1; color: #22201D; max-width: 480px; margin: 60px auto; padding: 0 20px; }
  h1 { font-size: 20px; }
  #token-form { display: flex; gap: 8px; margin-bottom: 24px; }
  input { flex: 1; padding: 8px 10px; border: 1px solid #E4DFD5; border-radius: 6px; font-size: 14px; }
  button { padding: 8px 14px; border: none; border-radius: 6px; background: #2F6E6E; color: #fff; cursor: pointer; }
  ul { list-style: none; padding: 0; }
  li a { display: block; padding: 12px 14px; border: 1px solid #E4DFD5; border-radius: 8px; margin-bottom: 8px; text-decoration: none; color: #22201D; }
  li a:hover { border-color: #2F6E6E; }
  #error { color: #B5563C; font-size: 13px; }
</style>
</head>
<body>
<h1>Labeling studies</h1>
<div id="token-form">
  <input id="token-input" type="password" placeholder="Access token">
  <button id="token-save">Save</button>
</div>
<div id="error"></div>
<ul id="studies"></ul>
<script>
(function () {
  var stored = localStorage.getItem("labeling_token") || "";
  document.getElementById("token-input").value = stored;
  document.getElementById("token-save").addEventListener("click", function () {
    localStorage.setItem("labeling_token", document.getElementById("token-input").value);
    load();
  });
  function load() {
    var token = localStorage.getItem("labeling_token") || "";
    fetch("/api/studies", { headers: { "X-Access-Token": token } })
      .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function (data) {
        document.getElementById("error").textContent = "";
        var ul = document.getElementById("studies");
        ul.innerHTML = "";
        data.studies.forEach(function (s) {
          var li = document.createElement("li");
          var a = document.createElement("a");
          a.href = "/study/" + s.slug;
          a.textContent = s.name;
          li.appendChild(a);
          ul.appendChild(li);
        });
      })
      .catch(function (e) { document.getElementById("error").textContent = "Couldn't load studies: " + e.message; });
  }
  load();
})();
</script>
</body>
</html>`;

function studyHtml(slug: string): string {
  const safeSlug = JSON.stringify(slug);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Labeling — ${slug}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
  :root {
    --ground: #F7F5F1; --ground-raised: #FFFFFF; --ink: #22201D; --ink-dim: #6B665D; --line: #E4DFD5;
    --accent: #2F6E6E; --accent-ink: #FFFFFF; --focus-ring: #2F6E6E;
  }
  * { box-sizing: border-box; }
  body { background: var(--ground); color: var(--ink); font-family: 'IBM Plex Sans', -apple-system, sans-serif; margin: 0; }
  .mono { font-family: 'IBM Plex Mono', ui-monospace, monospace; font-variant-numeric: tabular-nums; }
  #app { display: flex; min-height: 100vh; }
  .rail { width: 280px; flex: none; border-right: 1px solid var(--line); padding: 24px 20px; display: flex; flex-direction: column; gap: 24px; }
  .rail h1 { font-size: 17px; font-weight: 600; margin: 0 0 2px; }
  .rail .sub { font-size: 12.5px; color: var(--ink-dim); line-height: 1.5; }
  .progress-track { height: 6px; border-radius: 3px; background: var(--line); overflow: hidden; }
  .progress-fill { height: 100%; background: var(--accent); border-radius: 3px; }
  .progress-label { display: flex; justify-content: space-between; font-size: 12px; color: var(--ink-dim); margin-bottom: 6px; }
  .filters { display: flex; flex-direction: column; gap: 4px; }
  .filter-btn { all: unset; cursor: pointer; padding: 7px 10px; border-radius: 7px; font-size: 12.5px; color: var(--ink-dim); display: flex; justify-content: space-between; }
  .filter-btn.active { background: var(--ground-raised); color: var(--ink); font-weight: 600; }
  .keys { font-size: 11px; color: var(--ink-dim); line-height: 1.9; }
  .keys kbd { font-family: 'IBM Plex Mono', monospace; background: var(--ground-raised); border: 1px solid var(--line); border-radius: 4px; padding: 1px 5px; font-size: 10.5px; margin-right: 4px; }
  main { flex: 1; padding: 40px 48px; display: flex; flex-direction: column; align-items: center; }
  .card-wrap { width: 100%; max-width: 720px; }
  .meta-row { display: flex; align-items: center; gap: 14px; font-size: 12px; color: var(--ink-dim); margin-bottom: 14px; flex-wrap: wrap; }
  .pill { display: inline-flex; align-items: center; gap: 5px; border: 1px solid var(--line); border-radius: 100px; padding: 2px 10px; font-size: 11.5px; }
  .post-card { background: var(--ground-raised); border: 1px solid var(--line); border-radius: 14px; padding: 30px 32px; margin-bottom: 22px; }
  .post-text { font-family: 'Source Serif 4', Georgia, serif; font-size: 19px; line-height: 1.62; white-space: pre-wrap; }
  .hashtags { margin-top: 12px; display: flex; gap: 6px; flex-wrap: wrap; }
  .hashtag-chip { font-size: 12px; background: var(--ground); border: 1px solid var(--line); border-radius: 100px; padding: 2px 10px; color: var(--ink-dim); }
  .attachment, .quote-block { margin-top: 16px; border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; font-size: 13px; }
  .attachment img { max-width: 100%; border-radius: 6px; }
  .attachment .link-title { font-weight: 600; }
  .attachment .link-desc, .attachment .link-url { color: var(--ink-dim); }
  .quote-block { background: var(--ground); font-style: italic; }
  .ai-suggestion { margin-top: 22px; padding-top: 16px; border-top: 1px dashed var(--line); font-size: 12.5px; color: var(--ink-dim); }
  .category-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; margin-bottom: 14px; }
  .cat-btn { all: unset; cursor: pointer; text-align: center; padding: 13px 6px 11px; border-radius: 10px; border: 1.5px solid var(--line); font-size: 12px; font-weight: 500; }
  .cat-btn .k { display: block; font-family: 'IBM Plex Mono', monospace; font-size: 10px; color: var(--ink-dim); margin-bottom: 5px; }
  .cat-btn:hover { border-color: var(--accent); }
  .cat-btn.selected { border-color: transparent; color: #fff; }
  .cat-btn.ai-pick:not(.selected) { box-shadow: 0 0 0 1px var(--cat-color, var(--accent)) inset; }
  .flag-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
  .flag-btn { all: unset; cursor: pointer; font-size: 12px; padding: 7px 12px; border-radius: 8px; border: 1.5px solid var(--line); color: var(--ink-dim); }
  .flag-btn.active { border-color: #B5563C; color: #B5563C; }
  .notes { width: 100%; resize: vertical; min-height: 44px; background: var(--ground); border: 1px solid var(--line); border-radius: 8px; color: var(--ink); font-family: inherit; font-size: 13px; padding: 9px 11px; margin-bottom: 18px; }
  .nav-row { display: flex; justify-content: space-between; }
  .nav-btn { all: unset; cursor: pointer; font-size: 13px; padding: 9px 16px; border-radius: 8px; border: 1.5px solid var(--line); }
  .nav-btn.primary { background: var(--accent); color: var(--accent-ink); border-color: var(--accent); font-weight: 600; }
  .done-state { text-align: center; padding: 80px 20px; color: var(--ink-dim); }
  .toast { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); background: var(--ink); color: var(--ground); font-size: 12.5px; padding: 8px 16px; border-radius: 100px; opacity: 0; pointer-events: none; transition: opacity 0.2s ease; }
  .toast.show { opacity: 0.92; }
  @media (max-width: 860px) { #app { flex-direction: column; } .rail { width: 100%; } main { padding: 24px 18px; } }
</style>
</head>
<body>
<div id="app"></div>
<div class="toast" id="toast"></div>
<script>
(function () {
  "use strict";
  var STUDY_SLUG = ${safeSlug};
  var TOKEN = localStorage.getItem("labeling_token") || "";
  var CATEGORIES = [];
  var STATE = { filter: "unreviewed", index: 0, posts: [] };

  function api(path, opts) {
    opts = opts || {};
    opts.headers = Object.assign({ "X-Access-Token": TOKEN, "Content-Type": "application/json" }, opts.headers || {});
    return fetch(path, opts).then(function (r) {
      if (!r.ok) return r.json().then(function (b) { throw new Error(b.error || ("HTTP " + r.status)); });
      return r.json();
    });
  }

  function showToast(msg) {
    var t = document.getElementById("toast");
    t.textContent = msg;
    t.classList.add("show");
    clearTimeout(showToast._h);
    showToast._h = setTimeout(function () { t.classList.remove("show"); }, 1400);
  }

  function esc(s) { return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  function catColor(id) {
    var c = CATEGORIES.find(function (x) { return x.id === id; });
    return c ? c.color : "#6B665D";
  }

  function loadPosts() {
    return api("/api/studies/" + STUDY_SLUG + "/posts?filter=" + STATE.filter).then(function (data) {
      CATEGORIES = data.study.categories;
      STATE.posts = data.posts;
      if (STATE.index >= STATE.posts.length) STATE.index = Math.max(0, STATE.posts.length - 1);
      render();
    });
  }

  function counts() {
    return { total: STATE.posts.length };
  }

  function renderAttachment(a) {
    if (a.kind === "image") return '<div class="attachment"><img src="' + esc(a.thumbnailUrl) + '" alt="' + esc(a.alt || "") + '"></div>';
    if (a.kind === "link") return '<div class="attachment"><div class="link-title">' + esc(a.title || a.url) + '</div>' +
      (a.description ? '<div class="link-desc">' + esc(a.description) + '</div>' : '') +
      '<div class="link-url">' + esc(a.url) + '</div></div>';
    if (a.kind === "video") return '<div class="attachment">[video' + (a.isGif ? ", gif-like" : "") + ']</div>';
    if (a.kind === "quote") {
      var c = a.content;
      if (c && c.status === "available") return '<div class="quote-block">"' + esc(c.text) + '" — ' + esc(c.author.displayName || c.author.handle || "unknown") + '</div>';
      return '<div class="quote-block">[quoted post unavailable]</div>';
    }
    return "";
  }

  function render() {
    var vis = STATE.posts;
    var post = vis[STATE.index];
    var c = counts();

    var railHtml = '<div><h1>' + esc(STUDY_SLUG) + '</h1><div class="sub">Labeling review</div></div>'
      + '<div><div class="progress-label"><span>Queue</span><span class="mono">' + c.total + '</span></div>'
      + '<div class="progress-track"><div class="progress-fill" style="width:' + (c.total ? 100 : 0) + '%"></div></div></div>'
      + '<div class="filters">'
      + ["unreviewed", "flagged", "all"].map(function (f) {
          return '<button class="filter-btn' + (STATE.filter === f ? " active" : "") + '" data-filter="' + f + '">' + f + '</button>';
        }).join("")
      + '</div>'
      + '<div class="keys"><div><kbd>1</kbd>-<kbd>' + CATEGORIES.length + '</kbd> pick category</div>'
      + '<div><kbd>&larr;</kbd><kbd>&rarr;</kbd> prev / next</div><div><kbd>&crarr;</kbd> confirm AI suggestion</div>'
      + '<div><kbd>F</kbd> flag taxonomy issue</div></div>';

    document.getElementById("app").innerHTML = '<div class="rail">' + railHtml + '</div><main>' + (post ? renderCard(post) : '<div class="done-state"><h2>Nothing left in this filter</h2></div>') + '</main>';
    attachHandlers();
  }

  function renderCard(post) {
    var chosen = post.maintainer_label ? post.maintainer_label.category : null;
    var aiCat = post.ai_label ? post.ai_label.category : null;
    var buttons = CATEGORIES.map(function (cat, i) {
      var cls = "cat-btn";
      if (chosen === cat.id) cls += " selected";
      else if (!chosen && aiCat === cat.id) cls += " ai-pick";
      var style = chosen === cat.id ? "background:" + cat.color : (aiCat === cat.id ? "--cat-color:" + cat.color : "");
      return '<button class="' + cls + '" data-cat="' + cat.id + '" style="' + style + '"><span class="k">' + (i + 1) + '</span>' + esc(cat.label) + '</button>';
    }).join("");

    var attachmentsHtml = (post.attachments || []).map(renderAttachment).join("");
    var hashtagsHtml = (post.hashtags || []).length
      ? '<div class="hashtags">' + post.hashtags.map(function (h) { return '<span class="hashtag-chip">#' + esc(h) + '</span>'; }).join("") + '</div>'
      : "";

    return '<div class="card-wrap">'
      + '<div class="meta-row"><span class="pill mono">' + esc(post.source || "") + '</span>'
      + (post.rank_score != null ? '<span class="pill mono">rank ' + Number(post.rank_score).toFixed(3) + '</span>' : '')
      + '<span class="mono">' + esc((post.original_created_at || "").slice(0, 16)) + '</span></div>'
      + '<div class="post-card"><div class="post-text">' + esc(post.text) + '</div>' + hashtagsHtml + attachmentsHtml
      + '<div class="ai-suggestion">AI-drafted suggestion: <b>' + esc(aiCat || "none") + '</b></div></div>'
      + '<div class="category-grid">' + buttons + '</div>'
      + '<div class="flag-row"><button class="flag-btn' + (post.maintainer_label && post.maintainer_label.taxonomy_flag ? " active" : "") + '" data-action="flag">&#9873; Doesn\\'t fit the taxonomy</button></div>'
      + '<textarea class="notes" placeholder="Optional note..." data-action="notes">' + esc(post.maintainer_label ? post.maintainer_label.notes : "") + '</textarea>'
      + '<div class="nav-row"><button class="nav-btn" data-action="prev">&larr; Prev</button>'
      + '<button class="nav-btn primary" data-action="confirm">' + (chosen ? "Next →" : "Confirm & next →") + '</button></div></div>';
  }

  function submitLabel(post, category, extra) {
    var body = Object.assign({ category: category, taxonomy_flag: false, notes: "" }, post.maintainer_label || {}, extra || {}, { category: category });
    return api("/api/studies/" + STUDY_SLUG + "/posts/" + post.id + "/label", { method: "POST", body: JSON.stringify(body) })
      .then(function () { showToast("Saved"); return loadPosts(); })
      .catch(function (e) { showToast("Save failed: " + e.message); });
  }

  function advance() {
    if (STATE.index < STATE.posts.length - 1) STATE.index++;
    else STATE.index = Math.max(0, STATE.posts.length - 1);
    render();
  }

  function confirmOrAdvance(post) {
    if (post && !post.maintainer_label) submitLabel(post, post.ai_label ? post.ai_label.category : CATEGORIES[0].id);
    else advance();
  }

  function attachHandlers() {
    document.querySelectorAll(".filter-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { STATE.filter = btn.getAttribute("data-filter"); STATE.index = 0; loadPosts(); });
    });
    var post = STATE.posts[STATE.index];
    document.querySelectorAll(".cat-btn").forEach(function (btn) {
      btn.addEventListener("click", function () { if (post) submitLabel(post, btn.getAttribute("data-cat")); });
    });
    var flagBtn = document.querySelector('[data-action="flag"]');
    if (flagBtn) flagBtn.addEventListener("click", function () {
      if (!post) return;
      var current = post.maintainer_label ? post.maintainer_label.category : (post.ai_label ? post.ai_label.category : CATEGORIES[0].id);
      submitLabel(post, current, { taxonomy_flag: !(post.maintainer_label && post.maintainer_label.taxonomy_flag) });
    });
    var notes = document.querySelector('[data-action="notes"]');
    if (notes) notes.addEventListener("blur", function () {
      if (!post) return;
      var current = post.maintainer_label ? post.maintainer_label.category : (post.ai_label ? post.ai_label.category : CATEGORIES[0].id);
      submitLabel(post, current, { notes: notes.value });
    });
    var prevBtn = document.querySelector('[data-action="prev"]');
    if (prevBtn) prevBtn.addEventListener("click", function () { STATE.index = Math.max(0, STATE.index - 1); render(); });
    var confirmBtn = document.querySelector('[data-action="confirm"]');
    if (confirmBtn) confirmBtn.addEventListener("click", function () { confirmOrAdvance(post); });
  }

  document.addEventListener("keydown", function (e) {
    if (e.target && (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT")) return;
    var post = STATE.posts[STATE.index];
    var n = parseInt(e.key, 10);
    if (!isNaN(n) && n >= 1 && n <= CATEGORIES.length) {
      if (post) submitLabel(post, CATEGORIES[n - 1].id);
    } else if (e.key === "ArrowRight") advance();
    else if (e.key === "ArrowLeft") { STATE.index = Math.max(0, STATE.index - 1); render(); }
    else if (e.key === "Enter") confirmOrAdvance(post);
    else if (e.key.toLowerCase() === "f") {
      if (post) {
        var current = post.maintainer_label ? post.maintainer_label.category : (post.ai_label ? post.ai_label.category : CATEGORIES[0].id);
        submitLabel(post, current, { taxonomy_flag: !(post.maintainer_label && post.maintainer_label.taxonomy_flag) });
      }
    }
  });

  loadPosts();
})();
</script>
</body>
</html>`;
}

export async function uiRoute(app: FastifyInstance): Promise<void> {
  app.get("/", async (_request, reply) => {
    reply.header("Content-Type", "text/html");
    return PICKER_HTML;
  });

  app.get<{ Params: { slug: string } }>("/study/:slug", async (request, reply) => {
    reply.header("Content-Type", "text/html");
    return studyHtml(request.params.slug);
  });
}
