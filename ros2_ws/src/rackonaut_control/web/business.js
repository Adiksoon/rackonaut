import { activeMission, displayDate, droneProfile, missionPhase } from "/operator.js";

const confirmedFindings = new Set(["WRONG_PALLET", "MISSING_PALLET", "UNEXPECTED_PALLET", "DISCONTINUED_PRODUCT",
  "BLOCKED_PRODUCT", "DAMAGED_PACKAGE", "MISPLACED_PALLET"]);
const tone = state => ({discrepancy: "mismatch", manual: "review"}[state] || state);

export function locationResult(row, issues) {
  const mismatch = ["wrong_pallet", "missing_pallet", "unexpected_pallet"].includes(row.outcome);
  const quality = (row.quality_history || []).some(photo => photo.status === "DAMAGED");
  const problem = issues.some(issue => confirmedFindings.has(issue.type));
  if (mismatch || quality || problem) return {state: "discrepancy", label: "Issue detected"};
  if (issues.length || ["unreadable_label", "uncertain"].includes(row.outcome))
    return {state: "manual", label: "Reading needs review"};
  if (row.outcome === "match") return {state: "match", label: "Clear"};
  return {state: "uninspected", label: "Not inspected"};
}

function inspectionDate(run) {
  const date = /^INS-CONTROL-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})-[A-F0-9]+$/.exec(run);
  if (!date) return "";
  const [, year, month, day, hour, minute, second] = date;
  return displayDate(`${year}-${month}-${day}T${hour}:${minute}:${second}Z`);
}

