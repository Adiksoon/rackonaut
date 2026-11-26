export function createIntelligence(api, locate, safe, label) {
  const el = name => document.getElementById("intelligence" + (name ? "-" + name : ""));
  const status = message => { el("status").textContent = message; };
  const options = (name, entries, all) => {
    const select = el(name), previous = select.value;
    const contents = (all ? '<option value="">' + safe(all) + '</option>' : '') +
      entries.map(([value, caption]) => `<option value="${safe(value)}">${safe(caption)}</option>`).join("");
    if (select.innerHTML !== contents) {
      select.innerHTML = contents;
      if (entries.some(([key]) => key === previous)) select.value = previous;
    }
  };
  let current = null, data = null, selected = null, automatic = true, latest = null, pending = false, next = 0;
  let detailSignature = "", rowSignature = "", locationSignature = "", selectedSlot = null;
  const outcomes = {
    match: ["match", "Match"], wrong_pallet: ["mismatch", "Mismatch"],
    missing_pallet: ["mismatch", "Mismatch"], unexpected_pallet: ["mismatch", "Mismatch"],
    unreadable_label: ["review", "Needs review"], uncertain: ["unknown", "Unreliable reading"],
    uninspected: ["uninspected", "Not inspected"],
  };
  const outcome = row => outcomes[row.outcome] || ["unknown", "No reliable data"];

  function detail(issue) {
    const slot = data.slots.find(row => row.slot_id === (issue?.slot_id || selectedSlot));
    const section = el("detail");
    section.hidden = !slot;
    if (!slot) return;
    const signature = JSON.stringify([issue, slot]);
    if (signature === detailSignature) return;
    detailSignature = signature;
    const product = item => [item?.hu_id, item?.product_name].filter(Boolean).join(" · ");
    const stockDetails = [slot.expected_product, slot.observed_product].map((item, index) => item ?
      `<li><strong>${index ? "Observed stock" : "Expected stock"}</strong> · ${safe([item.hu_id,
      item.sku && `SKU ${item.sku}`, item.batch && `batch ${item.batch}`, item.lifecycle_status,
      item.quality_status, item.stock_status, item.expected_slot && `assigned ${item.expected_slot}`].filter(Boolean).join(" · "))}</li>` : "").join("");
    const allPhotos = new Map([...slot.quality_history, ...(issue?.quality || [])].map(photo => [photo.quality_id, photo]));
    const photos = [...allPhotos.values()].map(photo => `<figure>
      <a href="${safe(photo.photos.annotated)}" target="_blank" rel="noopener">
        <img src="${safe(photo.photos.annotated)}" alt="Annotated camera evidence at ${safe(photo.slot_id)}" loading="lazy"></a>
      <figcaption>${safe(label(photo.status))} · ${safe(photo.reason)}<br>
        <a href="${safe(photo.photos.original)}" target="_blank" rel="noopener">Original photo</a></figcaption></figure>`).join("");
    const events = new Map([...slot.readings, ...(issue?.evidence || [])].map(event => [event.observation_id, event]));
    const observations = [...events.values()].sort((a, b) => a.timestamp.localeCompare(b.timestamp)).map(event =>
      `<li><strong>${safe(event.slot_id)}</strong> · ${safe(event.pallet_id || label(event.occupancy))}
      · ${safe(label(event.label_status))} · <time>${safe(event.timestamp)}</time>
      <code>${safe(event.observation_id)}</code></li>`).join("");
    const related = (issue?.related_issue_ids || []).map(id => data.issues.find(item => item.issue_id === id)).filter(Boolean);
    const [kind, caption] = outcome(slot);
    const reading = slot.readings.at(-1);
    const observed = reading ? (product(slot.observed_product) || slot.observed_pallet_id ||
      (reading.occupancy === "empty" ? "Empty location" : reading.occupancy === "occupied"
        ? "Occupied · label unreadable" : "Occupancy uncertain")) : "No camera observation in this inspection";
    section.innerHTML = `<div class="intelligence-detail-head"><div>
      <span class="outcome-label" data-outcome="${kind}">${caption}</span>
      <h2>${safe(issue ? label(issue.type) : slot.slot_id)}</h2>
      ${issue ? `<p>${safe(slot.slot_id)}</p>` : ""}</div>
      <button class="chip" type="button" data-intel-map="${safe(slot.slot_id)}">Locate on map</button></div>
      <div class="intelligence-facts"><div><strong>Expected</strong><p>${safe(product(slot.expected_product) || slot.expected_pallet_id || "Empty location")}</p></div>
      <div><strong>Observed</strong><p>${safe(observed)}</p></div></div>
      ${issue ? `<div class="intelligence-recommendation"><strong>Recommended action</strong><p>${safe(issue.action)}</p>
      <p class="footnote">${safe(issue.reason)}</p></div>` : ""}
      ${related.length ? '<p>Related issues</p><div class="intelligence-related">' + related.map(item =>
        `<button type="button" class="chip" data-intel-issue="${safe(item.issue_id)}">${safe(label(item.type))} · ${safe(item.slot_id)}</button>`).join("") + '</div>' : ""}
      ${photos ? '<div class="intelligence-photos">' + photos + '</div>' : '<p class="footnote evidence-note">No image was saved for this location.</p>'}
      ${stockDetails ? `<details><summary>Stock record</summary><ul>${stockDetails}</ul></details>` : ""}
      ${observations ? `<details><summary>Camera readings and timestamps</summary><ul>${observations}</ul></details>` : ""}
      ${issue ? `<button class="chip" type="button" data-intel-verify="${safe(issue.issue_id)}" ${issue.status === "VERIFIED" ? "disabled" : ""}>
      ${issue.status === "VERIFIED" ? "Evidence reviewed" : "Mark evidence as reviewed"}</button>` : ""}`;
  }

  function render() {
    el("content").hidden = !data;
    if (!data) { el("metrics").replaceChildren(); return; }
    const m = data.metrics;
    const measures = [
      ["Locations observed", m.observed, `${m.total} in warehouse records`],
      ["Stock mismatches", m.inventory_discrepancies, "Confirmed by inventory comparison"],
      ["Needs manual review", m.manual_review_locations, "Locations"],
      ["Damaged packages", m.damaged_packages, "Camera evidence"],
    ];
    el("metrics").innerHTML = measures.map(([title,value,hint]) =>
      `<div><span>${safe(title)}</span><strong>${safe(value)}</strong><small>${safe(hint)}</small></div>`).join("");
    options("slot", data.slots.map(row => [row.slot_id, row.slot_id]), "All locations");
    options("type", [...new Set(data.issues.map(i => i.type))].sort().map(type => [type,label(type)]), "All types");
    const filters = ["priority","slot","type","review"].map(name => el(name).value);
    const issues = data.issues.filter(item => [item.priority,item.slot_id,item.type,item.status].every((value,index) =>
      !filters[index] || value === filters[index]));
    if (!selected && !selectedSlot && issues.length) selected = issues[0].issue_id;
    const activeIssue = data.issues.find(item => item.issue_id === selected);
    const activeSlot = activeIssue?.slot_id || selectedSlot;
    const signatureLocations = JSON.stringify([activeSlot, data.slots.map(row => [row.slot_id,row.outcome])]);
    if (signatureLocations !== locationSignature) {
      locationSignature = signatureLocations;
      el("locations").innerHTML = data.slots.map(row => {
        const [kind, caption] = outcome(row);
        return `<button type="button" data-intel-location="${safe(row.slot_id)}" data-outcome="${kind}" aria-pressed="${activeSlot === row.slot_id}"><strong>${safe(row.slot_id)}</strong><span>${caption}</span></button>`;
      }).join("");
    }
    const signature = JSON.stringify([issues,selected]);
    if (rowSignature !== signature) {
      rowSignature = signature;
      el("issues").innerHTML = issues.map(item =>
        `<tr data-selected="${selected===item.issue_id}"><td><button class="intelligence-issue" type="button" data-intel-issue="${safe(item.issue_id)}" aria-pressed="${selected===item.issue_id}"><strong>${safe(label(item.type))}</strong><span>${safe(item.slot_id)} · ${item.priority === "HIGH" ? "High priority" : "Review"}${item.status === "VERIFIED" ? " · Reviewed" : ""}</span></button></td></tr>`).join("")
        || '<tr><td>No matching findings.</td></tr>';
    }
    detail(activeIssue);
  }

  async function refresh() {
    if (pending || !current || Date.now() < next) return;
    pending = true;
    const run = current;
    try {
      const response = await api("/api/business/summary?inspection_id=" + encodeURIComponent(run));
      if (run === current && JSON.stringify(data) !== JSON.stringify(response)) {
        data = response;
        render();
      }
      if (run === current) status("");
    } catch (error) {
      if (run === current) status(error.message);
    } finally {
      pending = false;
      next = run === current ? Date.now() + 1700 : 0;
    }
  }

  function select(run) {
    if (current === run) return;
    current = run; selected = null; selectedSlot = null; data = null; next = 0; detailSignature = "";
    el("run").value = run || "";
    status(run ? "Loading inspection evidence…" : "Dispatch an inspection to see the comparison.");
    render();
    refresh();
  }

  el("run").addEventListener("change", () => {
    automatic = el("run").value === latest;
    select(el("run").value);
  });
  for (const name of ["priority","slot","type","review"]) el(name).addEventListener("change", render);
  el("").addEventListener("click", async event => {
    const item = event.target.closest("button");
    if (!item || !data) return;
    if (item.dataset.intelIssue) { selected = item.dataset.intelIssue; selectedSlot = null; render(); }
    if (item.dataset.intelLocation) {
      selectedSlot = item.dataset.intelLocation;
      selected = data.issues.find(row => row.slot_id === selectedSlot)?.issue_id || null;
      render();
    }
    if (item.dataset.intelMap) await locate(item.dataset.intelMap, current);
    if (item.dataset.intelVerify) {
      const issue = data.issues.find(row => row.issue_id === item.dataset.intelVerify);
      if (!issue) return;
      item.disabled = true;
      try {
        await api(`/api/business/issues/${issue.issue_id}/verify`, {inspection_id: current, revision: issue.revision});
        next = 0;
        await refresh();
      } catch (error) { status(error.message); }
      finally { item.disabled = false; }
    }
  });

  return {update(state) {
    el("").hidden = state?.backend?.mode !== "mock_sap";
    if (el("").hidden) return;
    latest = state.mission?.mode !== "manual" && state.mission?.inspection_id || state.history[0]?.run;
    const runs = [...new Set([latest, ...state.history.map(item => item.run)].filter(Boolean))];
    options("run", runs.map((run, index) => [run, index === 0 ? "Latest inspection" : `Inspection ending ${run.slice(-8)}`]), runs.length ? "" : "No inspection");
    select(automatic || !runs.includes(current) ? latest : current);
    const report = (state.mission?.inspection_id === current ? state.mission.result?.url : null) ||
      state.history.find(item => item.run === current)?.url;
    el("report").hidden = !report;
    if (report) el("report").href = report;
    refresh();
  }};
}
