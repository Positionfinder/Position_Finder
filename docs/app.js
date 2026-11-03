(() => {
  const $ = (s) => document.querySelector(s);
  const COUNTRY = { ES: "Spain", DE: "Germany" };
  const state = { country: "all", level: "all", topics: new Set(), q: "", region: "", sort: "match", matchf: "any", calls: false };
  let DATA = { items: [], sources: [], profiles: [], threshold: 60 };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const daysTo = (iso) => Math.round((new Date(iso + "T00:00:00") - today) / 86400000);
  const fmt = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
  const levelLabel = (l) => ({ postdoc: "Postdoc", research: "Researcher (level not stated)" }[l] || "Postdoc");
  const m = (it, pid) => (it.match ? it.match[pid] ?? 0 : null);
  const best = (it) => (it.match ? Math.max(...Object.values(it.match)) : -1);

  function matches(it) {
    const T = DATA.threshold;
    if (it.kind === "call") { if (!state.calls) return false; }
    else if (state.matchf === "any" && best(it) < T) return false;
    else if (state.matchf.startsWith("p:") && m(it, state.matchf.slice(2)) < T) return false;
    if (state.country !== "all" && (it.country || "ES") !== state.country) return false;
    if (state.level !== "all" && it.kind !== "call" && it.level !== state.level) return false;
    if (state.region && it.region !== state.region) return false;
    if (state.topics.size && !(it.topics || []).some((t) => state.topics.has(t))) return false;
    if (state.q) {
      const hay = `${it.title_en || ""} ${it.title} ${it.institution} ${it.city || ""} ${it.region} ${(it.topics || []).join(" ")}`.toLowerCase();
      if (!state.q.split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function matchCell(it, pid) {
    const v = m(it, pid);
    if (v === null) return `<td class="num" data-label="Match ${esc(pid)}"><span class="muted">–</span></td>`;
    const cls = v >= DATA.threshold ? "hi" : v >= 40 ? "mid" : "lo";
    return `<td class="num" data-label="Match ${esc(pid)}"><span class="pct ${cls}" style="--w:${v}%">${v}%</span></td>`;
  }

  function row(it) {
    const en = it.title_en || it.title;
    const orig = en !== it.title ? `<div class="orig">Original: ${esc(it.title)}</div>` : "";
    const isNew = it.first_seen && daysTo(it.first_seen) >= -7;
    const tags = `<span class="tag level">${it.kind === "call" ? "Fellowship call · all fields" : levelLabel(it.level)}</span>${isNew ? '<span class="tag new">New</span>' : ""}`;
    let dl = '<span class="muted">Not stated</span>';
    if (it.deadline) {
      const d = daysTo(it.deadline);
      dl = `<span class="${d <= 7 ? "soon" : ""}"${it.deadline_estimated ? ' title="Estimated from the call text. Check the announcement."' : ""}>${it.deadline_estimated ? "≈ " : ""}${fmt(it.deadline)}</span>${d >= 0 && d <= 30 ? `<div class="muted small">${d === 0 ? "today" : d + " days left"}</div>` : ""}`;
    }
    const loc = [it.city, it.region, COUNTRY[it.country || "ES"]].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(", ");
    const topics = (it.topics || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("") || '<span class="muted">–</span>';
    return `<tr>
      <td data-label="Position" class="pos"><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(en)}</a>${orig}<div class="tags">${tags}</div></td>
      <td data-label="Institution">${esc(it.institution)}</td>
      <td data-label="Location">${esc(loc)}</td>
      <td data-label="Topic"><div class="tags">${topics}</div></td>
      ${DATA.profiles.map((p) => matchCell(it, p.id)).join("")}
      <td data-label="Deadline"><div>${dl}</div></td>
      <td data-label="Link"><a class="open" href="${esc(it.url)}" target="_blank" rel="noopener">Open ↗</a></td>
    </tr>`;
  }

  function render() {
    const items = DATA.items.filter(matches);
    const by = {
      match: (a, b) => best(b) - best(a),
      deadline: (a, b) => (a.deadline || "9999").localeCompare(b.deadline || "9999"),
      new: (a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""),
    };
    DATA.profiles.forEach((p) => { by["p:" + p.id] = (a, b) => (m(b, p.id) ?? -1) - (m(a, p.id) ?? -1); });
    items.sort(by[state.sort] || by.match);
    $("#rows").innerHTML = items.length ? items.map(row).join("")
      : `<tr><td colspan="8" class="empty">No positions match these filters right now. Try "All positions" in the match filter, or check back tomorrow.</td></tr>`;
    const total = DATA.items.filter((i) => i.kind !== "call").length;
    $("#summary").textContent = `${items.length} shown · ${total} open postdoc/researcher positions collected`;
  }

  function seg(id, key) {
    document.querySelectorAll(`#${id} button`).forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll(`#${id} button`).forEach((x) => x.classList.remove("on"));
      b.classList.add("on"); state[key] = b.dataset.v; render();
    }));
  }

  function setup() {
    const P = DATA.profiles, T = DATA.threshold;
    $("#profiles").innerHTML = P.map((p) => `<div class="profile"><span class="pid">${esc(p.id)}</span><div><strong>Match ${esc(p.id)}</strong><br>${esc(p.label)}</div></div>`).join("");
    P.forEach((p) => { const h = $("#h" + p.id); if (h) { h.textContent = `Match ${p.id}`; h.title = p.label; } });
    $("#matchf").innerHTML = [`<option value="any">≥${T}% for profile A or B</option>`,
      ...P.map((p) => `<option value="p:${p.id}">≥${T}% for profile ${p.id} (${esc(p.short)})</option>`),
      `<option value="all">All positions</option>`].join("");
    $("#sort").innerHTML = [`<option value="match">Best match first</option>`,
      ...P.map((p) => `<option value="p:${p.id}">Match ${p.id} first</option>`),
      `<option value="deadline">Deadline soonest</option>`, `<option value="new">Newest first</option>`].join("");

    const groups = {};
    DATA.items.forEach((i) => { if (i.region) (groups[i.country || "ES"] ||= new Set()).add(i.region); });
    $("#region").insertAdjacentHTML("beforeend", Object.keys(groups).sort().reverse().map((c) =>
      `<optgroup label="${COUNTRY[c]}">${[...groups[c]].sort().map((r) => `<option>${esc(r)}</option>`).join("")}</optgroup>`).join(""));
    const topics = [...new Set(DATA.items.flatMap((i) => i.topics || []))].sort();
    $("#topics").innerHTML = topics.map((t) => `<button class="chip" data-t="${esc(t)}">${esc(t)}</button>`).join("");
    $("#topics").addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      const t = b.dataset.t; state.topics.has(t) ? state.topics.delete(t) : state.topics.add(t);
      b.classList.toggle("on"); render();
    });
    seg("country", "country"); seg("level", "level");
    $("#q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
    $("#region").addEventListener("change", (e) => { state.region = e.target.value; render(); });
    $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
    $("#matchf").addEventListener("change", (e) => { state.matchf = e.target.value; render(); });
    $("#calls").addEventListener("change", (e) => { state.calls = e.target.checked; render(); });

    $("#updated").textContent = DATA.generated ? new Date(DATA.generated).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "–";
    $("#srcs").innerHTML = (DATA.sources || []).map((s) => `<tr><td>${esc(s.institution)}</td>
      <td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a></td>
      <td class="${s.ok ? "ok" : "bad"}">${s.ok ? "OK" : esc(s.error || "error")}</td><td>${s.ok ? s.kept : "–"}</td></tr>`).join("");
  }

  fetch("data/jobs.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((d) => { DATA = { profiles: [], threshold: 60, ...d }; setup(); render(); })
    .catch(() => { $("#summary").textContent = "Couldn't load positions. Please try again later."; });
})();
