const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const STORE_HOST = "ranchr.host";
const STORE_TOKEN = "ranchr.token";
const COOKIE_HOST = "ranchr_host";
const COOKIE_TOKEN = "ranchr_token";

function cookiePath() {
  return new URL("./", location.href).pathname;
}

function writeCookie(name, value) {
  if (!value) return;
  const secure = location.protocol === "https:" ? "; Secure" : "";
  document.cookie =
    `${name}=${encodeURIComponent(value)}; Max-Age=${60 * 60 * 24 * 180}; Path=${cookiePath()}; SameSite=Lax${secure}`;
}

function readCookie(name) {
  for (const part of document.cookie.split(";")) {
    const p = part.trim();
    const eq = p.indexOf("=");
    if (eq < 0) continue;
    if (p.slice(0, eq) === name) {
      try {
        return decodeURIComponent(p.slice(eq + 1));
      } catch {
        return p.slice(eq + 1);
      }
    }
  }
  return "";
}

function storeGet(key) {
  try {
    return localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function storeSet(key, value) {
  if (!value) return;
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode */
  }
}

function persistRanch(host, token) {
  if (host) {
    storeSet(STORE_HOST, host);
    writeCookie(COOKIE_HOST, host);
  }
  if (token) {
    storeSet(STORE_TOKEN, token);
    writeCookie(COOKIE_TOKEN, token);
  }
}

function absorbConnect() {
  const q = new URLSearchParams(location.search);
  const host = (q.get("host") || "").trim().replace(/\/$/, "");
  const token = (q.get("t") || "").trim();
  // Keep host+t in the URL. iOS Add to Home Screen / Add to Dock uses the
  // page URL (and the manifest start_url); stripping the query drops the ranch.
  persistRanch(host, token);
}

function ranchHost() {
  const q = (new URLSearchParams(location.search).get("host") || "").trim().replace(/\/$/, "");
  if (q) return q;
  return (storeGet(STORE_HOST) || readCookie(COOKIE_HOST)).replace(/\/$/, "");
}

function ranchToken() {
  const q = (new URLSearchParams(location.search).get("t") || "").trim();
  if (q) return q;
  return storeGet(STORE_TOKEN) || readCookie(COOKIE_TOKEN);
}

function onPages() {
  return location.hostname.endsWith("github.io");
}

function apiUrl(path) {
  const host = ranchHost();
  const base = host || (onPages() ? "" : location.origin);
  if (!base) {
    const err = new Error("no ranch connected");
    err.code = "NO_RANCH";
    throw err;
  }
  const url = new URL(path, base + "/");
  const token = ranchToken();
  if (token && host) url.searchParams.set("t", token);
  return url.toString();
}

absorbConnect();
bootCachedTheme();

const state = {
  herd: { host: "this PC", agents: [], blocked: 0, default_agent: "codex" },
  filter: "all",
  screen: "herd",
  sessionId: null,
  sessionMode: "chat",
  kind: "codex",
  session: null,
  pendingUser: null,
  thinking: false,
  pollTimer: null,
  skipById: {},
  noticesById: {},
  workOpen: {},
  chatStick: true,
  chatScrolling: false,
  themeSlug: "",
  themeRev: "",
  themeApplied: false,
};

const THEME_STORE = "ranchr.theme.css";

function paintThemeCss(css) {
  if (!css || css.length < 40) return false;
  let tag = document.getElementById("ranch-theme");
  if (!tag) {
    tag = document.createElement("style");
    tag.id = "ranch-theme";
    document.head.appendChild(tag);
  }
  tag.textContent = css;
  try {
    localStorage.setItem(THEME_STORE, css);
  } catch {
    /* private mode */
  }
  if (navigator.serviceWorker && navigator.serviceWorker.controller) {
    navigator.serviceWorker.controller.postMessage({ type: "ranch-theme", css });
  }
  const bg = getComputedStyle(document.documentElement).getPropertyValue("--omarchy-background").trim()
    || getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta && bg.startsWith("#")) meta.setAttribute("content", bg);
  return true;
}

