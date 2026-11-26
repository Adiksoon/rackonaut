const el = id => document.getElementById(`route-${id}`);
const set = (id, value) => { el(id).textContent = value; };
const number = (value, unit) => Number.isFinite(value) ? `${value.toFixed(2)} ${unit}` : "—";

export function createRouteReview(api, changed) {
  let session = null, revision = null, selectedLocation = null, busy = false;
  let shortlist = new Set(), proposal = null, error = "";
  let archive = false, canSeal = false, sealed = "";
  const trusted = () => ["validated","approved"].includes(revision?.status);
  const review = () => revision?.route;
  const title = status => ({review:"Pending validation",validated:"Validated · live clearance required",
    approved:"Approved for this calibration",stale:"Locations changed · review again",rejected:"Validation rejected"}[status] || "Not reviewed");
  function drawStops() {
    const graph = review();
    const children = (graph?.locations || []).map(stop => {
      const wrapper = document.createElement("label");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = shortlist.has(stop.record_id);
      input.dataset.stop = stop.storage_location_id;
      input.addEventListener("change", () => {
        if (input.checked) shortlist.add(stop.record_id);
        else shortlist.delete(stop.record_id);
        proposal = null;
        render();
      });
      wrapper.append(input, document.createTextNode(stop.storage_location_id));
      return wrapper;
    });
    el("stops").replaceChildren(...children);
    const list = (graph?.nodes || []).map(node => {
      const item = document.createElement("li");
      const view = node.type.toLowerCase().replaceAll("_"," ");
      item.textContent = `${node.id} · ${view} · ${node.leg.toLowerCase()} · yaw ${(node.yaw_rad*180/Math.PI).toFixed(0)}°`;
      return item;
    });
    el("nodes").replaceChildren(...list);
  }
  function render() {
    const route = review();
    const approved = revision?.status==="approved";
    set("session", archive ? "Saved route" : approved ? "Ready to save" : "Review before approving");
    el("result").hidden = !route;
    set("feedback",error || (busy ? "Working…" : sealed || title(revision?.status)));
    el("review-again").hidden = el("validate").hidden = el("approve").hidden = archive;
    el("validate").hidden ||= trusted();
    el("approve").hidden ||= !trusted() || approved;
    el("seal").hidden = archive || !canSeal || !approved;
    el("seal").disabled = busy || !!sealed;
    el("stop-options").hidden = archive;
    set("energy-title",archive ? "Calibration route forecast" : "Energy forecast");
    el("review-again").disabled = busy || !session;
    el("validate").disabled = busy || !route;
    el("approve").disabled = busy || !trusted() || approved || !el("confirm").checked;
    el("validate").classList.toggle("primary", !!route && !trusted());
    el("validate").classList.toggle("secondary", !route || trusted());
    el("seal").classList.toggle("primary", approved && !sealed);
    el("seal").classList.toggle("secondary", !approved || !!sealed);
    el("confirm-area").hidden = !trusted() || approved;
    el("plan").disabled = busy || !trusted() || shortlist.size===0;
    if (!route) {
      changed();
      return;
    }
    const values = route.summary;
    set("samples",values.raw_samples);
    set("waypoints",values.waypoints);
    set("raw-distance",number(values.recorded_distance_m,"m"));
    set("length",number(values.learned_distance_m,"m"));
    set("deviation",number(values.max_deviation_m*1000,"mm"));
    const verification = revision.validation;
    set("validation",verification?.valid ? `${verification.validated_segments} segments · historical` : title(revision?.status));
    el("issues").replaceChildren(...(verification?.issues || []).map(issue => {
      const li = document.createElement("li"); li.textContent = issue; return li;
    }));
    el("issues").hidden = !verification?.issues?.length;
    el("plan-result").hidden = !proposal;
    if (proposal) set("plan-result",`${proposal.selected.map(stop=>stop.storage_location_id).join(" → ")} · ${proposal.edges} directed edges to dock`);
    const forecast = proposal?.forecast || route.forecast;
    set("time",number(forecast.duration_sim_s,"s sim"));
    set("climb",number(forecast.climb_m,"m"));
    set("energy",number(forecast.mission_percent,"pp"));
    set("return",number(forecast.return_percent,"pp"));
    set("reserve",number(forecast.reserve_percent,"pp"));
    const usage = route.calibration_energy?.sorties?.[0];
    set("actual",usage ? number(usage.start_percent-usage.end_percent,"pp") : "—");
    const photo = revision.locations.find(row => row.record_id===selectedLocation);
    el("photo-panel").hidden = !photo;
    if (photo) {
      set("photo-title",photo.storage_location_id);
      el("photo").src = `/api/service/mapping/${session}/${photo.reference_image}`;
    }
    changed();
  }
  async function action(name, data={}) {
    if (!session || busy) return;
    busy = true;
    error = "";
    render();
    try {
      const result = await api(`/api/service/route/${name}`,{
        calibration_id:session,route_sha256:revision?.route_sha256,...data,
      });
      if (name==="plan") proposal = result;
      else {
        if (!revision || revision.route_sha256!==result.route_sha256) {
          shortlist = new Set(result.route?.locations?.map(stop=>stop.record_id));
          selectedLocation = null;
          el("confirm").checked = false;
        }
        revision = result;
        proposal = null;
        drawStops();
        if (name === "approve" && result.status === "approved") changed("approved");
      }
    } catch (cause) {
      error = cause.message;
    } finally {
      busy = false;
      render();
    }
  }
  el("review-again").addEventListener("click",()=>action("review"));
  el("validate").addEventListener("click",()=>action("validate"));
  el("approve").addEventListener("click",()=>action("approve",{confirm:el("confirm").checked}));
  el("seal").addEventListener("click",async () => {
    if (busy) return;
    busy = true;
    error = "";
    render();
    try {
      const result = await api("/api/service/warehouses/seal", {calibration_id:session});
      sealed = "Saved revision " + result.manifest.revision + " · " + result.manifest.configuration_id;
    } catch (cause) {
      error = cause.message;
    } finally {
      busy = false;
      render();
    }
  });
  el("plan").addEventListener("click",()=>action("plan",{record_ids:[...shortlist]}));
  for (const label of ["raw","learned","locations"]) el(`show-${label}`).addEventListener("change",render);
  el("confirm").addEventListener("change",render);
  return {
    open(id, enableSeal = false) {
      session=id;
      archive = false;
      canSeal = enableSeal;
      sealed = error = "";
      revision = proposal = selectedLocation = null;
      shortlist = new Set();
      el("confirm").checked = false;
      render();
      action("review");
    },
    openArchive(value) {
      session = value.mapping_id;
      archive = true;
      revision = value;
      shortlist = new Set();
      proposal = selectedLocation = null;
      sealed = error = "";
      drawStops();
      render();
    },
    display() {
      if (!revision?.route) return null;
      return {raw:revision.raw_positions, nodes:revision.route.nodes, showRaw:el("show-raw").checked,
        showLearned:el("show-learned").checked, locations:el("show-locations").checked ? revision.locations : [],
        selectedLocation};
    },
    select(id) {
      const photo = revision?.locations?.find(row => row.record_id===id);
      if (!photo) return null;
      selectedLocation=id;
      render();
      return photo;
    }
  };
}
