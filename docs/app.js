const DATA_URL = "sessions.json";

const WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const state = {
  sessions: [],
  dayFilter: "All",
  locationFilter: "All",
};

function statusClass(status) {
  const s = (status || "").toLowerCase();
  if (s.includes("open") || s.includes("available")) return "status-open";
  if (s.includes("wait")) return "status-waitlist";
  if (s.includes("full") || s.includes("closed")) return "status-full";
  return "status-unknown";
}

function sortByWeekday(values) {
  return values.sort((a, b) => {
    const ai = WEEKDAY_ORDER.indexOf(a);
    const bi = WEEKDAY_ORDER.indexOf(b);
    if (ai === -1 && bi === -1) return a.localeCompare(b);
    if (ai === -1) return 1;
    if (bi === -1) return -1;
    return ai - bi;
  });
}

function uniqueValues(sessions, key, sorter = (vals) => vals.sort()) {
  const values = new Set();
  for (const s of sessions) {
    if (s[key]) values.add(s[key]);
  }
  return sorter(Array.from(values));
}

function renderFilterGroup(container, label, options, activeValue, onSelect) {
  if (options.length === 0) return;

  const group = document.createElement("div");
  group.className = "filter-group";

  const heading = document.createElement("div");
  heading.className = "filter-label";
  heading.textContent = label;
  group.appendChild(heading);

  const row = document.createElement("div");
  row.className = "chip-row";
  ["All", ...options].forEach((value) => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.textContent = value;
    btn.setAttribute("aria-pressed", String(activeValue === value));
    btn.addEventListener("click", () => onSelect(value));
    row.appendChild(btn);
  });
  group.appendChild(row);

  container.appendChild(group);
}

function renderFilters() {
  const container = document.getElementById("filters");
  container.innerHTML = "";

  const days = uniqueValues(state.sessions, "day", sortByWeekday);
  const locations = uniqueValues(state.sessions, "location");

  renderFilterGroup(container, "Day", days, state.dayFilter, (value) => {
    state.dayFilter = value;
    render();
  });

  if (locations.length > 1) {
    renderFilterGroup(container, "Location", locations, state.locationFilter, (value) => {
      state.locationFilter = value;
      render();
    });
  }
}

function filteredSessions() {
  return state.sessions.filter((s) => {
    const dayOk = state.dayFilter === "All" || s.day === state.dayFilter;
    const locOk = state.locationFilter === "All" || s.location === state.locationFilter;
    return dayOk && locOk;
  });
}

function renderResults() {
  const container = document.getElementById("results");
  container.innerHTML = "";

  const sessions = filteredSessions();
  if (sessions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No sessions match right now.";
    container.appendChild(empty);
    return;
  }

  const groups = new Map();
  for (const s of sessions) {
    const key = s.day || "Unscheduled";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
  }
  const orderedDays = sortByWeekday(Array.from(groups.keys()));

  for (const day of orderedDays) {
    const items = groups.get(day);
    const group = document.createElement("section");
    group.className = "day-group";

    const heading = document.createElement("h2");
    heading.textContent = day;
    group.appendChild(heading);

    for (const session of items) {
      const card = document.createElement("a");
      card.className = "session-card";
      card.href = session.register_url || "#";
      if (session.register_url) card.target = "_blank";

      const top = document.createElement("div");
      top.className = "session-top";

      const name = document.createElement("div");
      name.className = "session-name";
      name.textContent = session.name || "Pickleball session";
      top.appendChild(name);

      const badge = document.createElement("span");
      badge.className = `status-badge ${statusClass(session.status)}`;
      badge.textContent = session.status || "Unknown";
      top.appendChild(badge);

      card.appendChild(top);

      const meta = document.createElement("div");
      meta.className = "session-meta";
      const metaParts = [session.time, session.location, session.price].filter(Boolean);
      meta.textContent = metaParts.join(" · ");
      card.appendChild(meta);

      group.appendChild(card);
    }

    container.appendChild(group);
  }
}

function render() {
  renderFilters();
  renderResults();
}

async function load() {
  try {
    const res = await fetch(`${DATA_URL}?t=${Date.now()}`);
    const data = await res.json();
    state.sessions = data.sessions || [];

    const updatedEl = document.getElementById("updated-at");
    if (data.scraped_at) {
      const date = new Date(data.scraped_at);
      updatedEl.textContent = `Updated ${date.toLocaleString()}`;
    }
    render();
  } catch (err) {
    document.getElementById("results").innerHTML =
      '<div class="empty-state">Could not load session data.</div>';
    console.error(err);
  }
}

load();
