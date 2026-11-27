const el = id => document.getElementById(`teaching-${id}`);
const put = (id, value) => { el(id).textContent = value; };
const sameId = (a, b) => a.toLowerCase() === b.toLowerCase();

export function createTeaching(onLocations, onFocus) {
  let session = null, current = null, visible = false, busy = false, loading = false, unauthorized = false;
  let nextRefresh = 0, selected = null, form = null, listSignature = "", feedback = "";
  const manifest = () => current?.manifest;
  const locations = () => manifest()?.locations || [];
  const saved = () => locations().find(record => record.record_id === selected);
  const photo = record => `/api/service/mapping/${record.mapping_id}/${record.reference_image}`;
  const fit = record => record.localization.rms == null ? "Tracking" : `Tracking · ${(record.localization.rms * 1000).toFixed(0)} mm RMS`;
  const selectedText = record => `${record.position_m[2].toFixed(2)} m · ${record.status === "approved" ? "Approved" : record.status}`;

  async function request(path = "", data) {
    const response = await fetch(`/api/service/teaching${path}`, data === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
    const body = await response.json();
    if (!response.ok) {
      if (response.status === 401) {
        unauthorized = true;
        current = selected = form = null;
        onLocations([], null);
      }
      throw new Error(body.error || "Storage location request unavailable.");
    }
    unauthorized = false;
    return body;
  }

  function message(value = "") {
    feedback = value;
  }

  function renderList() {
    const signature = JSON.stringify([session, manifest(), selected]);
    if (signature === listSignature) return;
    listSignature = signature;
    const rows = locations().map(record => {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "teaching-row";
      button.setAttribute("aria-pressed", String(record.record_id === selected));
      const image = document.createElement("img");
      image.src = photo(record);
      image.alt = "";
      image.loading = "lazy";
      const words = document.createElement("span");
      const name = document.createElement("strong");
      name.textContent = record.storage_location_id;
      const meta = document.createElement("small");
      meta.textContent = `${selectedText(record)} · ${fit(record)}`;
      words.append(name, meta);
      button.append(image, words);
      button.addEventListener("click", () => select(record.record_id));
      li.append(button);
      return li;
    });
    el("list").replaceChildren(...rows);
    const record = saved();
    el("details").hidden = !record;
    if (record) {
      put("record-title", record.storage_location_id);
      el("reference").src = photo(record);
      const xyz = record.position_m.map(value => value.toFixed(2)).join(" / ");
      const source = record.id_source === "aruco" ? "ArUco location marker" : "Operator ID";
      const time = new Date(record.received_at_utc).toLocaleTimeString();
      put("record-data", `${selectedText(record)} · ${fit(record)} · ${source} · ${time} · XYZ ${xyz} m${record.description ? ` · ${record.description}` : ""}`);
    } else {
      el("reference").removeAttribute("src");
    }
    onLocations(locations(), selected);
  }

  function targetRecord() {
    return form?.record || (form?.type === "save"
      ? locations().find(record => sameId(record.storage_location_id, el("id").value.trim()))
      : null);
  }

  function renderForm() {
    el("form").hidden = !form;
    if (!form) {
      el("preview").removeAttribute("src");
      return;
    }
    const target = targetRecord();
    const confirmation = form.type === "delete" || form.type === "save" && !!target;
    const signature = confirmation ? target.record_id : null;
    if (form.confirmId !== signature) el("confirm").checked = false;
    form.confirmId = signature;
    el("confirm-field").hidden = !confirmation;
    if (confirmation) put("confirm-label", form.type === "delete"
      ? `Remove ${target.storage_location_id} from this draft.`
      : `Replace the saved pose and photo for ${target.storage_location_id}.`);
    el("save").disabled = busy || !current?.editable || (form.type === "save" && !current.capture_ready)
      || (confirmation && !el("confirm").checked);
  }

  function render() {
    el("panel").hidden = !visible || !session;
    put("count", manifest() ? `${locations().length} registered` : "Service access required");
    el("empty").hidden = !manifest() || !!locations().length;
    el("capture").disabled = busy || !!form || !current?.capture_ready;
    el("edit-tools").hidden = !current?.editable;
    el("recapture").disabled = busy || !!form || !current?.capture_ready;
    el("rename").disabled = el("remove").disabled = busy || !!form;
    const status = unauthorized ? "Unlock Service to view or register locations."
      : feedback || (current?.editable && !form ? current.reason : "");
    put("feedback", status || "");
    el("feedback").hidden = !status;
    renderList();
    renderForm();
  }

  async function refresh(force = false) {
    if (!visible || !session || busy || loading || (!force && performance.now() < nextRefresh)) return;
    const startedSession = session;
    nextRefresh = performance.now() + 640;
    loading = true;
    try {
      const data = await request();
      if (startedSession !== session || data.manifest?.calibration_id !== session) return;
      if (!manifest() || data.manifest.revision >= manifest().revision) current = data;
      render();
    } catch (error) {
      if (startedSession === session) {
        message(error.message);
        render();
      }
    } finally {
      loading = false;
    }
  }

  function select(id, focus = true) {
    const record = locations().find(item => item.record_id === id);
    if (!record) return;
    selected = id;
    render();
    if (focus) onFocus(record);
  }

  function open(type, record = null, capture = null) {
    form = { type, record, capture, revision: manifest().revision };
    put("form-title", type === "delete" ? "Remove draft location" : type === "rename" ? "Change location ID" : "Register Storage Location");
    put("save", type === "delete" ? "Remove location" : type === "rename" ? "Save ID" : "Save location");
    el("id-field").hidden = el("id").disabled = type === "delete";
    el("description-field").hidden = type !== "save";
    el("id").value = record?.storage_location_id || capture?.suggested_id || "";
    el("description").value = record?.description || "";
    el("preview").hidden = !capture;
    if (capture) el("preview").src = capture.photo;
    el("suggestion").hidden = !capture;
    if (capture) put("suggestion", capture.suggested_id
      ? `Location marker read as ${capture.suggested_id}. Confirm or edit the ID.`
      : "No unambiguous location marker. Enter the ID.");
    el("confirm").checked = false;
    message();
    render();
    (type === "delete" ? el("confirm") : el("id")).focus();
  }

  async function capture(record = null) {
    if (busy || !current?.capture_ready) return;
    const requestedSession = session;
    busy = true;
    message();
    render();
    try {
      const value = await request("/capture", { calibration_id: session });
      if (requestedSession === session && value.calibration_id === session) open("save", record, value);
    } catch (error) { message(error.message); }
    finally {
      busy = false;
      render();
      refresh(true);
    }
  }

  el("capture").addEventListener("click", () => capture());
  el("recapture").addEventListener("click", () => capture(saved()));
  el("rename").addEventListener("click", () => { if (saved()) open("rename", saved()); });
  el("remove").addEventListener("click", () => { if (saved()) open("delete", saved()); });
  el("cancel").addEventListener("click", () => { form = null; message(); render(); });
  el("id").addEventListener("input", renderForm);
  el("confirm").addEventListener("change", renderForm);
  el("form").addEventListener("submit", async event => {
    event.preventDefault();
    if (!form || busy || el("save").disabled) return;
    const { type, revision, capture } = form;
    const target = targetRecord();
    const requestedSession = session;
    const payload = { calibration_id: session, revision, record_id: target?.record_id ?? null,
      confirm: el("confirm").checked };
    if (type !== "delete") payload.storage_location_id = el("id").value.trim();
    if (capture) Object.assign(payload, { capture_id: capture.capture_id, description: el("description").value });
    busy = true;
    message();
    render();
    try {
      const result = await request(`/${type}`, payload);
      if (requestedSession !== session || result.calibration_id !== session) return;
      current = { ...current, manifest: result };
      form = null;
      if (type === "delete") {
        selected = null;
        message("Removed from the draft.");
      } else {
        const record = locations().find(item => sameId(item.storage_location_id, payload.storage_location_id));
        selected = record?.record_id || null;
        message(type === "rename" ? "Location ID updated." : "Location and reference photo saved.");
      }
    } catch (error) { message(error.message); }
    finally {
      busy = false;
      render();
      refresh(true);
    }
  });

  return {
    update(state, view) {
      visible = view === "manual";
      const mapping = state?.localization?.mapping_id || null;
      if (mapping !== session) {
        session = mapping;
        current = form = selected = null;
        unauthorized = false;
        nextRefresh = 0;
        message();
      }
      render();
      refresh();
    },
    select, locations, selection: () => selected,
  };
}
