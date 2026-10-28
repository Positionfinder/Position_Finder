(() => {
  const $ = (s) => document.querySelector(s);
  const state = { level: "all", fields: new Set(), q: "", region: "", itype: "", sort: "new", calls: false };
  let DATA = { items: [], sources: [] };

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const daysTo = (iso) => Math.round((new Date(iso + "T00:00:00") - today) / 86400000);
  const fmt = (iso) => new Date(iso + "T00:00:00").toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  function levelLabel(l) { return l === "phd" ? "PhD" : l === "postdoc" ? "Postdoc" : "PhD / Postdoc"; }

  function matches(it) {
    if (!state.calls && it.kind === "call") return false;
    if (state.level !== "all" && !(it.level || "").includes(state.level)) return false;
    if (state.region && it.region !== state.region) return false;
    if (state.itype && it.inst_type !== state.itype) return false;
    if (state.fields.size && !(it.fields || []).some((f) => state.fields.has(f))) return false;
    if (state.q) {
      const hay = `${it.title} ${it.institution} ${it.region} ${(it.fields || []).join(" ")}`.toLowerCase();
      if (!state.q.split(/\s+/).every((w) => hay.includes(w))) return false;
    }
    return true;
  }

  function card(it) {
    const isNew = it.first_seen && daysTo(it.first_seen) >= -7;
    let dl = "";
    if (it.deadline) {
      const d = daysTo(it.deadline);
      dl = `<span class="deadline${d <= 7 ? " soon" : ""}">Deadline ${fmt(it.deadline)}${d >= 0 && d <= 30 ? ` · ${d === 0 ? "today" : d + " days"}` : ""}</span>`;
    }
    const tags = [
      it.level ? `<span class="tag level">${levelLabel(it.level)}</span>` : "",
      isNew ? `<span class="tag new">New</span>` : "",
      it.kind === "call" ? `<span class="tag call">Fellowship call · all fields</span>` : "",
      ...(it.fields || []).map((f) => `<span class="tag">${esc(f)}</span>`),
    ].join("");
    return `<li class="card"><h3><a href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.title)}</a></h3>
      <p class="meta">${esc(it.institution)}${it.region ? " · " + esc(it.region) : ""}</p>
      <div class="tags">${tags}${dl}</div></li>`;
  }

  function render() {
    let items = DATA.items.filter(matches);
    if (state.sort === "deadline") items.sort((a, b) => (a.deadline || "9999").localeCompare(b.deadline || "9999"));
    else items.sort((a, b) => (b.first_seen || "").localeCompare(a.first_seen || ""));
    $("#list").innerHTML = items.length ? items.map(card).join("")
      : `<li class="empty">No positions match these filters right now. Try clearing a filter, or check back tomorrow.</li>`;
    const total = DATA.items.filter((i) => state.calls || i.kind !== "call").length;
    $("#summary").textContent = `${items.length} of ${total} open position${total === 1 ? "" : "s"}`;
  }

  function setup() {
    const regions = [...new Set(DATA.items.map((i) => i.region).filter(Boolean))].sort();
    $("#region").insertAdjacentHTML("beforeend", regions.map((r) => `<option>${esc(r)}</option>`).join(""));
    const fields = [...new Set(DATA.items.flatMap((i) => i.fields || []))].sort();
    $("#fields").innerHTML = fields.map((f) => `<button class="chip" data-f="${esc(f)}">${esc(f)}</button>`).join("");
    $("#fields").addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      const f = b.dataset.f; state.fields.has(f) ? state.fields.delete(f) : state.fields.add(f);
      b.classList.toggle("on"); render();
    });
    document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll(".seg button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on"); state.level = b.dataset.level; render();
    }));
    $("#q").addEventListener("input", (e) => { state.q = e.target.value.trim().toLowerCase(); render(); });
    $("#region").addEventListener("change", (e) => { state.region = e.target.value; render(); });
    $("#itype").addEventListener("change", (e) => { state.itype = e.target.value; render(); });
    $("#sort").addEventListener("change", (e) => { state.sort = e.target.value; render(); });
    $("#calls").addEventListener("change", (e) => { state.calls = e.target.checked; render(); });

    $("#updated").textContent = DATA.generated ? new Date(DATA.generated).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" }) : "–";
    $("#srcs").innerHTML = (DATA.sources || []).map((s) => `<tr><td>${esc(s.institution)}</td>
      <td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a></td>
      <td class="${s.ok ? "ok" : "bad"}">${s.ok ? "OK" : esc(s.error || "error")}</td><td>${s.ok ? s.kept : "–"}</td></tr>`).join("");
  }

  fetch("data/jobs.json", { cache: "no-cache" })
    .then((r) => r.json())
    .then((d) => { DATA = d; setup(); render(); })
    .catch(() => { $("#summary").textContent = "Couldn't load positions. Please try again later."; });
})();