function bootCachedTheme() {
  try {
    const css = localStorage.getItem(THEME_STORE);
    if (css) paintThemeCss(css);
  } catch {
    /* ignore */
  }
}

async function pullRanchTheme() {
  try {
    const headers = {};
    const token = ranchToken();
    if (token && ranchHost()) headers.Authorization = "Bearer " + token;
    const res = await fetch(apiUrl("/api/theme.css"), { headers, cache: "no-store" });
    if (!res.ok) return false;
    const css = await res.text();
    return paintThemeCss(css);
  } catch {
    return false;
  }
}

function applyHerdTheme(herd) {
  const rev = (herd && (herd.theme_rev || herd.theme)) || "";
  if (rev && rev === state.themeRev && state.themeApplied) return;
  pullRanchTheme().then((ok) => {
    if (!ok) return;
    if (rev) state.themeRev = rev;
    if (herd && herd.theme) state.themeSlug = herd.theme;
    state.themeApplied = true;
  });
}

function toast(msg) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.add("on");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.remove("on"), 2800);
}

async function api(path, opts) {
  const headers = { "Content-Type": "application/json", ...(opts && opts.headers) };
  const token = ranchToken();
  if (token && ranchHost()) headers.Authorization = "Bearer " + token;
  const res = await fetch(apiUrl(path), {
    ...opts,
    headers,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function go(id) {
  state.screen = id;
  $$(".screen").forEach((el) => {
    if (el.id === "placeholder") {
      el.classList.toggle("active", id === "herd");
      return;
    }
    el.classList.toggle("active", el.id === id);
  });
  $$("#herd-list .card").forEach((card) => {
    card.classList.toggle("selected", id === "session" && card.dataset.id === state.sessionId);
  });
  closeSheet();
  updateJumpLatest();
}

function applyFilter() {
  const cards = $$("#herd-list .card");
  let shown = 0;
  cards.forEach((card) => {
    const match = state.filter === "all" || card.dataset.status === state.filter;
    card.classList.toggle("is-hidden", !match);
    if (match) shown += 1;
  });
  const meta = $("#herd-meta");
  const label = shown === 1 ? "1 agent" : `${shown} agents`;
  const live = state.filter === "all" ? `${label} live` : label;
  if (meta) meta.textContent = `Herdr · ${live}`;
  const emptyFilter = $("#filter-empty");
  if (emptyFilter) {
    const show = shown === 0 && cards.length > 0;
    emptyFilter.hidden = !show;
    emptyFilter.classList.toggle("show", show);
  }
}

function renderHerd() {
  const { herd } = state;
  $("#host-name").textContent = herd.host || "this PC";
  const badge = $("#inbox-badge");
  badge.hidden = !herd.blocked;
  badge.textContent = String(herd.blocked || 0);
  const list = $("#herd-list");
  const empty = $("#herd-empty");
  if (!herd.agents?.length) {
    list.innerHTML = "";
    empty.hidden = false;
    applyFilter();
    renderInbox();
    return;
  }
  empty.hidden = true;
  list.innerHTML = herd.agents
    .map((a) => {
      const needs = a.status === "blocked";
      const preview = needs
        ? `<div class="preview"><em>Needs you ·</em> ${escapeHtml(a.preview || "waiting")}</div>`
        : `<div class="preview">${escapeHtml(a.preview || "—")}</div>`;
      const selected = state.sessionId === a.id && state.screen === "session";
      return `<article class="card${needs ? " needs" : ""}${selected ? " selected" : ""}" data-status="${a.status}" data-id="${a.id}">
        <div class="card-top">
          <span class="pip ${a.status}"></span>
          <div class="who">
            <div class="title">${escapeHtml(a.title || a.agent)}</div>
            <div class="sub">${escapeHtml(a.cwd_pretty || a.cwd || "")}</div>
          </div>
          <button class="card-close" data-close="${a.id}" title="Terminate session" aria-label="Terminate session">×</button>
        </div>
        ${preview}
        <div class="tags">
          <span class="tag${needs ? " blocked" : ""}">${escapeHtml(a.status)}</span>
          ${a.workspace ? `<span class="tag">${escapeHtml(a.workspace)}</span>` : ""}
        </div>
      </article>`;
    })
    .join("");
  list.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("[data-close]")) return;
      openSession(card.dataset.id);
    });
  });
  list.querySelectorAll("[data-close]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      closeAgent(btn.dataset.close);
    });
  });
  applyFilter();
  renderInbox();
}

