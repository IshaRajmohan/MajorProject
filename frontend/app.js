/* NyayaOS case dashboard — thin fetch() client over the FastAPI case APIs. */
(() => {
  const $ = (id) => document.getElementById(id);

  let activeCaseId = null;

  function setActive(caseId, storageHint) {
    activeCaseId = caseId || null;
    const line = $("activeCaseLine");
    if (!activeCaseId) {
      line.textContent = "No case selected.";
      $("storageHint").textContent = "data/cases/";
      return;
    }
    const path = storageHint || `data/cases/${activeCaseId}/`;
    line.innerHTML = `Active: <strong class="mono">${escapeHtml(activeCaseId)}</strong> · <span class="mono">${escapeHtml(path)}</span>`;
    $("storageHint").textContent = path;
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtConf(c) {
    if (c == null || c === "") return "—";
    const n = Number(c);
    return Number.isFinite(n) ? n.toFixed(3) : String(c);
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let body = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      body = await res.json();
    } else {
      body = await res.text();
    }
    if (!res.ok) {
      const detail =
        body && typeof body === "object" ? body.detail || JSON.stringify(body) : body;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }
    return body;
  }

  async function refreshCaseList() {
    const cases = await api("/cases");
    const sel = $("caseSelect");
    const prev = sel.value || activeCaseId || "";
    sel.innerHTML = '<option value="">— select —</option>';
    for (const c of cases) {
      const id = c.case_id;
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = `${id}${c.title ? " — " + c.title : ""}`;
      sel.appendChild(opt);
    }
    if (prev) sel.value = prev;
    return cases;
  }

  function renderTwin(view) {
    const twin = view.twin || {};
    const conflicts = view.conflicts || {};
    const summary = view.summary || {};
    const hint = view.storage_hint || "";

    setActive(view.case?.case_id || activeCaseId, hint);

    $("twinSummary").textContent =
      `${summary.twin_facts ?? Object.keys(twin).length} facts · ` +
      `${summary.conflicts ?? Object.keys(conflicts).length} unresolved · ` +
      `${summary.documents ?? 0} documents · ` +
      `${summary.observations ?? 0} observations`;

    const keys = new Set([...Object.keys(twin), ...Object.keys(conflicts)]);
    if (keys.size === 0) {
      $("twinBody").innerHTML = '<p class="empty">No facts yet — upload a document or paste text.</p>';
      return;
    }

    const rows = [...keys].sort().map((key) => {
      const fact = twin[key] || {};
      const conflict = conflicts[key];
      const unresolved =
        Boolean(conflict) ||
        String(fact.status || "").toLowerCase() === "unresolved";
      const statusBadge = unresolved
        ? '<span class="badge unresolved">UNRESOLVED</span>'
        : '<span class="badge resolved">RESOLVED</span>';

      let conflictHtml = "";
      if (conflict) {
        const expl = conflict.explanation || conflict.reason || "(no explanation)";
        const cands = (conflict.candidates || [])
          .map(
            (c) =>
              `<li><span class="mono">${escapeHtml(JSON.stringify(c.value))}</span> ` +
              `C=${fmtConf(c.confidence)} ` +
              `sources=${escapeHtml((c.supporting_source_ids || []).join(", ") || "—")}</li>`
          )
          .join("");
        conflictHtml = `
          <div class="conflict-box">
            <strong>Conflict</strong>
            <div>${escapeHtml(expl)}</div>
            <div class="mono" style="margin-top:0.25rem">
              previous=${escapeHtml(JSON.stringify(conflict.previous_value))}
              · C1=${fmtConf(conflict.C1)} · C2=${fmtConf(conflict.C2)}
              · margin=${fmtConf(conflict.margin)}
            </div>
            ${cands ? `<ul>${cands}</ul>` : ""}
          </div>`;
      }

      const provenance = (fact.provenance || [])
        .map(
          (p) =>
            `${escapeHtml(p.source_type || "")}/${escapeHtml(p.source || "")}` +
            ` → ${escapeHtml(JSON.stringify(p.value))}`
        )
        .join("; ");

      return `
        <tr>
          <td class="mono">${escapeHtml(key)}</td>
          <td class="mono">${escapeHtml(JSON.stringify(fact.value ?? null))}</td>
          <td class="mono">${fmtConf(fact.confidence)}</td>
          <td>${statusBadge}${conflictHtml}</td>
          <td class="mono" style="font-size:0.75rem">${provenance || "—"}</td>
        </tr>`;
    });

    $("twinBody").innerHTML = `
      <table class="facts">
        <thead>
          <tr>
            <th>Fact</th>
            <th>Value</th>
            <th>Confidence</th>
            <th>Status</th>
            <th>Supporting sources</th>
          </tr>
        </thead>
        <tbody>${rows.join("")}</tbody>
      </table>`;
  }

  async function loadFull(caseId) {
    if (!caseId) return;
    $("twinBody").innerHTML = '<p class="empty">Loading…</p>';
    const view = await api(`/cases/${encodeURIComponent(caseId)}/full`);
    renderTwin(view);
    return view;
  }

  function renderIngestResult(result) {
    const box = $("uploadResult");
    box.hidden = false;
    const decisions = result.decisions || result.history_tail || [];
    const lines = decisions.map((d) => {
      const decided = d.decided ?? d.decision === "ACCEPTED";
      const label = decided ? "ACCEPTED" : "ABSTAINED";
      const val = d.selected_value ?? d.accepted_value;
      return (
        `<li><strong>${escapeHtml(label)}</strong> ` +
        `<span class="mono">${escapeHtml(d.fact_key)}</span> ` +
        `value=${escapeHtml(JSON.stringify(val))} ` +
        `C1=${fmtConf(d.C1)} C2=${fmtConf(d.C2)}` +
        (d.explanation ? `<br/><span>${escapeHtml(d.explanation)}</span>` : "") +
        `</li>`
      );
    });
    const ocrNote = result.ocr
      ? `<p class="hint">OCR: ${escapeHtml(result.ocr.method || "")} — ${escapeHtml(result.ocr.note || "")}</p>`
      : "";
    box.innerHTML =
      `<strong>Last ingest</strong> (${escapeHtml(result.extractor || result.ocr?.method || "pipeline")})` +
      ocrNote +
      (lines.length ? `<ul>${lines.join("")}</ul>` : "<p class='hint'>No CAMS decisions in response.</p>");
  }

  async function createCase() {
    const case_id = $("newCaseId").value.trim() || null;
    const title = $("newCaseTitle").value.trim() || "Untitled case";
    const meta = await api("/cases", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_id, title, description: "Created via web dashboard" }),
    });
    await refreshCaseList();
    $("caseSelect").value = meta.case_id;
    setActive(meta.case_id);
    await loadFull(meta.case_id);
  }

  async function openSelected() {
    const id = $("caseSelect").value;
    if (!id) {
      alert("Select a case first.");
      return;
    }
    setActive(id);
    await loadFull(id);
  }

  async function uploadFile() {
    if (!activeCaseId) {
      alert("Open or create a case first.");
      return;
    }
    const file = $("fileInput").files?.[0];
    if (!file) {
      alert("Choose a file.");
      return;
    }
    $("uploadStatus").textContent = "Uploading…";
    $("btnUpload").disabled = true;
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("source", $("uploadSource").value.trim() || "user");
      fd.append("source_type", $("uploadSourceType").value);
      fd.append("force_fallback", $("forceFallback").value);
      fd.append("title", file.name);
      const result = await api(`/cases/${encodeURIComponent(activeCaseId)}/upload`, {
        method: "POST",
        body: fd,
      });
      renderIngestResult(result);
      $("uploadStatus").innerHTML = '<span class="ok">Upload complete — twin refreshed.</span>';
      await loadFull(activeCaseId);
      $("fileInput").value = "";
    } catch (e) {
      $("uploadStatus").innerHTML = `<span class="err">${escapeHtml(e.message)}</span>`;
    } finally {
      $("btnUpload").disabled = false;
    }
  }

  async function ingestPaste() {
    if (!activeCaseId) {
      alert("Open or create a case first.");
      return;
    }
    const text = $("pasteText").value.trim();
    if (!text) {
      alert("Paste some text first.");
      return;
    }
    $("uploadStatus").textContent = "Ingesting text…";
    $("btnPasteText").disabled = true;
    try {
      const result = await api(`/cases/${encodeURIComponent(activeCaseId)}/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          source: $("uploadSource").value.trim() || "user",
          source_type: $("uploadSourceType").value,
          force_fallback: $("forceFallback").value === "true",
          title: "web-paste",
        }),
      });
      renderIngestResult(result);
      $("uploadStatus").innerHTML = '<span class="ok">Text ingested — twin refreshed.</span>';
      await loadFull(activeCaseId);
    } catch (e) {
      $("uploadStatus").innerHTML = `<span class="err">${escapeHtml(e.message)}</span>`;
    } finally {
      $("btnPasteText").disabled = false;
    }
  }

  $("btnRefreshCases").addEventListener("click", () =>
    refreshCaseList().catch((e) => alert(e.message))
  );
  $("btnCreateCase").addEventListener("click", () => createCase().catch((e) => alert(e.message)));
  $("btnOpenCase").addEventListener("click", () => openSelected().catch((e) => alert(e.message)));
  $("caseSelect").addEventListener("change", () => {
    if ($("caseSelect").value) openSelected().catch((e) => alert(e.message));
  });
  $("btnUpload").addEventListener("click", () => uploadFile());
  $("btnPasteText").addEventListener("click", () => ingestPaste());

  // Deep-link: /?case=CASE_ID
  const params = new URLSearchParams(location.search);
  const deep = params.get("case");

  refreshCaseList()
    .then(async () => {
      if (deep) {
        $("caseSelect").value = deep;
        setActive(deep);
        await loadFull(deep);
      }
    })
    .catch((e) => {
      $("twinBody").innerHTML = `<p class="err">API error: ${escapeHtml(e.message)}</p>`;
    });
})();
