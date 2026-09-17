/* Frontend: fetch only — no CAMS math in JavaScript */

const $ = (id) => document.getElementById(id);

function caseId() {
  return ($("caseId").value || "CASE-001").trim();
}

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmt(v) {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : v.toFixed(3);
  return String(v);
}

function setStatus(msg, kind) {
  const el = $("status");
  el.hidden = !msg;
  el.textContent = msg || "";
  el.className = "status " + (kind || "");
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(`${res.status}: ${t}`);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

function renderExtract(extraction) {
  $("extractNote").textContent = extraction?.note || "";
  const facts = extraction?.facts || [];
  if (!facts.length) {
    $("extractOut").innerHTML = "<p class='help'>No facts extracted.</p>";
    return;
  }
  $("extractOut").innerHTML = facts
    .map(
      (f) => `<div class="item" data-fact="${esc(f.fact_key)}">
      <strong>${esc(f.fact_key)}</strong> = <code>${esc(fmt(f.value))}</code>
      <span class="badge">E=${fmt(f.extraction_confidence)}</span>
      <div class="help">Evidence: “${esc(f.evidence || "(none)")}”</div>
    </div>`
    )
    .join("");
  bindFactClicks($("extractOut"));
}

function renderObservations(obs) {
  if (!obs?.length) {
    $("obsOut").innerHTML = "<p class='help'>No observations saved yet.</p>";
    return;
  }
  $("obsOut").innerHTML = obs
    .map(
      (o) => `<div class="item" data-fact="${esc(o.fact_key)}" data-obs="${esc(o.observation_id)}">
      <strong>${esc(o.fact_key)}</strong> = <code>${esc(fmt(o.value))}</code>
      <span class="badge">${esc(o.source_type)}</span>
      <div>source <b>${esc(o.source || o.source_id)}</b> · id <code>${esc(o.observation_id)}</code></div>
      <div class="help">evidence: “${esc(o.evidence || "")}”</div>
    </div>`
    )
    .join("");
  bindObsClicks($("obsOut"));
}

function renderCamsAndDecisions(decisions) {
  if (!decisions?.length) {
    $("camsOut").innerHTML = "<p class='help'>No CAMS decisions yet.</p>";
    $("decisionOut").innerHTML = "<p class='help'>No decisions yet.</p>";
    return;
  }

  $("camsOut").innerHTML = decisions
    .map((d) => {
      const cands = (d.candidates || [])
        .map((c) => {
          const f = c.factors || {};
          return `<div class="item nested">
            candidate <code>${esc(fmt(c.value))}</code> · C=${fmt(c.confidence)}
            <div class="factors">
              <span>A ${fmt(f.source_authority)}</span>
              <span>T ${fmt(f.temporal_consistency)}</span>
              <span>X ${fmt(f.cross_source_corroboration)}</span>
              <span>E ${fmt(f.extraction_reliability)}</span>
            </div>
          </div>`;
        })
        .join("");
      return `<div class="item" data-fact="${esc(d.fact_key)}">
        <strong>${esc(d.fact_key)}</strong>
        <span class="badge ${d.decided ? "ok" : "warn"}">${esc(d.decision || (d.decided ? "ACCEPTED" : "ABSTAINED"))}</span>
        <div>${esc(d.explanation || d.reason || "")}</div>
        <div class="help">C1=${fmt(d.C1)} · C2=${fmt(d.C2)} · margin=${fmt(d.margin)} · click to expand calculation</div>
        <div class="calc">
          <div>τ=${fmt(d.tau)} · δ=${fmt(d.delta)} · weights ${esc(JSON.stringify(d.weights || {}))}</div>
          <div>previous value: ${esc(fmt(d.previous_value))}</div>
          ${cands}
        </div>
      </div>`;
    })
    .join("");

  $("camsOut").querySelectorAll(".item").forEach((el) => {
    el.onclick = (e) => {
      if (e.target.closest(".nested")) return;
      el.classList.toggle("open");
      selectFact(el.dataset.fact);
    };
  });

  $("decisionOut").innerHTML = decisions
    .map(
      (d) => `<div class="item" data-fact="${esc(d.fact_key)}">
      <strong>${esc(d.fact_key)}</strong>
      <span class="badge ${d.decided ? "ok" : "warn"}">${d.decided ? "ACCEPTED" : "ABSTAINED"}</span>
      <div>${esc(d.explanation || d.reason || "")}</div>
      <div class="help">selected=${esc(fmt(d.selected_value))} · previous kept if abstained=${esc(fmt(d.previous_value))}</div>
    </div>`
    )
    .join("");
  bindFactClicks($("decisionOut"));
}

function renderTwin(facts) {
  const keys = Object.keys(facts || {});
  if (!keys.length) {
    $("twinOut").innerHTML = "<p class='help'>Digital Twin has no resolved facts yet.</p>";
    return;
  }
  $("twinOut").innerHTML = keys
    .map((k) => {
      const f = facts[k];
      return `<div class="item" data-fact="${esc(k)}">
        <strong>${esc(k)}</strong>
        <span class="badge ${f.status === "resolved" ? "ok" : "warn"}">${esc(f.status)}</span>
        <div>value <code>${esc(fmt(f.value))}</code> · confidence ${fmt(f.confidence)}</div>
        <div class="help">updated ${esc(f.last_updated || "—")}</div>
      </div>`;
    })
    .join("");
  bindFactClicks($("twinOut"));
}

function renderConflicts(conflicts) {
  const keys = Object.keys(conflicts || {});
  if (!keys.length) {
    $("conflictOut").innerHTML = "<p class='help'>No unresolved conflicts.</p>";
    return;
  }
  $("conflictOut").innerHTML = keys
    .map((k) => {
      const c = conflicts[k];
      const cands = (c.candidates || [])
        .map((x) => `<li><code>${esc(fmt(x.value))}</code> C=${fmt(x.confidence)}</li>`)
        .join("");
      return `<div class="item" data-fact="${esc(k)}">
        <strong>${esc(k)}</strong> <span class="badge warn">unresolved</span>
        <div>${esc(c.explanation || c.reason || "")}</div>
        <div class="help">Previous twin value kept: ${esc(fmt(c.previous_value))}</div>
        <ul>${cands}</ul>
      </div>`;
    })
    .join("");
  bindFactClicks($("conflictOut"));
}

function renderProvenance(prov) {
  const p = prov?.provenance || {};
  const keys = Object.keys(p);
  if (!keys.length) {
    $("provOut").innerHTML = "<p class='help'>No provenance chains yet.</p>";
    return;
  }
  $("provOut").innerHTML = keys
    .map((k) => {
      const node = p[k];
      const fact = node.current_fact || {};
      const dec = node.latest_decision;
      const traces = (node.trace || [])
        .map(
          (t) => `<div class="trace">
          obs <code>${esc(t.observation?.observation_id)}</code>
          (${esc(t.source_type)}/${esc(t.source)}) →
          evidence “${esc(t.evidence || "")}” →
          text: <em>${esc((t.original_text || "").slice(0, 160))}${(t.original_text || "").length > 160 ? "…" : ""}</em>
        </div>`
        )
        .join("");
      return `<details class="item" data-fact="${esc(k)}">
        <summary><strong>${esc(k)}</strong> = <code>${esc(fmt(fact.value))}</code>
          <span class="badge">${esc(fact.status)}</span></summary>
        <div class="help">Expand shows: twin → last CAMS decision → observations → evidence → original text</div>
        ${
          dec
            ? `<div>Last decision: <b>${esc(dec.decision)}</b> — ${esc(dec.explanation || dec.reason || "")}</div>`
            : ""
        }
        ${traces || "<p class='help'>No supporting observation chain.</p>"}
      </details>`;
    })
    .join("");
}

function selectFact(factKey) {
  if (!factKey) return;
  document.querySelectorAll(".item").forEach((el) => {
    el.classList.toggle("highlight-fact", el.dataset.fact === factKey);
  });
  const explain = $("factExplain");
  explain.hidden = false;
  explain.innerHTML = `<b>Selected fact:</b> <code>${esc(factKey)}</code>.
    Highlighted everywhere it appears. Open History &amp; provenance for the full trace.`;
}

function bindFactClicks(root) {
  root.querySelectorAll("[data-fact]").forEach((el) => {
    el.addEventListener("click", () => selectFact(el.dataset.fact));
  });
}

function bindObsClicks(root) {
  root.querySelectorAll("[data-obs]").forEach((el) => {
    el.addEventListener("click", () => selectFact(el.dataset.fact));
  });
}

async function refreshAll() {
  const id = caseId();
  const [obs, facts, hist, conflicts, prov] = await Promise.all([
    api(`/cases/${encodeURIComponent(id)}/observations`),
    api(`/cases/${encodeURIComponent(id)}/facts`),
    api(`/cases/${encodeURIComponent(id)}/history`),
    api(`/cases/${encodeURIComponent(id)}/conflicts`),
    api(`/cases/${encodeURIComponent(id)}/provenance`),
  ]);
  renderObservations(obs.observations || []);
  renderTwin(facts.facts || {});
  renderCamsAndDecisions(hist.history || []);
  renderConflicts(conflicts.conflicts || {});
  renderProvenance(prov);
}

async function createCase() {
  setStatus("Creating case…", "loading");
  try {
    await api("/cases", {
      method: "POST",
      body: JSON.stringify({
        case_id: caseId(),
        title: caseId() === "CASE-001" ? "Demo case" : caseId(),
        description: "NyayaOS file-backed case",
      }),
    });
    setStatus("Case ready.", "ok");
    await refreshAll();
  } catch (e) {
    setStatus(String(e), "error");
  }
}

async function submitText() {
  const id = caseId();
  const text = $("text").value;
  $("lastInput").textContent = text;
  setStatus("Processing: extract → save observations → CAMS…", "loading");
  try {
    await api("/cases", {
      method: "POST",
      body: JSON.stringify({ case_id: id, title: id, description: "" }),
    });
    const result = await api(`/cases/${encodeURIComponent(id)}/text`, {
      method: "POST",
      body: JSON.stringify({
        text,
        source: $("source").value,
        source_type: $("sourceType").value,
        force_fallback: $("forceFallback").checked,
      }),
    });
    renderExtract(result.extraction);
    renderObservations([
      ...(result.observations_created || []),
    ]);
    renderCamsAndDecisions(result.decisions || []);
    renderTwin(result.facts || {});
    renderConflicts(result.conflicts || {});
    setStatus(
      `Saved. Extractor=${result.extraction?.extractor}. Observations+=${(result.observations_created || []).length}`,
      "ok"
    );
    await refreshAll();
  } catch (e) {
    setStatus(String(e), "error");
  }
}

async function runDemo(name) {
  setStatus(`Running demo “${name}”…`, "loading");
  try {
    $("caseId").value = "CASE-001";
    const data =
      name === "full"
        ? await api("/demo/case-001", { method: "POST" })
        : await api(`/demo/scenario/${encodeURIComponent(name)}?case_id=CASE-001`, {
            method: "POST",
          });

    // Show last extraction batch if present
    const steps = data.steps || [];
    const last = steps.length
      ? steps[steps.length - 1].result
      : data.result || (data.results || [])[(data.results || []).length - 1];
    if (last?.extraction) renderExtract(last.extraction);
    if (last?.document?.text) $("lastInput").textContent = last.document.text;

    setStatus(`Demo “${name}” finished — data written under data/cases/CASE-001/`, "ok");
    await refreshAll();
  } catch (e) {
    setStatus(String(e), "error");
  }
}

async function init() {
  try {
    const cfg = await api("/api/config");
    $("camsConfig").textContent = `Backend weights ${JSON.stringify(cfg.weights)} · τ=${cfg.tau} · δ=${cfg.delta}`;
  } catch (_) {}
  try {
    const ev = await api("/api/evaluation");
    $("evalOut").textContent = (ev.note || "") + "\n\n" + (ev.markdown || "Run python evaluate.py");
  } catch (e) {
    $("evalOut").textContent = String(e);
  }

  $("btnCreate").onclick = createCase;
  $("btnSubmit").onclick = submitText;
  $("btnReset").onclick = async () => {
    if (!confirm("Delete all JSON case files under data/cases/?")) return;
    await api("/api/reset", { method: "POST" });
    setStatus("All case files cleared.", "ok");
    $("extractOut").textContent = "Waiting…";
    $("obsOut").textContent = "No observations.";
    $("camsOut").textContent = "No CAMS run.";
    $("decisionOut").textContent = "No decisions.";
    $("twinOut").textContent = "Empty twin.";
    $("provOut").textContent = "No provenance.";
    $("conflictOut").textContent = "No conflicts.";
  };
  document.querySelectorAll("[data-demo]").forEach((btn) => {
    btn.onclick = () => runDemo(btn.dataset.demo);
  });
}

init();