function renderInbox() {
  const blocked = (state.herd.agents || []).filter((a) => a.status === "blocked");
  $("#inbox-meta").textContent =
    blocked.length === 1 ? "one blocked pane" : `${blocked.length} blocked panes`;
  const list = $("#inbox-list");
  if (!blocked.length) {
    list.innerHTML = `<p class="empty">Nothing needs you.</p>`;
    return;
  }
  list.innerHTML = blocked
    .map(
      (a) => `<article class="card needs" data-id="${a.id}">
        <div class="card-top">
          <span class="pip blocked"></span>
          <div class="who">
            <div class="title">${escapeHtml(a.title || a.agent)} wants input</div>
            <div class="sub">${escapeHtml(a.cwd_pretty || "")}</div>
          </div>
        </div>
        <div class="preview">${escapeHtml(a.preview || "")}</div>
        <div class="row-btns" style="margin-top:12px">
          <button class="btn quiet" data-act="deny">Deny</button>
          <button class="btn quiet" data-act="once">Once</button>
          <button class="btn primary" data-act="always">Allow</button>
        </div>
      </article>`
    )
    .join("");
  list.querySelectorAll(".card").forEach((card) => {
    card.addEventListener("click", (ev) => {
      if (ev.target.closest("button")) return;
      openSession(card.dataset.id);
    });
    card.querySelectorAll("button[data-act]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        approve(card.dataset.id, btn.dataset.act);
      });
    });
  });
}

function setThinking(on) {
  state.thinking = on;
  updateComposerMode();
}

function isWorking() {
  return state.thinking || state.session?.agent?.status === "working";
}

function updateComposerMode() {
  const working = isWorking();
  $("#send").hidden = working;
  $("#send-now").hidden = !working;
  const bar = $("#working-bar");
  if (bar) bar.hidden = !working;
  const box = $("#composer");
  if (box) {
    box.placeholder = working
      ? "Steer this turn — Now interrupts and sends"
      : "Steer this session…";
  }
}

async function openSession(id) {
  stopPoll();
  state.sessionId = id;
  state.pendingUser = null;
  setThinking(false);
  state.session = null;
  state.chatStick = true;
  go("session");
  await refreshSession();
  pinThread();
}

function stopPoll() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

function ensureWorkingPoll() {
  if (state.pollTimer || state.screen !== "session") return;
  state.pollTimer = setInterval(async () => {
    await refreshSession();
  }, 500);
}

function transcriptHasReply(messages, userText) {
  const want = userText.trim();
  let seenUser = false;
  for (const m of messages || []) {
    if (m.role === "user" && (m.text || "").trim() === want) {
      seenUser = true;
      continue;
    }
    if (seenUser && m.role === "tool") return true;
    if (seenUser && m.role === "agent" && (m.text || "").trim()) return true;
  }
  return false;
}