export function createIntelligence(api, locate, reinspect, safe, label, sceneChanged) {
  const el = name => document.getElementById("intelligence" + (name ? "-" + name : ""));
  const status = message => {
    if (el("status").textContent !== message) el("status").textContent = message;
  };
  function replace(name, content) {
    if (el(name).innerHTML !== content) el(name).innerHTML = content;
  }
  function options(name, entries, all) {
    const select = el(name), previous = select.value;
    const contents = (all ? '<option value="">' + safe(all) + '</option>' : '') +
      entries.map(([value, caption]) => `<option value="${safe(value)}">${safe(caption)}</option>`).join("");
    replace(name, contents);
    if (entries.some(([key]) => key === previous) && select.value !== previous) select.value = previous;
  }
  let runs = new Map(), current = null, latest = null, selectedSlot = null, data = null;
  let pending = false, next = 0, detailSignature = "", photoIndex = 0, annotated = false, selectedIssue = null;
  let reviewed = new Set();

  function detail(issues, known) {
    const slot = data.slots.find(row => row.slot_id === selectedSlot);
    el("detail").hidden = !slot;
    if (!slot) return;
    const featured = issues.find(issue => issue.issue_id === selectedIssue)
      || issues.find(issue => issue.type === "DAMAGED_PACKAGE") || issues[0];
    const signature = JSON.stringify([slot, issues, featured?.issue_id, data.archived, photoIndex, annotated, known]);
    if (signature === detailSignature) return;
    detailSignature = signature;
    const readings = slot.readings || [];
    const reading = readings.at(-1);
    const product = item => [item?.hu_id, item?.product_name].filter(Boolean).join(" · ");
    const observed = reading ? (product(slot.observed_product) || slot.observed_pallet_id ||
      (reading.occupancy === "empty" ? "Empty location" : reading.occupancy === "occupied"
        ? "Occupied · label unreadable" : "Occupancy uncertain")) : "No camera observation in this inspection";
    const outcome = locationResult(slot, issues);
    const linkedPhotos = (featured?.quality || []).filter(photo => photo.slot_id === slot.slot_id && photo.photos?.original);
    const observationIds = new Set(featured ? featured.evidence.filter(event => event.slot_id === slot.slot_id)
      .map(event => event.observation_id) : reading ? [reading.observation_id] : []);
    const matchingPhotos = (slot.quality_history || []).filter(photo => observationIds.has(photo.observation_id));
    const allPhotos = new Map((linkedPhotos.length ? linkedPhotos : matchingPhotos)
      .filter(photo => photo.photos?.original).map(photo => [photo.quality_id, photo]));
    const photos = [...allPhotos.values()].sort((a, b) => Number(b.status === "DAMAGED") - Number(a.status === "DAMAGED")
      || (b.timestamp || "").localeCompare(a.timestamp || ""));
    const photo = photos[photoIndex] || photos[0];
    const source = annotated && photo?.photos.annotated ? photo.photos.annotated : photo?.photos.original;
    const photoLabel = annotated && photo?.photos.annotated ? "Annotated photo" : "Original photo";
    const issueCards = (featured ? [featured] : []).map(issue => `<li><div class="finding-summary">
      <strong>${safe(label(issue.type))}</strong><span class="outcome-label" data-outcome="${confirmedFindings.has(issue.type) ? "mismatch" : "review"}">
      ${safe(label(issue.priority))} priority</span></div>
      <p>${safe(issue.reason || issue.description)}</p>
      <div class="action-row"><span class="footnote">${issue.status === "VERIFIED" ? "Evidence reviewed" : "Evidence review pending"}</span>
      ${!data.archived && issue.status !== "VERIFIED" ? `<button class="chip" type="button" data-intel-verify="${safe(issue.issue_id)}">Mark evidence reviewed</button>` : ""}</div></li>`).join("");
    el("detail").innerHTML = `<div class="intelligence-detail-head">
      <div><h2>${safe(slot.slot_id)}</h2><span class="outcome-label" data-outcome="${tone(outcome.state)}">${outcome.label}</span></div>
      <div class="action-row">
        <button type="button" class="chip" data-intel-map="${safe(slot.slot_id)}">Show on map</button>
        <button type="button" class="secondary" data-intel-reinspect="${safe(slot.slot_id)}" ${known ? "" : "disabled"}
          aria-describedby="reinspect-help">Plan reinspection</button>
      </div></div>
      ${!known ? '<p class="operator-hint" id="reinspect-help">This location must be taught in the active warehouse before it can be inspected again.</p>'
        : data.archived ? '<p class="operator-hint" id="reinspect-help">Plan locally. Dispatch requires a live drone and inventory API.</p>' : ""}
      <p id="reinspect-feedback" class="operator-hint" role="status"></p>
      ${issues.length ? `<div class="action-row finding-tabs" role="group" aria-label="Findings at this location">${issues.map(issue =>
        `<button class="chip" type="button" data-intel-issue="${safe(issue.issue_id)}" aria-pressed="${issue === featured}">
          ${safe(label(issue.type))}</button>`).join("")}</div>` : ""}
      <div class="evidence-workbench">
      ${source ? `<figure class="evidence-photo">
        <div class="evidence-toolbar action-row">
          <span>${photo.status === "CAPTURED" ? "Observation photo" : safe(label(photo.status))} · ${safe(photo.reason)}</span>
          ${photos.length > 1 ? `<label>Capture <select id="intelligence-photo">${photos.map((item, index) =>
            `<option value="${index}" ${item === photo ? "selected" : ""}>${index + 1}. ${safe(displayDate(item.timestamp, true) || label(item.status))}</option>`).join("")}</select></label>` : ""}
          ${photo.photos.annotated ? '<button type="button" class="chip" data-intel-annotate aria-pressed="' + annotated + '">' +
            (annotated ? "Show original" : "Show annotations") + '</button>' : ""}
        </div>
        <a href="${safe(source)}" target="_blank" rel="noopener"><img src="${safe(source)}"
          alt="${photoLabel} at ${safe(slot.slot_id)}"></a>
        <figcaption>${photoLabel}${photo.timestamp ? " · " + safe(displayDate(photo.timestamp, true)) : ""}</figcaption>
      </figure>` : `<div class="empty-result"><p>No photo was saved for this observation.</p>${reading
        ? `<p><strong>Latest camera reading</strong> · ${safe(label(reading.occupancy))} · ${safe(label(reading.label_status))}
          · ${safe(displayDate(reading.timestamp,true))}</p>` : ""}</div>`}
      <div class="intelligence-facts"><div><strong>Expected in Mock SAP</strong><p>${safe(product(slot.expected_product) || slot.expected_pallet_id || "Empty location")}</p></div>
      <div><strong>Observed by drone</strong><p>${safe(observed)}</p></div>
      ${featured ? `<div class="finding-action"><strong>${safe(label(featured.type))} · Recommended action</strong>
        <p>${safe(featured.action)}</p><p>${featured.status === "VERIFIED" ? "Evidence reviewed" : "Evidence review pending"}</p></div>` : ""}</div>
      </div>
      ${issueCards ? '<ul class="finding-details">' + issueCards + '</ul>' : ""}
      ${readings.length ? '<details><summary>Camera readings</summary><ul>' + readings.map(event =>
        `<li>${safe(label(event.occupancy))} · ${safe(label(event.label_status))} · ${safe(displayDate(event.timestamp))}</li>`).join("") + '</ul></details>' : ""}
    `;
    const help = document.getElementById("reinspect-help");
    if (!help) el("detail").querySelector("[data-intel-reinspect]").removeAttribute("aria-describedby");
    el("detail").querySelector("img")?.addEventListener("error", event => {
      const message = document.createElement("p");
      message.className = "empty-result";
      message.textContent = "This evidence image is unavailable.";
      event.target.closest("figure").append(message);
      event.target.closest("a").hidden = true;
    }, {once:true});
  }

  let canReinspect = () => true;

  function render() {
    el("content").hidden = !data;
    document.getElementById("business-map").disabled = !current;
    if (!data) {
      el("metrics").replaceChildren();
      sceneChanged(current, {});
      return;
    }
    const byLocation = new Map(data.slots.map(row => [row.slot_id, []]));
    for (const issue of data.issues) byLocation.get(issue.slot_id)?.push(issue);
    const markers = Object.fromEntries(data.slots.map(row => [row.slot_id, locationResult(row, byLocation.get(row.slot_id))]));
    sceneChanged(current, markers);
    const metadata = runs.get(current);
    const plan = metadata?.planned_slots || [];
    const { metrics } = data;
    const observedInPlan = plan.length ? data.slots.filter(row => plan.includes(row.slot_id) && row.readings?.length).length
      : metadata?.confirmed;
    const completed = Number.isFinite(observedInPlan) && metadata?.total ? `${observedInPlan} / ${metadata.total}` : "Unavailable";
    const lifecycle = new Set(data.issues.filter(issue => ["DISCONTINUED_PRODUCT", "BLOCKED_PRODUCT"].includes(issue.type))
      .map(issue => issue.slot_id)).size;
    const measures = [
      ["Plan completed", completed, "Planned locations with observations"],
      ["Warehouse coverage", `${metrics.observed} / ${metrics.total}`, "Locations in the Mock SAP register"],
      ["Inventory mismatches", metrics.inventory_discrepancies, "Compared with Mock SAP"],
      ["Damaged packages", metrics.damaged_packages, "Visible packaging damage"],
      ["Reading needs review", metrics.manual_review_locations, "Uncertain or incomplete readings"],
      ["Restricted stock", lifecycle, "Discontinued or blocked products"],
    ];
    replace("metrics", measures.map(([title, value, hint]) =>
      `<div><span>${title}</span><strong>${value}</strong><small>${hint}</small></div>`).join(""));
    const issueTypes = [...new Set(data.issues.map(issue => issue.type))].sort();
    options("type", issueTypes.map(type => [type, label(type)]), "All types");
    const type = el("type").value, review = el("review").value;
    const filtered = [...byLocation].map(([place, issues]) => [place, issues.filter(issue =>
      (!type || issue.type === type) && (!review || issue.status === review))]).filter(([, issues]) => issues.length);
    filtered.sort(([a, aa], [b, bb]) => Number(bb.some(issue => issue.priority === "HIGH"))
      - Number(aa.some(issue => issue.priority === "HIGH")) || bb.length - aa.length || a.localeCompare(b));
    if (!selectedSlot) selectedSlot = filtered[0]?.[0] || data.slots.find(row => row.readings?.length)?.slot_id || null;
    replace("issues", filtered.map(([place, issues]) => {
      const verified = issues.filter(issue => issue.status === "VERIFIED").length;
      const names = [...new Set(issues.map(issue => label(issue.type)))];
      return `<button type="button" class="issue-group" data-intel-location="${safe(place)}" aria-pressed="${place === selectedSlot}">
        <span><strong>${safe(place)}</strong><span class="outcome-label" data-outcome="${tone(markers[place].state)}">
          ${issues.some(issue => issue.priority === "HIGH") ? "High priority" : safe(label(issues[0].priority)) + " priority"}</span></span>
        <span>${safe(names.join(" · "))}</span>
        <small>${issues.length} ${issues.length === 1 ? "finding" : "findings"} · ${verified === issues.length ? "Evidence reviewed" : `${verified} of ${issues.length} reviewed`}</small>
      </button>`;
    }).join("") || '<p class="empty-result">No findings match these filters.</p>');
    replace("locations", data.slots.map(row => {
      const result = markers[row.slot_id];
      return `<button type="button" data-intel-location="${safe(row.slot_id)}" data-outcome="${tone(result.state)}"
        aria-pressed="${row.slot_id === selectedSlot}"><strong>${safe(row.slot_id)}</strong><span>${result.label}</span></button>`;
    }).join(""));
    detail(byLocation.get(selectedSlot) || [], canReinspect(selectedSlot));
  }

  async function refresh() {
    if (!current || pending || Date.now() < next) return;
    const run = current;
    pending = true;
    try {
      const response = await api("/api/business/summary?inspection_id=" + encodeURIComponent(run));
      if (run !== current) return;
      data = response;
      const item = runs.get(run);
      const archive = data.archived ? "Saved report · review actions unavailable offline" : "";
      status([item?.warehouse_revision != null ? `Warehouse revision ${item.warehouse_revision}` : "", archive]
        .filter(Boolean).join(" · "));
      replace("id", `<summary>Inspection ID</summary><code>${safe(run)}</code>`);
      render();
    } catch (error) {
      if (run === current) status(error.message);
    } finally {
      pending = false;
      next = run === current ? Date.now() + (data ? 3500 : 1800) : 0;
      if (run !== current) refresh();
    }
  }

  function selectRun(run) {
    if (run === current) return;
    current = run;
    data = selectedSlot = null;
    selectedIssue = null;
    photoIndex = 0;
    annotated = false;
    detailSignature = "";
    next = 0;
    el("run").value = run || "";
    status(run ? "Loading inspection results…" : "Completed inspections will appear here.");
    el("id").hidden = !run;
    render();
    refresh();
  }

  el("run").addEventListener("change", () => selectRun(el("run").value));
  for (const name of ["type", "review"]) el(name).addEventListener("change", render);
  el("").addEventListener("change", event => {
    if (event.target.id !== "intelligence-photo") return;
    photoIndex = Number(event.target.value);
    annotated = false;
    render();
    el("photo")?.focus();
  });
  el("").addEventListener("click", async event => {
    const item = event.target.closest("button");
    if (!item || !data) return;
    if (item.dataset.intelLocation) {
      selectLocation(item.dataset.intelLocation);
      [...el("issues").querySelectorAll("button"), ...el("locations").querySelectorAll("button")]
        .find(button => button.dataset.intelLocation === selectedSlot && button.getClientRects().length)?.focus();
    }
    if (item.dataset.intelMap) await locate(item.dataset.intelMap, current);
    if (item.dataset.intelReinspect) {
      try { await reinspect(item.dataset.intelReinspect); }
      catch (error) { document.getElementById("reinspect-feedback").textContent = error.message; }
    }
    if (item.dataset.intelIssue) {
      selectedIssue = item.dataset.intelIssue;
      photoIndex = 0;
      annotated = false;
      render();
      el("detail").querySelector(`[data-intel-issue="${CSS.escape(selectedIssue)}"]`)?.focus();
    }
    if ("intelAnnotate" in item.dataset) {
      annotated = !annotated;
      render();
      el("detail").querySelector("[data-intel-annotate]")?.focus();
    }
    if (item.dataset.intelVerify) {
      const issue = data.issues.find(row => row.issue_id === item.dataset.intelVerify);
      if (!issue || reviewed.has(issue.issue_id)) return;
      reviewed.add(issue.issue_id);
      try {
        item.disabled = true;
        await api(`/api/business/issues/${issue.issue_id}/verify`, {inspection_id: current, revision: issue.revision});
        next = 0;
        await refresh();
      } catch (error) { status(error.message); }
      finally { item.disabled = false; reviewed.delete(issue.issue_id); }
    }
  });

  function selectLocation(id) {
    if (!data?.slots.some(row => row.slot_id === id)) return false;
    selectedSlot = id;
    selectedIssue = null;
    annotated = false;
    photoIndex = 0;
    render();
    return true;
  }

  return {
    selectLocation,
    currentRun: () => current,
    update(state, eligible) {
      canReinspect = eligible || canReinspect;
      const business = state?.backend?.mode === "mock_sap";
      const history = (state?.history || []).filter(item => item.business || business);
      el("").hidden = !business && !history.length;
      if (el("").hidden) return;
      runs = new Map(history.map(row => [row.run, row]));
      const job = state.mission;
      if (business && job?.mode !== "manual" && !activeMission(job) && job?.result && !runs.has(job.inspection_id)) {
        runs.set(job.inspection_id, {stage:job.stage, total:job.slots.length, planned_slots:job.slots, url:job.result.url});
      }
      const previousLatest = latest;
      latest = runs.keys().next().value || null;
      options("run", [...runs].map(([run, item]) => [run, [
        inspectionDate(run) || run, item.warehouse_name, item.drone_model && droneProfile(item.drone_model),
        item.planned_slots?.length ? item.planned_slots.join(" → ") : "",
        item.stage ? missionPhase(item) : "",
      ].filter(Boolean).join(" · ")]), runs.size ? "" : "No saved inspection");
      selectRun(current && current !== previousLatest && runs.has(current) ? current : latest);
      const report = runs.get(current)?.url;
      el("report").hidden = !report;
      if (report) el("report").href = report;
      refresh();
    },
  };
}
