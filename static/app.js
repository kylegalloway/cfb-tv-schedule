(() => {
  const THEME_KEY = "cfb-tv-schedule-theme";
  const themeToggleInput = document.getElementById("theme-toggle-input");

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    themeToggleInput.checked = theme === "dark";
  }

  applyTheme(localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light");

  themeToggleInput.addEventListener("change", () => {
    const next = themeToggleInput.checked ? "dark" : "light";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  });

  // Scraped times are wall-clock US Eastern. This picker lets the viewer
  // see them converted to their own zone; conversion is DST-aware (uses
  // the actual offset for each game's date, not a fixed ET/CT-style delta).
  const SOURCE_ZONE = "America/New_York";
  const TZ_KEY = "cfb-tv-schedule-timezone";
  const timezoneSelect = document.getElementById("timezone-select");
  const timeColHeader = document.getElementById("time-col-header");
  let scheduleYear = new Date().getFullYear();

  function resolveZone() {
    if (timezoneSelect.value === "auto") {
      try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || SOURCE_ZONE;
      } catch {
        return SOURCE_ZONE;
      }
    }
    return timezoneSelect.value;
  }

  function zoneAbbrev(zone, atDate) {
    try {
      const parts = new Intl.DateTimeFormat("en-US", {
        timeZone: zone,
        timeZoneName: "short",
      }).formatToParts(atDate);
      return parts.find((p) => p.type === "timeZoneName")?.value || zone;
    } catch {
      return zone;
    }
  }

  // Wall-clock time in `zone` for the UTC instant `date`, as {y,m,d,h,min}.
  function wallClockIn(date, zone) {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: zone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }).formatToParts(date);
    const map = {};
    for (const p of parts) map[p.type] = p.value;
    return {
      y: Number(map.year),
      m: Number(map.month),
      d: Number(map.day),
      h: Number(map.hour),
      min: Number(map.minute),
    };
  }

  // Find the UTC instant whose wall-clock time in `zone` matches
  // y/m/d/h/min. Handles EDT/EST (and any other zone's DST) correctly.
  function zonedWallClockToUTC(y, m, d, h, min, zone) {
    const target = Date.UTC(y, m - 1, d, h, min);
    let guess = target;
    for (let i = 0; i < 2; i++) {
      const wall = wallClockIn(new Date(guess), zone);
      const wallAsUTC = Date.UTC(wall.y, wall.m - 1, wall.d, wall.h, wall.min);
      guess -= wallAsUTC - target;
    }
    return guess;
  }

  const MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  ];

  function parseGameDateTime(g) {
    // date: "Thursday, August 27"; time: "6:00pm" or "TBD"/"" etc.
    const dateMatch = /,\s*([A-Za-z]+)\s+(\d{1,2})\s*$/.exec((g.date || "").trim());
    const timeMatch = /^(\d{1,2}):(\d{2})\s*(am|pm)$/i.exec((g.time || "").trim());
    if (!dateMatch || !timeMatch) return null;
    const month = MONTHS.indexOf(dateMatch[1]);
    if (month === -1) return null;
    const day = parseInt(dateMatch[2], 10);
    let hours = parseInt(timeMatch[1], 10) % 12;
    if (timeMatch[3].toLowerCase() === "pm") hours += 12;
    const minutes = parseInt(timeMatch[2], 10);
    return { month, day, hours, minutes };
  }

  // Returns display strings for a game's date/time converted into the
  // currently selected zone. Falls back to the raw values (e.g. "TBD").
  function convertGameDateTime(g, zone) {
    const parsed = parseGameDateTime(g);
    if (!parsed) return { date: g.date, time: g.time };

    const utcMs = zonedWallClockToUTC(
      scheduleYear, parsed.month + 1, parsed.day, parsed.hours, parsed.minutes, SOURCE_ZONE
    );
    const wall = wallClockIn(new Date(utcMs), zone);
    const weekday = new Intl.DateTimeFormat("en-US", { timeZone: zone, weekday: "long" })
      .format(new Date(utcMs));

    let displayHours = wall.h % 12;
    if (displayHours === 0) displayHours = 12;
    const ampm = wall.h < 12 ? "am" : "pm";
    const time = `${displayHours}:${String(wall.min).padStart(2, "0")}${ampm}`;
    const date = `${weekday}, ${MONTHS[wall.m - 1]} ${wall.d}`;
    return { date, time };
  }

  function updateTimeColumnHeader() {
    const zone = resolveZone();
    timeColHeader.textContent = `Time (${zoneAbbrev(zone, new Date())})`;
  }

  timezoneSelect.value = localStorage.getItem(TZ_KEY) || "auto";
  updateTimeColumnHeader();

  timezoneSelect.addEventListener("change", () => {
    localStorage.setItem(TZ_KEY, timezoneSelect.value);
    updateTimeColumnHeader();
    render();
  });

  let games = [];
  let sortKey = "order_index";
  let sortDir = 1;

  const weekFilter = document.getElementById("week-filter");
  const teamSearch = document.getElementById("team-search");
  const networkCheckboxes = document.getElementById("network-checkboxes");
  const networkDropdownBtn = document.getElementById("network-dropdown-btn");
  const networkDropdownPanel = document.getElementById("network-dropdown-panel");
  const networkSummary = document.getElementById("network-summary");
  const networkSelectAll = document.getElementById("network-select-all");
  const networkSelectNone = document.getElementById("network-select-none");
  const networkSelectNational = document.getElementById("network-select-national");
  const networkSelectOta = document.getElementById("network-select-ota");
  const tbody = document.getElementById("games-body");
  const updatedAt = document.getElementById("updated-at");
  const refreshBtn = document.getElementById("refresh-btn");
  const emptyState = document.getElementById("empty-state");
  const degradedBanner = document.getElementById("degraded-banner");
  const viewListBtn = document.getElementById("view-list-btn");
  const viewGuideBtn = document.getElementById("view-guide-btn");
  const listView = document.getElementById("list-view");
  const guideView = document.getElementById("guide-view");
  const guideHint = document.getElementById("guide-hint");
  const guideDays = document.getElementById("guide-days");

  let viewMode = "list";

  // Network dropdown ordering: major broadcast networks first, then the
  // ESPN family + major streaming services, then everything else (local
  // affiliates, regional sports networks, etc). Exact-match sets, not
  // prefixes — "ABC" belongs in tier 1, but "ABC 7" (a local affiliate) is
  // a different string and correctly falls through to tier 3.
  const NETWORK_TIER_1 = new Set(["ABC", "CBS", "NBC", "FOX", "The CW"]);
  const NETWORK_TIER_2 = new Set([
    "ESPN", "ESPN2", "ESPNU", "ESPN+", "ESPN network",
    "ACCN", "ACCNX", "SECN", "SECN+", "BTN", "FS1", "CBSSN",
    "Peacock", "Paramount+", "Disney+", "HBO Max", "USA", "YouTube", "TNT",
  ]);

  function networkTier(name) {
    if (NETWORK_TIER_1.has(name)) return 0;
    if (NETWORK_TIER_2.has(name)) return 1;
    return 2;
  }

  function compareNetworks(a, b) {
    const tierDiff = networkTier(a) - networkTier(b);
    return tierDiff !== 0 ? tierDiff : a.localeCompare(b);
  }

  function timeToMinutes(t) {
    // "8:00pm" / "12:30pm" / "TBD" -> sortable minutes, TBD-ish text sorts last
    const m = /^(\d{1,2}):(\d{2})\s*(am|pm)$/i.exec((t || "").trim());
    if (!m) return 24 * 60 + 1;
    let hours = parseInt(m[1], 10) % 12;
    if (m[3].toLowerCase() === "pm") hours += 12;
    return hours * 60 + parseInt(m[2], 10);
  }

  function matchupText(g) {
    const away = (g.away_rank ? `#${g.away_rank} ` : "") + g.away_team;
    const home = (g.home_rank ? `#${g.home_rank} ` : "") + g.home_team;
    return `${away} ${g.separator} ${home}`;
  }

  function logoImg(url, teamName) {
    if (!url) return "";
    return `<img class="team-logo" src="${url}" alt="${teamName} logo" loading="lazy" onerror="this.remove()" />`;
  }

  function matchupHTML(g) {
    const away = (g.away_rank ? `#${g.away_rank} ` : "") + g.away_team;
    const home = (g.home_rank ? `#${g.home_rank} ` : "") + g.home_team;
    return (
      `${logoImg(g.away_logo, g.away_team)}` +
      `<span class="team-name">${away}</span> ${g.separator} <span class="team-name">${home}</span>` +
      `${logoImg(g.home_logo, g.home_team)}`
    );
  }

  function getFilteredGames() {
    const week = weekFilter.value;
    const search = teamSearch.value.trim().toLowerCase();
    const checkedNetworks = new Set(
      Array.from(networkCheckboxes.querySelectorAll("input:checked")).map((el) => el.value)
    );

    return games.filter((g) => {
      if (week && g.week_label !== week) return false;
      if (!g.networks.some((n) => checkedNetworks.has(n))) return false;
      if (search) {
        const haystack = `${g.away_team} ${g.home_team}`.toLowerCase();
        if (!haystack.includes(search)) return false;
      }
      return true;
    });
  }

  function render() {
    if (viewMode === "guide") {
      renderGuide();
    } else {
      renderList();
    }
  }

  function renderList() {
    let rows = getFilteredGames();
    const zone = resolveZone();

    rows = rows.slice().sort((a, b) => {
      let av, bv;
      if (sortKey === "time") {
        av = timeToMinutes(convertGameDateTime(a, zone).time);
        bv = timeToMinutes(convertGameDateTime(b, zone).time);
      } else if (sortKey === "matchup") {
        av = matchupText(a);
        bv = matchupText(b);
      } else {
        av = a[sortKey];
        bv = b[sortKey];
      }
      if (av < bv) return -1 * sortDir;
      if (av > bv) return 1 * sortDir;
      return a.order_index - b.order_index;
    });

    tbody.innerHTML = "";
    for (const g of rows) {
      const { date, time } = convertGameDateTime(g, zone);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${g.week_label}</td>
        <td>${date}</td>
        <td>${time}</td>
        <td class="matchup-cell">${matchupHTML(g)}</td>
        <td>${g.network}</td>
      `;
      tbody.appendChild(tr);
    }

    emptyState.classList.toggle("hidden", rows.length > 0);
  }

  function renderGuide() {
    const rows = getFilteredGames();
    const zone = resolveZone();
    guideDays.innerHTML = "";

    if (!weekFilter.value) {
      guideHint.classList.remove("hidden");
      return;
    }
    guideHint.classList.add("hidden");

    // Group by (converted) date, preserving the order dates first appear in
    // (already chronological, since `games` comes off the wire in scrape order).
    const byDate = new Map();
    const displayCache = new Map();
    for (const g of rows) {
      const display = convertGameDateTime(g, zone);
      displayCache.set(g, display);
      if (!byDate.has(display.date)) byDate.set(display.date, []);
      byDate.get(display.date).push(g);
    }

    for (const [date, dayGames] of byDate) {
      const times = [...new Set(dayGames.map((g) => displayCache.get(g).time))].sort(
        (a, b) => timeToMinutes(a) - timeToMinutes(b)
      );
      const networksToday = [...new Set(dayGames.flatMap((g) => g.networks))].sort(compareNetworks);

      // cell[network][time] -> games in that slot
      const cell = new Map();
      for (const g of dayGames) {
        const time = displayCache.get(g).time;
        for (const n of g.networks) {
          const key = `${n} ${time}`;
          if (!cell.has(key)) cell.set(key, []);
          cell.get(key).push(g);
        }
      }

      const table = document.createElement("table");
      table.className = "guide-table";

      const thead = document.createElement("thead");
      const headRow = document.createElement("tr");
      headRow.innerHTML = `<th class="guide-channel-head">Network</th>` + times.map((t) => `<th>${t}</th>`).join("");
      thead.appendChild(headRow);
      table.appendChild(thead);

      const guideBody = document.createElement("tbody");
      for (const n of networksToday) {
        const tr = document.createElement("tr");
        let rowHtml = `<th class="guide-channel">${n}</th>`;
        for (const t of times) {
          const slotGames = cell.get(`${n} ${t}`) || [];
          rowHtml += `<td>${slotGames.map((g) => `<div class="guide-game">${matchupHTML(g)}</div>`).join("")}</td>`;
        }
        tr.innerHTML = rowHtml;
        guideBody.appendChild(tr);
      }
      table.appendChild(guideBody);

      const heading = document.createElement("h3");
      heading.className = "guide-date-heading";
      heading.textContent = date;

      const wrap = document.createElement("div");
      wrap.className = "guide-table-wrap";
      wrap.appendChild(table);

      guideDays.appendChild(heading);
      guideDays.appendChild(wrap);
    }

    if (byDate.size === 0) {
      const p = document.createElement("p");
      p.className = "hint";
      p.textContent = "No games match the current filters.";
      guideDays.appendChild(p);
    }
  }

  // A week isn't "over" the instant its last game kicks off — give it time
  // to actually finish. Games don't carry a known end time, so this is a
  // typical-length guess rather than something derived from real data.
  const GAME_DURATION_MS = 4 * 60 * 60 * 1000;

  // Picks the week whose games are "current": the chronologically-earliest
  // week whose games aren't fully over yet (i.e. its last kickoff, plus a
  // game-length buffer, hasn't passed), so a trailing Monday-nighter or a
  // Tuesday-morning page load still advances to the next week once the
  // previous week's games have wrapped up. Falls back to the most recent
  // week once the whole season's data is in the past.
  function computeCurrentWeek() {
    const weekBounds = new Map();
    for (const g of games) {
      const parsed = parseGameDateTime(g);
      if (!parsed) continue;
      const utcMs = zonedWallClockToUTC(
        scheduleYear, parsed.month + 1, parsed.day, parsed.hours, parsed.minutes, SOURCE_ZONE
      );
      const bounds = weekBounds.get(g.week_label);
      if (!bounds) {
        weekBounds.set(g.week_label, { start: utcMs, end: utcMs });
      } else {
        if (utcMs < bounds.start) bounds.start = utcMs;
        if (utcMs > bounds.end) bounds.end = utcMs;
      }
    }
    const now = Date.now();
    let current = null;
    let currentStart = Infinity;
    let mostRecent = null;
    let mostRecentEnd = -Infinity;
    for (const [week, bounds] of weekBounds) {
      if (now < bounds.end + GAME_DURATION_MS && bounds.start < currentStart) {
        current = week;
        currentStart = bounds.start;
      }
      if (bounds.end > mostRecentEnd) {
        mostRecentEnd = bounds.end;
        mostRecent = week;
      }
    }
    return current || mostRecent;
  }

  function populateFilters() {
    const previousValue = weekFilter.value;
    const isFirstLoad = !weekFilter.dataset.initialized;
    const weeks = [...new Set(games.map((g) => g.week_label))];
    weekFilter.innerHTML = '<option value="">All weeks</option>';
    for (const w of weeks) {
      const opt = document.createElement("option");
      opt.value = w;
      opt.textContent = w;
      weekFilter.appendChild(opt);
    }
    if (isFirstLoad) {
      const currentWeek = computeCurrentWeek();
      if (currentWeek && weeks.includes(currentWeek)) weekFilter.value = currentWeek;
      weekFilter.dataset.initialized = "1";
    } else if (weeks.includes(previousValue)) {
      weekFilter.value = previousValue;
    }

    const networkSet = new Set();
    for (const g of games) {
      for (const n of g.networks) networkSet.add(n);
    }
    const allNetworks = [...networkSet].sort(compareNetworks);
    networkCheckboxes.innerHTML = "";
    let prevTier = null;
    for (const n of allNetworks) {
      const tier = networkTier(n);
      if (prevTier !== null && tier !== prevTier) {
        networkCheckboxes.appendChild(document.createElement("hr"));
      }
      prevTier = tier;

      const label = document.createElement("label");
      label.className = "network-option";
      label.innerHTML = `<input type="checkbox" value="${n}" /> ${n}`;
      networkCheckboxes.appendChild(label);
    }
    selectOta();
  }

  function updateNetworkSummary() {
    const boxes = Array.from(networkCheckboxes.querySelectorAll("input"));
    const checked = boxes.filter((b) => b.checked).length;
    if (checked === boxes.length) {
      networkSummary.textContent = "(all)";
    } else if (checked === 0) {
      networkSummary.textContent = "(none)";
    } else {
      networkSummary.textContent = `(${checked} selected)`;
    }
  }

  function setData(data) {
    games = data.games || [];
    if (data.scraped_at) scheduleYear = new Date(data.scraped_at).getUTCFullYear();
    updatedAt.textContent = data.scraped_at
      ? `Last updated: ${new Date(data.scraped_at).toLocaleString()}`
      : "No data yet";
    degradedBanner.classList.toggle("hidden", !data.degraded);
    populateFilters();
    render();
  }

  async function loadGames() {
    const resp = await fetch("/api/games");
    setData(await resp.json());
  }

  async function refresh() {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "Refreshing…";
    // The primary source is usually fast, but when it's blocked the server
    // falls back to driving a real browser to get past it, which can take
    // a couple of minutes — let the user know this isn't stuck.
    const slowNoticeTimer = setTimeout(() => {
      refreshBtn.textContent = "Still refreshing… (primary source is blocked, retrying with a slower method — can take a couple minutes)";
    }, 8000);
    try {
      const resp = await fetch("/api/refresh", { method: "POST" });
      setData(await resp.json());
    } finally {
      clearTimeout(slowNoticeTimer);
      refreshBtn.disabled = false;
      refreshBtn.textContent = "Refresh now";
    }
  }

  document.querySelectorAll("th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (sortKey === key) {
        sortDir *= -1;
      } else {
        sortKey = key;
        sortDir = 1;
      }
      render();
    });
  });

  weekFilter.addEventListener("change", render);
  teamSearch.addEventListener("input", render);
  networkCheckboxes.addEventListener("change", () => {
    updateNetworkSummary();
    render();
  });

  networkDropdownBtn.addEventListener("click", () => {
    networkDropdownPanel.classList.toggle("hidden");
  });

  document.addEventListener("click", (e) => {
    if (!document.getElementById("network-filter").contains(e.target)) {
      networkDropdownPanel.classList.add("hidden");
    }
  });

  networkSelectAll.addEventListener("click", () => {
    networkCheckboxes.querySelectorAll("input").forEach((b) => (b.checked = true));
    updateNetworkSummary();
    render();
  });

  networkSelectNone.addEventListener("click", () => {
    networkCheckboxes.querySelectorAll("input").forEach((b) => (b.checked = false));
    updateNetworkSummary();
    render();
  });

  networkSelectNational.addEventListener("click", () => {
    // "National" = tiers 0/1 (major broadcast + ESPN family/streaming),
    // excludes tier 2 (regional sports networks, local affiliates, etc).
    networkCheckboxes.querySelectorAll("input").forEach((b) => {
      b.checked = networkTier(b.value) < 2;
    });
    updateNetworkSummary();
    render();
  });

  function selectOta() {
    // OTA (over-the-air) = tier 0 only: ABC, CBS, NBC, FOX, The CW.
    networkCheckboxes.querySelectorAll("input").forEach((b) => {
      b.checked = networkTier(b.value) === 0;
    });
    updateNetworkSummary();
  }

  networkSelectOta.addEventListener("click", () => {
    selectOta();
    render();
  });

  refreshBtn.addEventListener("click", refresh);

  function setViewMode(mode) {
    viewMode = mode;
    viewListBtn.classList.toggle("active", mode === "list");
    viewGuideBtn.classList.toggle("active", mode === "guide");
    listView.classList.toggle("hidden", mode !== "list");
    guideView.classList.toggle("hidden", mode !== "guide");
    render();
  }

  viewListBtn.addEventListener("click", () => setViewMode("list"));
  viewGuideBtn.addEventListener("click", () => setViewMode("guide"));

  loadGames();
})();