async function refreshSession() {
  if (!state.sessionId) return;
  try {
    const data = await api(`/api/agents/${encodeURIComponent(state.sessionId)}/session`);
    state.session = data;
    const a = data.agent;
    $("#session-name").textContent = a.title || a.agent;
    $("#session-meta").textContent = `${a.cwd_pretty || a.cwd} · ${a.status}`;
    const pip = $("#session-pip");
    pip.className = `pip ${a.status}`;
    const blocked = a.status === "blocked";
    const need = $("#session-need");
    need.hidden = !blocked;
    if (blocked) {
      $("#session-need-text").textContent = a.preview || "This agent is waiting.";
    }
    if (state.pendingUser && transcriptHasReply(visibleMessages(data.messages), state.pendingUser)) {
      state.pendingUser = null;
      setThinking(false);
    } else if (state.thinking && blocked) {
      setThinking(false);
    }
    $("#session-term").textContent = data.text || "";
    renderChat(data);
    setSessionMode(state.sessionMode);
    updateComposerMode();
    if (state.thinking || a.status === "working") ensureWorkingPoll();
    else stopPoll();
  } catch (err) {
    if (!state.thinking) toast(err.message);
  }
}

function visibleMessages(messages) {
  const all = messages || [];
  const skip = state.skipById[state.sessionId] || 0;
  if (skip > all.length) return all;
  return all.slice(skip);
}

function groupChat(messages) {
  const groups = [];
  for (const m of messages) {
    if (m.role === "tool") {
      const last = groups[groups.length - 1];
      if (last && last.role === "agent") {
        last.tools.push(m);
      } else {
        groups.push({ role: "agent", text: "", tools: [m] });
      }
    } else {
      groups.push({ role: m.role, text: m.text, tools: [] });
    }
  }
  return groups;
}

const CHAT_BOTTOM_PX = 80;

function threadEl() {
  return $("#session-thread");
}

function threadAtBottom(el) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < CHAT_BOTTOM_PX;
}

function updateJumpLatest() {
  const btn = $("#jump-latest");
  if (!btn) return;
  const chat = state.screen === "session" && state.sessionMode !== "term";
  btn.hidden = !(chat && !state.chatStick);
}

function pinThread() {
  const el = threadEl();
  if (!el) return;
  state.chatStick = true;
  const snap = () => {
    state.chatScrolling = true;
    el.scrollTop = el.scrollHeight;
  };
  snap();
  requestAnimationFrame(() => {
    snap();
    requestAnimationFrame(() => {
      snap();
      state.chatScrolling = false;
      updateJumpLatest();
    });
  });
}

