/*
 * NyayaOS case dashboard — JWT-authenticated, role-aware fetch() client.
 *
 * The token is kept in localStorage (prototype-grade session storage) and
 * sent as `Authorization: Bearer <token>` on every API call. All role
 * gating below is UX only — the backend (rbac.py / users_api.py) is the
 * authority and re-checks every request.
 */
(() => {
  const $ = (id) => document.getElementById(id);
  const TOKEN_KEY = "nyayaos_token";

  let token = localStorage.getItem(TOKEN_KEY) || null;
  let me = null;
  let activeCaseId = null;
  let activeCaseRole = null;
  const caseMetaById = new Map();

  // Per-case-role UX capabilities (subset of rbac.py capabilities).
  const CASE_ROLE_UI = {
    ADMIN:    { upload: false, manageAccess: true,  review: false, submit: false, listSubmissions: true  },
    COURT:    { upload: true,  manageAccess: true,  review: true,  submit: false, listSubmissions: true  },
    POLICE:   { upload: true,  manageAccess: false, review: false, submit: false, listSubmissions: false },
    LAWYER:   { upload: true,  manageAccess: false, review: false, submit: false, listSubmissions: false },
    FORENSIC: { upload: true,  manageAccess: false, review: false, submit: false, listSubmissions: false },
    CITIZEN:  { upload: false, manageAccess: false, review: false, submit: true,  listSubmissions: true  },
  };
  const NO_ROLE_UI = { upload: false, manageAccess: false, review: false, submit: false, listSubmissions: false };
  const ui = () => CASE_ROLE_UI[activeCaseRole] || NO_ROLE_UI;
  const canCreateCase = () => Boolean(me) && (me.system_role === "ADMIN" || me.system_role === "COURT");

  // ---- helpers ----

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

  function errorText(e) {
    return escapeHtml(e && e.message ? e.message : String(e));
  }

  // ---- session ----

  function setSession(tok) {
    token = tok || null;
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  }

  function showLogin(message) {
    $("loginOverlay").hidden = false;
    $("appMain").hidden = true;
    $("userBox").hidden = true;
    $("loginStatus").textContent = message || "";
    $("loginPassword").value = "";
  }

  function clearSession(message) {
    setSession(null);
    me = null;
    activeCaseId = null;
    activeCaseRole = null;
    caseMetaById.clear();
    showLogin(message);
  }

  async function api(path, opts = {}) {
    const headers = new Headers(opts.headers || {});
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const res = await fetch(path, { ...opts, headers });
    let body = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) body = await res.json().catch(() => null);
    else body = await res.text();
    if (res.status === 401) {
      clearSession("Session expired or account deactivated — sign in again.");
      throw new Error("Session expired or account deactivated — sign in again.");
    }
    if (!res.ok) {
      const detail = body && typeof body === "object" ? body.detail || JSON.stringify(body) : body;
      const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
      throw new Error((res.status === 403 ? "Not authorized: " : "") + msg);
    }
    return body;
  }

  // ---- login / logout ----

  async function onLogin(ev) {
    ev.preventDefault();
    const email = $("loginEmail").value.trim();
    const password = $("loginPassword").value;
    $("btnLogin").disabled = true;
    $("loginStatus").textContent = "Signing in…";
    try {
      // Raw fetch: a 401 here means bad credentials, not an expired session.
      const res = await fetch("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const body = await res.json().catch(() => null);
      if (!res.ok || !body || !body.access_token) {
        const detail = body && typeof body === "object" ? body.detail : null;
        $("loginStatus").innerHTML =
          `<span class="err">${escapeHtml(typeof detail === "string" ? detail : "Sign-in failed")}</span>`;
        return;
      }
      setSession(body.access_token);
      await bootAuthenticated();
    } catch (e) {
      $("loginStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    } finally {
      $("btnLogin").disabled = false;
    }
  }

  function renderUser() {
    $("userBox").hidden = false;
    $("userEmail").textContent = me.email;
    $("userRole").textContent = me.system_role;
  }

  async function bootAuthenticated() {
    me = await api("/auth/me");
    renderUser();
    $("loginOverlay").hidden = true;
    $("appMain").hidden = false;
    $("loginStatus").textContent = "";
    applyGlobalUi();
    await refreshCaseList();
    if (me.system_role === "ADMIN") await loadUsers();
    const deep = new URLSearchParams(location.search).get("case");
    if (deep) {
      $("caseSelect").value = deep;
      if ($("caseSelect").value === deep) await openCase(deep);
      else $("caseStatus").textContent = `Case ${deep} is not visible for this account.`;
    }
  }

  // ---- role-aware panel visibility (UX only) ----

  function applyGlobalUi() {
    $("createCaseRow").hidden = !canCreateCase();
    $("usersSection").hidden = me.system_role !== "ADMIN";
    $("caseHint").textContent =
      me.system_role === "ADMIN"
        ? "ADMIN sees every case read-only: ingestion, uploads and Twin changes stay with case roles."
        : "Only cases where an ACTIVE case_access row grants your role are listed.";
  }

  function applyCaseUi() {
    const u = ui();
    const hasCase = Boolean(activeCaseId);
    $("uploadSection").hidden = !(hasCase && u.upload);
    $("visibilityRow").hidden = !(hasCase && activeCaseRole === "COURT");
    $("documentsSection").hidden = !hasCase;
    $("submissionSection").hidden = !(hasCase && (u.submit || u.listSubmissions));
    $("submissionCreate").hidden = !(hasCase && u.submit);
    $("submissionCreateText").hidden = !(hasCase && u.submit);
    $("reviewRow").hidden = !(hasCase && u.review);
    $("accessSection").hidden = !(hasCase && u.manageAccess);
    $("submissionHint").textContent = u.submit
      ? "Your statement goes to the court for review before it enters the case record."
      : u.review
        ? "Approving a submission ingests it through the same extraction/CAMS pipeline."
        : "Submission statements are reviewed by the court before entering the case record.";
  }

  function setActive(caseId, storageHint) {
    activeCaseId = caseId || null;
    const line = $("activeCaseLine");
    if (!activeCaseId) {
      activeCaseRole = null;
      line.textContent = "No case selected.";
      $("storageHint").textContent = "data/cases/";
      applyCaseUi();
      return;
    }
    const meta = caseMetaById.get(activeCaseId) || {};
    activeCaseRole = meta.role || null;
    const path = storageHint || `data/cases/${activeCaseId}/`;
    line.innerHTML =
      `Active: <strong class="mono">${escapeHtml(activeCaseId)}</strong>` +
      (activeCaseRole ? ` · case role <span class="badge plain">${escapeHtml(activeCaseRole)}</span>` : "") +
      ` · <span class="mono">${escapeHtml(path)}</span>`;
    $("storageHint").textContent = path;
    applyCaseUi();
  }

  // ---- cases ----

  async function refreshCaseList() {
    const cases = await api("/cases");
    caseMetaById.clear();
    const sel = $("caseSelect");
    const prev = sel.value || activeCaseId || "";
    sel.innerHTML = '<option value="">— select —</option>';
    for (const c of cases) {
      caseMetaById.set(c.case_id, c);
      const opt = document.createElement("option");
      opt.value = c.case_id;
      opt.textContent = `${c.case_id}${c.title ? " — " + c.title : ""}${c.role ? " · " + c.role : ""}`;
      sel.appendChild(opt);
    }
    if (prev) sel.value = prev;
    $("caseStatus").textContent = cases.length
      ? `${cases.length} case(s) visible to ${me.email} (${me.system_role}).`
      : "No cases visible for this account yet.";
    return cases;
  }

  async function createCase() {
    const case_id = $("newCaseId").value.trim() || null;
    const title = $("newCaseTitle").value.trim();
    if (!title) {
      $("caseStatus").innerHTML = '<span class="err">Enter a case title first.</span>';
      $("newCaseTitle").focus();
      return;
    }
    const description = $("newCaseDescription").value.trim();
    $("caseStatus").textContent = "Creating…";
    try {
      const meta = await api("/cases", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id, title, description }),
      });
      await refreshCaseList();
      $("caseSelect").value = meta.case_id;
      await openCase(meta.case_id);
      $("caseStatus").innerHTML = `<span class="ok">Created ${escapeHtml(meta.case_id)}</span>`;
    } catch (e) {
      $("caseStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    }
  }

  async function openCase(caseId) {
    setActive(caseId);
    $("uploadResult").hidden = true;
    $("reviewResult").hidden = true;
    $("uploadStatus").textContent = "";
    $("submissionStatus").textContent = "";
    $("accessStatus").textContent = "";
    $("usersStatus").textContent = "";
    await Promise.all([
      loadFull(caseId),
      loadDocuments(caseId),
      ui().listSubmissions ? loadSubmissions(caseId) : null,
      ui().manageAccess ? loadAccess(caseId) : null,
    ]);
  }

  async function openSelected() {
    const id = $("caseSelect").value;
    if (!id) {
      alert("Select a case first.");
      return;
    }
    await openCase(id);
  }

  // ---- twin ----

  function renderTwin(view) {
    const twin = view.twin || {};
    const conflicts = view.conflicts || {};
    const summary = view.summary || {};

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

    const parts = [...keys].sort().map((key) => {
      const fact = twin[key] || {};
      const conflict = conflicts[key];
      const unresolved =
        Boolean(conflict) || String(fact.status || "").toLowerCase() === "unresolved";
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
            `<li><span class="mono">${escapeHtml(p.source_type || "")}/${escapeHtml(p.source || "")}</span>` +
            ` → <span class="mono">${escapeHtml(JSON.stringify(p.value))}</span></li>`
        )
        .join("");

      return `
        <details class="twin-part">
          <summary>
            <span class="mono twin-key">${escapeHtml(key)}</span>
            <span class="mono twin-val">${escapeHtml(JSON.stringify(fact.value ?? null))}</span>
            ${statusBadge}
          </summary>
          <div class="twin-detail">
            <div class="twin-grid">
              <span class="k">Confidence</span><span class="mono">${fmtConf(fact.confidence)}</span>
              <span class="k">Status</span><span>${escapeHtml(fact.status || "—")}</span>
            </div>
            ${conflictHtml}
            <div class="twin-sources">
              <div class="k">Supporting sources</div>
              ${provenance ? `<ul>${provenance}</ul>` : '<div class="mono">—</div>'}
            </div>
          </div>
        </details>`;
    });

    $("twinBody").innerHTML =
      '<p class="hint">Click a part to expand its details.</p>' +
      `<div class="twin-parts">${parts.join("")}</div>`;
  }

  async function loadFull(caseId) {
    $("twinBody").innerHTML = '<p class="empty">Loading…</p>';
    try {
      const view = await api(`/cases/${encodeURIComponent(caseId)}/full`);
      renderTwin(view);
    } catch (e) {
      $("twinSummary").textContent = "Could not load Twin.";
      $("twinBody").innerHTML = `<p class="err">${errorText(e)}</p>`;
    }
  }

  // ---- documents ----

  async function loadDocuments(caseId) {
    $("documentsBody").innerHTML = '<p class="empty">Loading…</p>';
    try {
      const data = await api(`/cases/${encodeURIComponent(caseId)}/documents`);
      renderDocuments(data.documents || []);
    } catch (e) {
      $("documentsBody").innerHTML = `<p class="err">${errorText(e)}</p>`;
    }
  }

  function renderDocuments(docs) {
    if (!docs.length) {
      $("documentsSummary").textContent = "No documents recorded for this case.";
      $("documentsBody").innerHTML = '<p class="empty">No documents.</p>';
      return;
    }
    $("documentsSummary").textContent =
      activeCaseRole === "CITIZEN"
        ? `${docs.length} document(s) shared with citizens on this case.`
        : `${docs.length} document(s) recorded for this case.`;
    const rows = docs
      .map((d) => {
        const visibility = d.visibility || "INTERNAL";
        return `
        <tr>
          <td class="mono">${escapeHtml(d.title || d.document_id || "(untitled)")}</td>
          <td class="mono">${escapeHtml(d.source_type || "")}/${escapeHtml(d.source_id || "")}</td>
          <td><span class="badge ${visibility === "CITIZEN_VISIBLE" ? "CITIZEN_VISIBLE" : "plain"}">${escapeHtml(visibility)}</span></td>
          <td class="mono" style="font-size:0.75rem">${escapeHtml(d.ingestion_time || "")}</td>
        </tr>`;
      })
      .join("");
    $("documentsBody").innerHTML = `
      <table class="facts">
        <thead><tr><th>Title</th><th>Source</th><th>Visibility</th><th>Ingested</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  // ---- upload / ingest ----

  function requestedVisibility() {
    if (activeCaseRole !== "COURT") return null;
    return $("markVisible").checked ? "CITIZEN_VISIBLE" : "INTERNAL";
  }

  function renderIngestResult(result, boxId) {
    const box = $(boxId || "uploadResult");
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

  async function uploadFile() {
    if (!activeCaseId) {
      alert("Open or create a case first.");
      return;
    }
    if (!ui().upload) return;
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
      fd.append("force_fallback", $("forceFallback").value);
      fd.append("title", file.name);
      const visibility = requestedVisibility();
      if (visibility) fd.append("visibility", visibility);
      const result = await api(`/cases/${encodeURIComponent(activeCaseId)}/upload`, {
        method: "POST",
        body: fd,
      });
      renderIngestResult(result);
      $("uploadStatus").innerHTML =
        '<span class="ok">Upload complete — twin refreshed.</span> <span class="hint">(source identity taken from your case role)</span>';
      await Promise.all([loadFull(activeCaseId), loadDocuments(activeCaseId)]);
      $("fileInput").value = "";
    } catch (e) {
      $("uploadStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    } finally {
      $("btnUpload").disabled = false;
    }
  }

  async function ingestPaste() {
    if (!activeCaseId) {
      alert("Open or create a case first.");
      return;
    }
    if (!ui().upload) return;
    const text = $("pasteText").value.trim();
    if (!text) {
      alert("Paste some text first.");
      return;
    }
    $("uploadStatus").textContent = "Ingesting text…";
    $("btnPasteText").disabled = true;
    try {
      const firstLine = text.split(/\r?\n/).map((l) => l.replace(/\s+/g, " ").trim()).find(Boolean) || "";
      const derivedTitle = firstLine.length > 60 ? `${firstLine.slice(0, 57).trimEnd()}…` : firstLine;
      const payload = {
        text,
        force_fallback: $("forceFallback").value === "true",
        title: derivedTitle,
      };
      const visibility = requestedVisibility();
      if (visibility) payload.visibility = visibility;
      const result = await api(`/cases/${encodeURIComponent(activeCaseId)}/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderIngestResult(result);
      $("uploadStatus").innerHTML = '<span class="ok">Text ingested — twin refreshed.</span>';
      await Promise.all([loadFull(activeCaseId), loadDocuments(activeCaseId)]);
    } catch (e) {
      $("uploadStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    } finally {
      $("btnPasteText").disabled = false;
    }
  }

  // ---- submissions ----

  async function loadSubmissions(caseId) {
    $("submissionsBody").innerHTML = '<p class="empty">Loading…</p>';
    try {
      const data = await api(`/cases/${encodeURIComponent(caseId)}/submissions`);
      renderSubmissions(data.submissions || []);
    } catch (e) {
      $("submissionsBody").innerHTML = `<p class="err">${errorText(e)}</p>`;
    }
  }

  function renderSubmissions(subs) {
    if (!subs.length) {
      $("submissionsBody").innerHTML = '<p class="empty">No submissions.</p>';
      return;
    }
    const rows = subs
      .map((s) => {
        const reviewable = ui().review && s.status === "PENDING";
        const actions = reviewable
          ? `<button type="button" class="tiny" data-review="APPROVE" data-sub="${escapeHtml(s.submission_id)}">Approve</button>
             <button type="button" class="tiny danger" data-review="REJECT" data-sub="${escapeHtml(s.submission_id)}">Reject</button>`
          : s.review_note
            ? escapeHtml(s.review_note)
            : "—";
        return `
        <tr>
          <td class="mono">${escapeHtml(s.title || "(untitled)")}</td>
          <td class="mono" style="font-size:0.75rem">${escapeHtml(s.submitted_by_email || "")}</td>
          <td><span class="badge ${escapeHtml(s.status || "")}">${escapeHtml(s.status || "")}</span></td>
          <td class="mono" style="font-size:0.75rem">${escapeHtml(s.created_at || "")}</td>
          <td>${actions}
            <details style="margin-top:0.3rem">
              <summary class="mono" style="font-size:0.75rem">statement</summary>
              <div class="mono" style="white-space:pre-wrap;font-size:0.78rem">${escapeHtml(s.text || "")}</div>
            </details>
          </td>
        </tr>`;
      })
      .join("");
    $("submissionsBody").innerHTML = `
      <table class="facts">
        <thead><tr><th>Title</th><th>From</th><th>Status</th><th>Created</th><th>Statement / review</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  async function reviewSubmission(submissionId, decision) {
    if (!activeCaseId || !ui().review) return;
    $("submissionStatus").textContent = decision === "APPROVE" ? "Approving…" : "Rejecting…";
    try {
      const note = $("reviewNote").value.trim();
      const out = await api(
        `/cases/${encodeURIComponent(activeCaseId)}/submissions/${encodeURIComponent(submissionId)}/review`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision, note: note || null }),
        }
      );
      $("submissionStatus").innerHTML = `<span class="ok">${escapeHtml(decision)} recorded.</span>`;
      if (out && out.ingestion) renderIngestResult(out.ingestion, "reviewResult");
      await Promise.all([loadSubmissions(activeCaseId), loadFull(activeCaseId)]);
    } catch (e) {
      $("submissionStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    }
  }

  async function createSubmission() {
    if (!activeCaseId || !ui().submit) return;
    const text = $("submissionText").value.trim();
    if (!text) {
      alert("Write your statement first.");
      return;
    }
    $("btnCreateSubmission").disabled = true;
    $("submissionStatus").textContent = "Submitting…";
    try {
      await api(`/cases/${encodeURIComponent(activeCaseId)}/submissions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: $("submissionTitle").value.trim(), text }),
      });
      $("submissionText").value = "";
      $("submissionTitle").value = "";
      $("submissionStatus").innerHTML = '<span class="ok">Submitted — pending court review.</span>';
      await loadSubmissions(activeCaseId);
    } catch (e) {
      $("submissionStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    } finally {
      $("btnCreateSubmission").disabled = false;
    }
  }

  // ---- case access ----

  async function loadAccess(caseId) {
    $("accessBody").innerHTML = '<p class="empty">Loading…</p>';
    try {
      const data = await api(`/cases/${encodeURIComponent(caseId)}/access`);
      renderAccess(data.access || []);
    } catch (e) {
      $("accessBody").innerHTML = `<p class="err">${errorText(e)}</p>`;
    }
  }

  function renderAccess(rows) {
    if (!rows.length) {
      $("accessBody").innerHTML = '<p class="empty">No access rows for this case.</p>';
      return;
    }
    const body = rows
      .map((a) => {
        const revoke =
          a.status === "ACTIVE"
            ? `<button type="button" class="tiny danger" data-revoke="${escapeHtml(a.user_id)}" data-email="${escapeHtml(a.email)}">Revoke</button>`
            : "—";
        return `
        <tr>
          <td class="mono">${escapeHtml(a.email)}</td>
          <td>${escapeHtml(a.case_role)}</td>
          <td><span class="badge ${escapeHtml(a.status)}">${escapeHtml(a.status)}</span></td>
          <td class="mono" style="font-size:0.75rem">${escapeHtml(a.granted_by || "")}</td>
          <td>${revoke}</td>
        </tr>`;
      })
      .join("");
    $("accessBody").innerHTML = `
      <table class="facts">
        <thead><tr><th>User</th><th>Case role</th><th>Status</th><th>Granted by</th><th></th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  async function grantAccess() {
    if (!activeCaseId || !ui().manageAccess) return;
    const email = $("grantEmail").value.trim();
    const case_role = $("grantRole").value;
    if (!email) {
      alert("Enter the user's email.");
      return;
    }
    $("btnGrant").disabled = true;
    $("accessStatus").textContent = "Granting…";
    try {
      await api(`/cases/${encodeURIComponent(activeCaseId)}/access`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, case_role }),
      });
      $("grantEmail").value = "";
      $("accessStatus").innerHTML = `<span class="ok">Granted ${escapeHtml(case_role)} to ${escapeHtml(email)}.</span>`;
      await loadAccess(activeCaseId);
    } catch (e) {
      $("accessStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    } finally {
      $("btnGrant").disabled = false;
    }
  }

  async function revokeAccess(userId, email) {
    if (!activeCaseId || !ui().manageAccess) return;
    if (!confirm(`Revoke case access for ${email}?`)) return;
    try {
      await api(`/cases/${encodeURIComponent(activeCaseId)}/access/${encodeURIComponent(userId)}`, {
        method: "DELETE",
      });
      $("accessStatus").innerHTML = `<span class="ok">Access revoked for ${escapeHtml(email)}.</span>`;
      await loadAccess(activeCaseId);
    } catch (e) {
      $("accessStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    }
  }

  // ---- user management (ADMIN) ----

  async function loadUsers() {
    $("usersBody").innerHTML = '<p class="empty">Loading…</p>';
    try {
      const data = await api("/users");
      renderUsers(data.users || []);
    } catch (e) {
      $("usersBody").innerHTML = `<p class="err">${errorText(e)}</p>`;
    }
  }

  function renderUsers(users) {
    if (!users.length) {
      $("usersBody").innerHTML = '<p class="empty">No users.</p>';
      return;
    }
    const body = users
      .map((u) => {
        const self = me && u.id === me.id;
        const toggle = u.is_active
          ? `<button type="button" class="tiny danger" data-toggle="${escapeHtml(u.id)}" data-active="false" data-email="${escapeHtml(u.email)}" ${self ? "disabled" : ""}>Deactivate</button>`
          : `<button type="button" class="tiny" data-toggle="${escapeHtml(u.id)}" data-active="true" data-email="${escapeHtml(u.email)}">Activate</button>`;
        return `
        <tr>
          <td class="mono">${escapeHtml(u.email)}${self ? ' <span class="badge plain">you</span>' : ""}</td>
          <td>${escapeHtml(u.system_role)}</td>
          <td><span class="badge ${u.is_active ? "ACTIVE" : "REVOKED"}">${u.is_active ? "ACTIVE" : "INACTIVE"}</span></td>
          <td class="mono" style="font-size:0.75rem">${escapeHtml(u.created_at || "")}</td>
          <td>${toggle}
            <button type="button" class="tiny secondary" data-password="${escapeHtml(u.id)}" data-email="${escapeHtml(u.email)}">Reset password</button>
          </td>
        </tr>`;
      })
      .join("");
    $("usersBody").innerHTML = `
      <table class="facts">
        <thead><tr><th>Email</th><th>System role</th><th>Status</th><th>Created</th><th></th></tr></thead>
        <tbody>${body}</tbody>
      </table>`;
  }

  async function createUser() {
    const email = $("newUserEmail").value.trim();
    const password = $("newUserPassword").value;
    const system_role = $("newUserRole").value;
    if (!email || !password) {
      alert("Email and password are required.");
      return;
    }
    $("btnCreateUser").disabled = true;
    $("usersStatus").textContent = "Creating…";
    try {
      const out = await api("/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password, system_role }),
      });
      $("newUserEmail").value = "";
      $("newUserPassword").value = "";
      $("usersStatus").innerHTML = `<span class="ok">Created ${escapeHtml(out.user?.email || email)} (${escapeHtml(system_role)}).</span>`;
      await loadUsers();
    } catch (e) {
      $("usersStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    } finally {
      $("btnCreateUser").disabled = false;
    }
  }

  async function toggleUser(userId, active, email) {
    if (!me || me.system_role !== "ADMIN") return;
    if (!active && !confirm(`Deactivate ${email}? They lose sign-in and existing tokens.`)) return;
    try {
      await api(`/users/${encodeURIComponent(userId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: active }),
      });
      $("usersStatus").innerHTML = `<span class="ok">${escapeHtml(email)} is now ${active ? "active" : "inactive"}.</span>`;
      await loadUsers();
    } catch (e) {
      $("usersStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    }
  }

  async function resetPassword(userId, email) {
    if (!me || me.system_role !== "ADMIN") return;
    const password = prompt(`New password for ${email} (min 8 chars):`);
    if (password == null) return;
    if (password.length < 8) {
      $("usersStatus").innerHTML = '<span class="err">Password must be at least 8 characters.</span>';
      return;
    }
    try {
      await api(`/users/${encodeURIComponent(userId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      $("usersStatus").innerHTML = `<span class="ok">Password updated for ${escapeHtml(email)}.</span>`;
    } catch (e) {
      $("usersStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    }
  }

  // ---- wiring ----

  $("loginForm").addEventListener("submit", onLogin);
  $("btnLogout").addEventListener("click", () => clearSession("Signed out."));
  $("btnRefreshCases").addEventListener("click", () =>
    refreshCaseList().catch((e) => {
      $("caseStatus").innerHTML = `<span class="err">${errorText(e)}</span>`;
    })
  );
  $("btnCreateCase").addEventListener("click", () => createCase());
  $("btnOpenCase").addEventListener("click", () => openSelected());
  $("caseSelect").addEventListener("change", () => {
    if ($("caseSelect").value) openSelected();
  });
  $("btnUpload").addEventListener("click", () => uploadFile());
  $("btnPasteText").addEventListener("click", () => ingestPaste());
  $("btnCreateSubmission").addEventListener("click", () => createSubmission());
  $("btnGrant").addEventListener("click", () => grantAccess());
  $("btnCreateUser").addEventListener("click", () => createUser());

  $("submissionsBody").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-review]");
    if (btn) reviewSubmission(btn.dataset.sub, btn.dataset.review);
  });
  $("accessBody").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-revoke]");
    if (btn) revokeAccess(btn.dataset.revoke, btn.dataset.email);
  });
  $("usersBody").addEventListener("click", (ev) => {
    const toggle = ev.target.closest("button[data-toggle]");
    if (toggle) {
      toggleUser(toggle.dataset.toggle, toggle.dataset.active === "true", toggle.dataset.email);
      return;
    }
    const pw = ev.target.closest("button[data-password]");
    if (pw) resetPassword(pw.dataset.password, pw.dataset.email);
  });

  // ---- boot ----

  (async function boot() {
    if (!token) {
      showLogin("");
      return;
    }
    try {
      await bootAuthenticated();
    } catch (e) {
      if (token) {
        clearSession("Session expired or account deactivated — sign in again.");
      }
    }
  })();
})();
