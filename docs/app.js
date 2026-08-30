const DATA_URL = "sessions.json";
const DAY_FILTER_STORAGE_KEY = "sm-pickleball-day-filter";

const WEEKDAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function loadStoredDayFilters() {
  try {
    const raw = localStorage.getItem(DAY_FILTER_STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function saveStoredDayFilters(days) {
  try {
    localStorage.setItem(DAY_FILTER_STORAGE_KEY, JSON.stringify([...days]));
  } catch {
    // ignore (private browsing, storage disabled, etc.)
  }
}

const state = {
  sessions: [],
  dayFilters: loadStoredDayFilters(),
  locationFilter: "All",
};

// The badge is the primary signal on each card, so it leads with capacity
// (how many spots are actually open right now) rather than a flat
// Open/Full word -- with "Full" reserved for literally zero spots left,
// never a redundant "104/104".
function badgeInfo(session) {
  const status = (session.status || "").toLowerCase();
  const { spots_left, spots_total } = session;

  if (status.includes("wait")) {
    return { text: "Waitlist", className: "status-waitlist" };
  }
  if (status === "full" || spots_left === 0) {
    return { text: "Full", className: "status-full" };
  }
  if (spots_left != null) {
    const remainingRatio = spots_total ? spots_left / spots_total : null;
    const label = `${spots_left} spot${spots_left === 1 ? "" : "s"} open`;
    if (remainingRatio != null && remainingRatio <= 0.15) {
      return { text: label, className: "status-limited" };
    }
    return { text: label, className: "status-open" };
  }
  return { text: session.status || "Unknown", className: "status-unknown" };
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

function makeChip(label, active, onClick) {
  const btn = document.createElement("button");
  btn.className = "chip";
  btn.textContent = label;
  btn.setAttribute("aria-pressed", String(active));
  btn.addEventListener("click", onClick);
  return btn;
}

// Multi-select: any number of days can be picked at once (e.g. "I'm free
// Mon and Thu, show me just those"). Empty selection means show every day.
function renderDayFilter(container, days) {
  if (days.length === 0) return;

  const group = document.createElement("div");
  group.className = "filter-group";

  const heading = document.createElement("div");
  heading.className = "filter-label";
  heading.textContent = "Day";
  group.appendChild(heading);

  const row = document.createElement("div");
  row.className = "chip-row";

  row.appendChild(
    makeChip("All", state.dayFilters.size === 0, () => {
      state.dayFilters.clear();
      saveStoredDayFilters(state.dayFilters);
      render();
    })
  );

  days.forEach((day) => {
    row.appendChild(
      makeChip(day, state.dayFilters.has(day), () => {
        if (state.dayFilters.has(day)) {
          state.dayFilters.delete(day);
        } else {
          state.dayFilters.add(day);
        }
        saveStoredDayFilters(state.dayFilters);
        render();
      })
    );
  });

  group.appendChild(row);
  container.appendChild(group);
}

// Single-select: only one location makes sense to view at a time.
function renderLocationFilter(container, locations) {
  if (locations.length <= 1) return;

  const group = document.createElement("div");
  group.className = "filter-group";

  const heading = document.createElement("div");
  heading.className = "filter-label";
  heading.textContent = "Location";
  group.appendChild(heading);

  const row = document.createElement("div");
  row.className = "chip-row";
  ["All", ...locations].forEach((value) => {
    row.appendChild(
      makeChip(value, state.locationFilter === value, () => {
        state.locationFilter = value;
        render();
      })
    );
  });
  group.appendChild(row);

  container.appendChild(group);
}

function renderFilters() {
  const container = document.getElementById("filters");
  container.innerHTML = "";

  const days = uniqueValues(state.sessions, "day", sortByWeekday);
  const locations = uniqueValues(state.sessions, "location");

  renderDayFilter(container, days);
  renderLocationFilter(container, locations);
}

function filteredSessions() {
  return state.sessions.filter((s) => {
    const dayOk = state.dayFilters.size === 0 || state.dayFilters.has(s.day);
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

      const info = badgeInfo(session);
      const badge = document.createElement("span");
      badge.className = `status-badge ${info.className}`;
      badge.textContent = info.text;
      top.appendChild(badge);

      card.appendChild(top);

      const meta = document.createElement("div");
      meta.className = "session-meta";
      const metaParts = [session.time, session.location].filter(Boolean);
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