function renderChat(data) {
  const el = threadEl();
  const agentName = data?.agent?.agent || "agent";
  const working = isWorking();
  const messages = [...visibleMessages(data?.messages)];
  const notices = state.noticesById[state.sessionId] || [];
  if (state.pendingUser) {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (!lastUser || lastUser.text.trim() !== state.pendingUser.trim()) {
      messages.push({ role: "user", text: state.pendingUser });
    }
  }
  const groups = groupChat(messages);
  if (!groups.length && !notices.length && !state.thinking) {
    const note = data?.note || "No chat transcript yet.";
    el.innerHTML = `<p class="empty">${escapeHtml(note)}</p>`;
    el._html = "";
    updateJumpLatest();
    return;
  }
  const open = state.workOpen[state.sessionId] || {};
  let html = notices
    .map((n) => `<div class="msg system">${escapeHtml(n)}</div>`)
    .join("");
  html += groups
    .map((g, i) => {
      if (g.role === "user") {
        return `<div class="msg you">${escapeHtml(g.text)}</div>`;
      }
      const last = i === groups.length - 1;
      const busy = last && working;
      const tools = g.tools || [];
      const expanded = Boolean(open[i]);
      let body = `<div class="kicker">${escapeHtml(agentName)}</div>`;
      if (g.text) body += `<div class="agent-text">${escapeHtml(g.text)}</div>`;
      if (busy && !g.text) {
        body += `<span class="dots" aria-live="polite"><span></span><span></span><span></span></span>`;
      }
      if (tools.length) {
        const label = busy
          ? `Working · ${tools.length}`
          : `${tools.length} step${tools.length === 1 ? "" : "s"}`;
        const chev = expanded ? "▾" : "▸";
        body += `<button type="button" class="work-toggle" data-work="${i}" aria-expanded="${expanded}">${
          busy
            ? `<span class="dots tiny"><span></span><span></span><span></span></span>`
            : `<span class="chev">${chev}</span>`
        } ${label}</button><div class="work-list"${expanded ? "" : " hidden"}>${tools
          .map((t) => `<div class="tool">${escapeHtml(t.text)}</div>`)
          .join("")}</div>`;
      } else if (busy && g.text) {
        body += `<div class="work-toggle static"><span class="dots tiny"><span></span><span></span><span></span></span> Working</div>`;
      }
      return `<div class="msg agent${busy ? " busy" : ""}">${body}</div>`;
    })
    .join("");
  const last = groups[groups.length - 1];
  if (state.thinking && (!last || last.role !== "agent")) {
    html += `<div class="msg agent thinking" aria-live="polite">
      <div class="kicker">${escapeHtml(agentName)}</div>
      <span class="dots"><span></span><span></span><span></span></span>
    </div>`;
  }
  const stick = state.chatStick;
  const prevTop = el.scrollTop;
  if (el._html !== html) {
    el._html = html;
    el.innerHTML = html;
    el.querySelectorAll(".work-toggle[data-work]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const key = btn.dataset.work;
        const map = state.workOpen[state.sessionId] || {};
        map[key] = !map[key];
        state.workOpen[state.sessionId] = map;
        const openNow = map[key];
        const list = btn.nextElementSibling;
        if (list && list.classList.contains("work-list")) list.hidden = !openNow;
        btn.setAttribute("aria-expanded", openNow);
        const chev = btn.querySelector(".chev");
        if (chev) chev.textContent = openNow ? "▾" : "▸";
        if (state.chatStick) pinThread();
      });
    });
  }
  if (stick) pinThread();
  else el.scrollTop = prevTop;
  updateJumpLatest();
}

function setSessionMode(mode) {
  state.sessionMode = mode;
  $$("#session .seg button").forEach((b) =>
    b.classList.toggle("on", b.dataset.mode === mode)
  );
  $("#thread-wrap").classList.toggle("off", mode === "term");
  $("#session-term").classList.toggle("on", mode === "term");
  updateJumpLatest();
  if (mode !== "term" && state.chatStick) pinThread();
}

const HERD_COMMANDS = new Set(["/clear", "/reset", "/new", "/cancel", "/stop"]);

function herdCommand(text) {
  const trimmed = text.trim();
  const m = trimmed.match(/^(\/[a-zA-Z][\w-]*)(?:\s|$)/);
  if (!m) return null;
  const cmd = m[1].toLowerCase();
  if (!HERD_COMMANDS.has(cmd)) return null;
  if (trimmed !== cmd && !trimmed.startsWith(cmd + " ")) return null;
  return cmd;
}

function note(text) {
  const id = state.sessionId;
  if (!id) return;
  const list = state.noticesById[id] || [];
  list.push(text);
  state.noticesById[id] = list;
}

