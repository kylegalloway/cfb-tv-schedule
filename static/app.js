(() => {
  // Preference keys were renamed along with the project (it was
  // cfb-tv-schedule before it covered more than college football); fall
  // back to the old key so returning visitors keep their choice.
  function readPref(key, legacyKey) {
    return localStorage.getItem(key) ?? localStorage.getItem(legacyKey);
  }

  const THEME_KEY = "ota-sports-schedule-theme";
  const themeToggleInput = document.getElementById("theme-toggle-input");

  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    themeToggleInput.checked = theme === "dark";
  }

  applyTheme(readPref(THEME_KEY, "cfb-tv-schedule-theme") === "dark" ? "dark" : "light");

  themeToggleInput.addEventListener("change", () => {
    const next = themeToggleInput.checked ? "dark" : "light";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
  });

  // Every game arrives with an absolute `start_utc` (or just a `start_date`
  // when its time is TBD) — the server normalizes each source's own
  // wall-clock format. This picker shows them in the viewer's zone.
  // Broadcast weeks and TBD dates are anchored to US Eastern.
  const SOURCE_ZONE = "America/New_York";
  const TZ_KEY = "ota-sports-schedule-timezone";
  const timezoneSelect = document.getElementById("timezone-select");
  const timeColHeader = document.getElementById("time-col-header");

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

  // The game's start as a UTC epoch-ms instant, or null when unknown
  // (e.g. a "TBD" kickoff).
  function gameInstantMs(g) {
    return g.start_utc ? Date.parse(g.start_utc) : null;
  }

  // Sort/bucket key for every game, including ones without a known start
  // time: those sort at the end of their (Eastern) day.
  function gameSortMs(g) {
    const instant = gameInstantMs(g);
    if (instant !== null) return instant;
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(g.start_date || "");
    if (!m) return Infinity;
    return zonedWallClockToUTC(Number(m[1]), Number(m[2]), Number(m[3]), 23, 59, SOURCE_ZONE);
  }

  // Returns display strings for a game's date/time converted into the
  // currently selected zone. Falls back to the raw values (e.g. "TBD").
  function convertGameDateTime(g, zone) {
    const utcMs = gameInstantMs(g);
    if (utcMs === null) return { date: g.date, time: g.time };

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

  timezoneSelect.value = readPref(TZ_KEY, "cfb-tv-schedule-timezone") || "auto";
  updateTimeColumnHeader();

  timezoneSelect.addEventListener("change", () => {
    localStorage.setItem(TZ_KEY, timezoneSelect.value);
    updateTimeColumnHeader();
    render();
  });

  // Weeks are broadcast weeks shared by every league: Tuesday through
  // Monday (Eastern), which keeps a football week's Thursday-Saturday slate
  // and any Monday-nighter together. Key is the Tuesday's YYYY-MM-DD.
  const DAY_MS = 24 * 60 * 60 * 1000;

  function broadcastWeekKey(ms) {
    if (!Number.isFinite(ms)) return "";
    const wall = wallClockIn(new Date(ms), SOURCE_ZONE);
    const dayUtc = Date.UTC(wall.y, wall.m - 1, wall.d);
    const sinceTuesday = (new Date(dayUtc).getUTCDay() + 5) % 7;
    return new Date(dayUtc - sinceTuesday * DAY_MS).toISOString().slice(0, 10);
  }

  // leagueWeeks: e.g. ["CFB Week 7", "NFL Week 5"] for leagues that
  // number their weeks.
  function broadcastWeekLabel(key, leagueWeeks) {
    if (!key) return "Date TBD";
    const fmt = (ms) =>
      new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
    const start = Date.parse(key);
    const label = `${fmt(start)} – ${fmt(start + 6 * DAY_MS)}`;
    return leagueWeeks.length ? `${label} · ${leagueWeeks.join(" / ")}` : label;
  }

  let games = [];
  // OTA network -> St. Paul digital channel ("ABC" -> "5.1"), from the
  // server's station lineup (stations.py).
  let channels = {};
  let sortKey = "date";
  let sortDir = 1;

  const weekFilter = document.getElementById("week-filter");
  const leagueFilter = document.getElementById("league-filter");
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

  // Network dropdown ordering: OTA channels first, in channel order (2.1,
  // 4.1, 5.1, 5.2, ...), then the ESPN family + major streaming services,
  // then everything else (other markets' affiliates, regional sports
  // networks, etc). Exact-match sets, not prefixes — "ABC" is OTA here,
  // but "ABC 7" (another market's affiliate) is a different string and
  // correctly falls through to the last tier.
  // National broadcast networks, for the "National only" preset; a local
  // independent like 45TV is OTA but not national.
  const NATIONAL_BROADCAST = new Set(["ABC", "CBS", "NBC", "FOX", "The CW", "PBS", "ION", "MyNetworkTV"]);
  const NATIONAL_CABLE = new Set([
    "ESPN", "ESPN2", "ESPNU", "ESPN+", "ESPN network",
    "ACCN", "ACCNX", "SECN", "SECN+", "BTN", "FS1", "CBSSN",
    "Peacock", "Paramount+", "Disney+", "HBO Max", "USA", "YouTube", "TNT",
  ]);

  const TIER_OTA = 0;
  const TIER_NATIONAL_CABLE = 1;
  const TIER_OTHER = 2;

  function networkTier(name) {
    if (channels[name]) return TIER_OTA;
    if (NATIONAL_CABLE.has(name)) return TIER_NATIONAL_CABLE;
    return TIER_OTHER;
  }

  // "9.10" -> [9, 10], so it sorts after 9.2 (a subchannel number, not a
  // decimal fraction).
  function channelSortKey(channel) {
    const [major, minor = 0] = channel.split(".").map(Number);
    return [major, minor];
  }

  function compareNetworks(a, b) {
    const tierDiff = networkTier(a) - networkTier(b);
    if (tierDiff !== 0) return tierDiff;
    if (channels[a] && channels[b]) {
      const [aMajor, aMinor] = channelSortKey(channels[a]);
      const [bMajor, bMinor] = channelSortKey(channels[b]);
      return aMajor - bMajor || aMinor - bMinor;
    }
    return a.localeCompare(b);
  }

  // "ABC" -> "5.1 ABC"; non-OTA networks have no channel to show.
  function networkLabel(name) {
    return channels[name] ? `${channels[name]} ${name}` : name;
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

  function logoImg(url, teamName, league) {
    if (!url) return "";
    const leagueClass = league ? ` team-logo--${league.toLowerCase()}` : "";
    return `<img class="team-logo${leagueClass}" src="${url}" alt="${teamName} logo" loading="lazy" onerror="this.remove()" />`;
  }

  // A finished game's score, bold for the winner. Upcoming and canceled
  // games have no scores.
  function scoreHTML(score, otherScore) {
    if (score == null) return "";
    const won = otherScore != null && score > otherScore;
    return ` <span class="score${won ? " score--won" : ""}">${score}</span>`;
  }

  function matchupHTML(g) {
    const away = (g.away_rank ? `#${g.away_rank} ` : "") + g.away_team;
    const home = (g.home_rank ? `#${g.home_rank} ` : "") + g.home_team;
    return (
      `${logoImg(g.away_logo, g.away_team, g.league)}` +
      `<span class="team-name">${away}</span>${scoreHTML(g.away_score, g.home_score)} ${g.separator} ` +
      `<span class="team-name">${home}</span>${scoreHTML(g.home_score, g.away_score)}` +
      `${logoImg(g.home_logo, g.home_team, g.league)}` +
      (g.status ? ` <span class="game-status">${g.status}</span>` : "")
    );
  }

  function leagueText(g) {
    return g.week_label ? `${g.league} · ${g.week_label}` : g.league;
  }

  function getFilteredGames() {
    const week = weekFilter.value;
    const league = leagueFilter.value;
    const search = teamSearch.value.trim().toLowerCase();
    const checkedNetworks = new Set(
      Array.from(networkCheckboxes.querySelectorAll("input:checked")).map((el) => el.value)
    );

    return games.filter((g) => {
      if (week && g._week !== week) return false;
      if (league && g.league !== league) return false;
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
      if (sortKey === "date") {
        av = a._sortMs;
        bv = b._sortMs;
      } else if (sortKey === "league") {
        av = leagueText(a);
        bv = leagueText(b);
      } else if (sortKey === "time") {
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
      return a._sortMs - b._sortMs || a.order_index - b.order_index;
    });

    tbody.innerHTML = "";
    for (const g of rows) {
      const { date, time } = convertGameDateTime(g, zone);
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${leagueText(g)}</td>
        <td>${date}</td>
        <td>${time}</td>
        <td class="matchup-cell">${matchupHTML(g)}</td>
        <td>${g.networks.map(networkLabel).join(" / ")}</td>
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

    // Group by (converted) date, in chronological order.
    const byDate = new Map();
    const displayCache = new Map();
    for (const g of rows.slice().sort((a, b) => a._sortMs - b._sortMs || a.order_index - b.order_index)) {
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
        let rowHtml = `<th class="guide-channel">${networkLabel(n)}</th>`;
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
  // broadcast week whose games aren't fully over yet (i.e. its last start,
  // plus a game-length buffer, hasn't passed), so a trailing Monday-nighter
  // or a Tuesday-morning page load still advances to the next week once the
  // previous week's games have wrapped up. Falls back to the most recent
  // week once the whole season's data is in the past.
  function computeCurrentWeek() {
    const weekBounds = new Map();
    for (const g of games) {
      const utcMs = gameInstantMs(g);
      if (utcMs === null) continue;
      const bounds = weekBounds.get(g._week);
      if (!bounds) {
        weekBounds.set(g._week, { start: utcMs, end: utcMs });
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
    const leagueWeeksByKey = new Map();
    for (const g of games) {
      if (!leagueWeeksByKey.has(g._week)) leagueWeeksByKey.set(g._week, []);
      const leagueWeek = g.week_label ? leagueText(g).replace(" · ", " ") : null;
      if (leagueWeek && !leagueWeeksByKey.get(g._week).includes(leagueWeek)) {
        leagueWeeksByKey.get(g._week).push(leagueWeek);
      }
    }
    // "" (undated games) sorts first as a string; keep it last instead.
    const weeks = [...leagueWeeksByKey.keys()].sort((a, b) => (a === "") - (b === "") || a.localeCompare(b));
    weekFilter.innerHTML = '<option value="">All weeks</option>';
    for (const w of weeks) {
      const opt = document.createElement("option");
      opt.value = w;
      opt.textContent = broadcastWeekLabel(w, leagueWeeksByKey.get(w));
      weekFilter.appendChild(opt);
    }
    if (isFirstLoad) {
      const currentWeek = computeCurrentWeek();
      if (currentWeek && weeks.includes(currentWeek)) weekFilter.value = currentWeek;
      weekFilter.dataset.initialized = "1";
    } else if (weeks.includes(previousValue)) {
      weekFilter.value = previousValue;
    }

    const previousLeague = leagueFilter.value;
    const leagues = [...new Set(games.map((g) => g.league))].sort();
    leagueFilter.innerHTML = '<option value="">All leagues</option>';
    for (const l of leagues) {
      const opt = document.createElement("option");
      opt.value = l;
      opt.textContent = l;
      leagueFilter.appendChild(opt);
    }
    if (leagues.includes(previousLeague)) leagueFilter.value = previousLeague;

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
      label.innerHTML = `<input type="checkbox" value="${n}" /> ${networkLabel(n)}`;
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
    channels = data.channels || {};
    games = (data.games || []).map((g) => {
      const game = { ...g };
      game._sortMs = gameSortMs(game);
      game._week = broadcastWeekKey(game._sortMs);
      return game;
    });
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
  leagueFilter.addEventListener("change", render);
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
    // "National" = national broadcast networks + ESPN family/streaming;
    // excludes local independents (45TV) and everything else (regional
    // sports networks, etc).
    networkCheckboxes.querySelectorAll("input").forEach((b) => {
      b.checked = NATIONAL_BROADCAST.has(b.value) || networkTier(b.value) === TIER_NATIONAL_CABLE;
    });
    updateNetworkSummary();
    render();
  });

  function selectOta() {
    // OTA (over-the-air) = anything with a St. Paul channel number.
    networkCheckboxes.querySelectorAll("input").forEach((b) => {
      b.checked = networkTier(b.value) === TIER_OTA;
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
