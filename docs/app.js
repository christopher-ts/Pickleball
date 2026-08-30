const DATA_URL = "sessions.json";

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

function uniqueValues(sessions, key) {
  const values = new Set();
  for (const s of sessions) {
    if (s[key]) values.add(s[key]);
  }
  return ["All", ...Array.from(values).sort()];
}

function renderFilters() {
  const container = document.getElementById("filters");
  container.innerHTML = "";

  const days = uniqueValues(state.sessions, "day");
  const locations = uniqueValues(state.sessions, "location");

  const makeChip = (label, active, onClick) => {
    const btn = document.createElement("button");
    btn.className = "chip";
    btn.textContent = label;
    btn.setAttribute("aria-pressed", String(active));
    btn.addEventListener("click", onClick);
    return btn;
  };

  days.forEach((day) => {
    container.appendChild(
      makeChip(day, state.dayFilter === day, () => {
        state.dayFilter = day;
        render();
      })
    );
  });

  if (locations.length > 1) {
    const divider = document.createElement("span");
    divider.style.width = "100%";
    divider.style.height = "0";
    container.appendChild(divider);
    locations.forEach((loc) => {
      container.appendChild(
        makeChip(loc, state.locationFilter === loc, () => {
          state.locationFilter = loc;
          render();
        })
      );
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

  for (const [day, items] of groups) {
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