async function sendPrompt() {
  const box = $("#composer");
  const text = box.value.trim();
  if (!text || !state.sessionId) return;
  if (state.thinking && !isWorking()) return;
  box.value = "";
  growComposer(box);

  const cmd = herdCommand(text);
  if (cmd) {
    if (cmd === "/cancel" || cmd === "/stop") {
      await cancelTurn();
      return;
    }
    if (cmd === "/clear" || cmd === "/reset" || cmd === "/new") {
      state.skipById[state.sessionId] = (state.session?.messages || []).length;
      state.pendingUser = null;
      setThinking(false);
      stopPoll();
      note("Cleared conversation");
    } else {
      note(`Ran ${cmd}`);
    }
    state.chatStick = true;
    renderChat(state.session || { messages: [] });
    try {
      await api(`/api/agents/${encodeURIComponent(state.sessionId)}/prompt`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
    } catch (err) {
      toast(err.message);
    }
    return;
  }

  const interject = isWorking();
  state.pendingUser = text;
  state.chatStick = true;
  setThinking(true);
  renderChat(state.session || { messages: [], agent: { agent: "agent" } });
  try {
    await api(`/api/agents/${encodeURIComponent(state.sessionId)}/prompt`, {
      method: "POST",
      body: JSON.stringify({ text, interject }),
    });
  } catch (err) {
    state.pendingUser = null;
    setThinking(false);
    box.value = text;
    growComposer(box);
    toast(err.message);
    renderChat(state.session || { messages: [] });
    if (/blocked/i.test(err.message)) refreshSession();
    return;
  }
  stopPoll();
  let ticks = 0;
  state.pollTimer = setInterval(async () => {
    ticks += 1;
    if (ticks > 240) {
      setThinking(false);
      stopPoll();
      toast("Still working on the PC — check Terminal");
      renderChat(state.session || { messages: [] });
      return;
    }
    await refreshSession();
  }, 500);
  refreshSession();
}

async function closeAgent(id) {
  const agent = (state.herd.agents || []).find((a) => a.id === id);
  const label = agent?.title || agent?.agent || "this agent";
  if (!confirm(`Terminate ${label}? This closes the Herdr pane.`)) return;
  try {
    await api(`/api/agents/${encodeURIComponent(id)}/close`, {
      method: "POST",
      body: "{}",
    });
    if (state.sessionId === id) {
      stopPoll();
      setThinking(false);
      state.sessionId = null;
      go("herd");
    }
    await loadHerd();
  } catch (err) {
    toast(err.message);
  }
}

async function cancelTurn() {
  if (!state.sessionId) return;
  stopPoll();
  setThinking(false);
  note("Stop sent");
  renderChat(state.session || { messages: [] });
  try {
    await api(`/api/agents/${encodeURIComponent(state.sessionId)}/cancel`, {
      method: "POST",
      body: "{}",
    });
  } catch (err) {
    toast(err.message);
  }
  // Keep Stop visible until Herdr reports idle/blocked.
  let ticks = 0;
  state.pollTimer = setInterval(async () => {
    ticks += 1;
    await refreshSession();
    const status = state.session?.agent?.status;
    if (status !== "working" || ticks > 20) stopPoll();
  }, 400);
  refreshSession();
}

async function approve(id, action) {
  try {
    await api(`/api/agents/${encodeURIComponent(id)}/approve`, {
      method: "POST",
      body: JSON.stringify({ action }),
    });
    toast(action === "deny" ? "Denied" : "Sent");
    await loadHerd();
    if (state.screen === "session") await refreshSession();
  } catch (err) {
    toast(err.message);
  }
}

function openSheet() {
  $("#scrim").classList.add("on");
  $("#spawn-sheet").classList.add("open");
  const def = state.herd.default_agent || "codex";
  state.kind = def;
  $$("#spawn-sheet .pick").forEach((p) =>
    p.classList.toggle("on", p.dataset.kind === def)
  );
}
function closeSheet() {
  $("#scrim").classList.remove("on");
  $("#spawn-sheet").classList.remove("open");
}

async function spawn() {
  const cwd = $("#spawn-cwd").value.trim();
  const prompt = $("#spawn-prompt").value.trim();
  try {
    const created = await api("/api/spawn", {
      method: "POST",
      body: JSON.stringify({ cwd, kind: state.kind, prompt }),
    });
    closeSheet();
    toast(`Started ${created.kind}`);
    await loadHerd();
    if (created.id) openSession(created.id);
  } catch (err) {
    toast(err.message);
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function loadHerd() {
  try {
    state.herd = await api("/api/herd");
    applyHerdTheme(state.herd);
    renderHerd();
  } catch (err) {
    const disconnected = err.code === "NO_RANCH";
    $("#host-name").textContent = disconnected ? "no ranch" : "offline";
    $("#herd-meta").textContent = disconnected ? "not connected" : err.message;
    $("#herd-empty").hidden = false;
    $("#herd-empty").innerHTML = disconnected
      ? "Start the host from the Ranchr bar widget, then open the magic link on this phone."
      : `Can't reach Herdr.<br>Open a Herdr session on this PC, then refresh.<br><code>${escapeHtml(err.message)}</code>`;
  }
}

function wire() {
  $$(".filters .chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$(".filters .chip").forEach((c) => c.classList.remove("on"));
      btn.classList.add("on");
      state.filter = btn.dataset.filter;
      applyFilter();
    });
  });
  $("#inbox-btn").addEventListener("click", () => go("inbox"));
  $("#back-herd").addEventListener("click", () => go("herd"));
  $("#back-session").addEventListener("click", () => {
    stopPoll();
    setThinking(false);
    state.pendingUser = null;
    go("herd");
  });
  $$("#session .seg button").forEach((btn) => {
    btn.addEventListener("click", () => setSessionMode(btn.dataset.mode));
  });
  $("#send").addEventListener("click", sendPrompt);
  $("#send-now").addEventListener("click", sendPrompt);
  $("#working-stop").addEventListener("click", cancelTurn);
  $("#composer").addEventListener("input", () => {
    growComposer($("#composer"));
    if (state.chatStick && state.screen === "session") pinThread();
  });
  window.addEventListener("resize", () => {
    if (state.chatStick && state.screen === "session") pinThread();
  });
  $("#composer").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendPrompt();
    }
  });
  growComposer($("#composer"));
  $("#session-need").querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => approve(state.sessionId, btn.dataset.act));
  });
  $("#fab").addEventListener("click", openSheet);
  $("#scrim").addEventListener("click", closeSheet);
  $$("#spawn-sheet .pick").forEach((btn) => {
    btn.addEventListener("click", () => {
      $$("#spawn-sheet .pick").forEach((p) => p.classList.remove("on"));
      btn.classList.add("on");
      state.kind = btn.dataset.kind;
    });
  });
  $("#spawn-go").addEventListener("click", spawn);
  const thread = threadEl();
  thread.addEventListener(
    "scroll",
    () => {
      if (state.chatScrolling) return;
      state.chatStick = threadAtBottom(thread);
      updateJumpLatest();
    },
    { passive: true }
  );
  $("#jump-latest").addEventListener("click", () => pinThread());
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") pullRanchTheme();
  });
}

function growComposer(box) {
  if (!box) return;
  box.style.height = "auto";
  const cap = Math.round(window.innerHeight * 0.4);
  const next = Math.min(Math.max(box.scrollHeight, 44), cap);
  box.style.height = `${next}px`;
  box.style.overflowY = box.scrollHeight > cap ? "auto" : "hidden";
}

function live() {
  let src;
  try {
    src = new EventSource(apiUrl("/api/events"));
  } catch {
    return;
  }
  src.addEventListener("herd", (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.error) return;
      state.herd = data;
      applyHerdTheme(data);
      renderHerd();
      if (state.screen === "session") refreshSession();
    } catch {
      /* ignore */
    }
  });
  src.addEventListener("theme", (ev) => {
    try {
      const data = JSON.parse(ev.data);
      if (data.css && paintThemeCss(data.css)) {
        state.themeRev = data.rev || state.themeRev;
        state.themeSlug = data.theme || state.themeSlug;
        state.themeApplied = true;
      }
    } catch {
      /* ignore */
    }
  });
  src.onerror = () => {};
}

wire();
loadHerd().then(() => {
  const hash = location.hash.replace("#", "");
  if (hash.startsWith("session=")) openSession(decodeURIComponent(hash.slice(8)));
  if (hash === "inbox") go("inbox");
  if (hash === "spawn") openSheet();
});
live();
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("./sw.js").catch(() => {});
}
