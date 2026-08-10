(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = String(text);
    return element;
  };

  const commandViews = {
    analyze: "analyze", match: "match", tsearch: "transform", combo: "combo",
    status: "database", sync: "database", "build-index": "database", "optimize-db": "database",
    bfetch: "bfiles", bindex: "bfiles", bsearch: "bfiles", selfcheck: "selfcheck"
  };
  const sectionDefinitions = [
    ["ranked_explanations", "Top ranked explanations", "explanation"],
    ["matches", "Matches", "match"],
    ["exact_matches", "Direct matches", "exact"],
    ["transform_matches", "Transform matches", "transform"],
    ["similarity", "Similarity candidates", "similarity"],
    ["combinations", "Linear pairs", "combo"],
    ["triple_combinations", "Linear triples", "combo"],
    ["modclass_combinations", "Mod-class decompositions", "modclass"],
    ["pointwise_combinations", "Pointwise decompositions", "pointwise"],
    ["convolution_combinations", "Convolution decompositions", "convolution"],
    ["results", "Trial results", "trial"]
  ];
  const state = { activeJob: null, activeForm: null, pollTimer: null, progressTimer: null, lastOutput: null, lastJob: null };

  async function request(path, options = {}) {
    const response = await fetch(path, { cache: "no-store", ...options });
    const text = await response.text();
    let payload = null;
    if (text) {
      try { payload = JSON.parse(text); }
      catch { payload = text; }
    }
    if (!response.ok) {
      const message = payload && typeof payload === "object" ? payload.error : payload;
      throw new Error(message || `Request failed (${response.status})`);
    }
    return payload;
  }

  function toast(message, kind = "ok") {
    const item = node("div", `toast${kind === "error" ? " error" : ""}`, message);
    $("#toasts").append(item);
    window.setTimeout(() => item.remove(), 4200);
  }

  function switchView(name, focus = false) {
    const view = $(`#view-${name}`);
    if (!view) return;
    $$(".view").forEach(element => element.classList.toggle("active", element === view));
    $$(".sidebar nav .nav-link").forEach(button => button.classList.toggle("active", button.dataset.view === name));
    $("#view-title").textContent = view.dataset.title || name;
    window.history.replaceState(null, "", `#${name}`);
    if (focus) window.setTimeout(() => $("textarea, input", view)?.focus(), 0);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function termCount(text) {
    if (!text.trim()) return "0 terms";
    if (/(^|\s)[a-z-]+(?:@\d+)?:/i.test(text)) return "Fielded query";
    const tokens = text.trim().split(/[\s,]+/).filter(Boolean);
    const unknown = tokens.filter(token => token === "?" || token === "*").length;
    const invalid = tokens.filter(token => !/^[+-]?\d+$/.test(token) && token !== "?" && token !== "*").length;
    return `${tokens.length} terms${unknown ? ` · ${unknown} unknown` : ""}${invalid ? ` · ${invalid} invalid` : ""}`;
  }

  function updateTermCount(textarea) {
    const field = textarea.closest(".sequence-field");
    if (!field) return;
    const output = $(".term-count", field);
    if (output) output.textContent = `${termCount(textarea.value)}${textarea.id === "combo-sequence" ? " · five or more recommended" : ""}`;
  }

  function buildArgs(form) {
    const args = [];
    const positionals = $$('[data-positional]', form).map(input => input.value.trim()).filter(Boolean);
    const preset = $('input[name="preset"]:checked', form);
    if (preset) args.push(`--${preset.value}`);
    $$('[data-flag]', form).forEach(input => {
      const flag = input.dataset.flag;
      if (!flag) return;
      if (input.type === "checkbox") {
        if (input.checked) args.push(flag);
      } else if (input.value.trim() !== "") {
        args.push(`${flag}=${input.value.trim()}`);
      }
    });
    if (form.dataset.command === "analyze") {
      [["--pointwise-ops", "--pointwise-limit", "10"], ["--convolution-ops", "--convolution-limit", "5"]].forEach(([opsFlag, limitFlag, fallback]) => {
        const ops = $(`[data-flag="${opsFlag}"]`, form);
        const limit = $(`[data-flag="${limitFlag}"]`, form);
        if (ops?.value.trim() && !limit?.value.trim()) args.push(`${limitFlag}=${fallback}`);
      });
    }
    $$('[data-unchecked-flag]', form).forEach(input => {
      if (!input.checked && input.dataset.uncheckedFlag) args.push(input.dataset.uncheckedFlag);
    });
    if (positionals.length) args.push("--", ...positionals);
    return args;
  }

  function isFieldedMatch(command, text) {
    return command === "match" && /(?:^|\s)(?:id|name|formula|keyword|sign|monotonic|has-?formula|contains|excludes|term@\d+):/i.test(text);
  }

  function validateSearchInput(form) {
    const command = form.dataset.command;
    if (!["match", "tsearch", "combo", "analyze"].includes(command)) return true;
    if (command === "analyze") {
      const checkpoint = $('[data-flag="--checkpoint"]', form);
      checkpoint.setCustomValidity("");
      if ($('[data-flag="--resume"]', form)?.checked && !checkpoint.value.trim()) {
        checkpoint.setCustomValidity("Choose a checkpoint path before resuming.");
        checkpoint.reportValidity();
        return false;
      }
    }
    const input = $("[data-positional]", form);
    const text = input.value.trim();
    input.setCustomValidity("");
    if (isFieldedMatch(command, text)) return true;
    const tokens = text.split(/[\s,]+/).filter(Boolean);
    const invalid = tokens.filter(token => !/^[+-]?\d+$/.test(token) && token !== "?" && token !== "*");
    const wildcards = tokens.filter(token => token === "?" || token === "*").length;
    let message = "";
    if (invalid.length) message = `Invalid term${invalid.length === 1 ? "" : "s"}: ${invalid.slice(0, 3).join(", ")}. Use integers, ? or *.`;
    else if (tokens.length < 3) message = "Enter at least 3 sequence terms.";
    else if (wildcards > 3) message = "Use at most 3 unknown terms.";
    else if (wildcards / tokens.length > 0.5) message = "Unknown terms cannot be more than half of the sequence.";
    if (!message) return true;
    input.setCustomValidity(message);
    input.reportValidity();
    return false;
  }

  function setFormRunning(form, running) {
    if (!form) return;
    const submit = $('[type="submit"]', form);
    if (submit) {
      submit.disabled = running;
      submit.classList.toggle("running", running);
    }
    form.setAttribute("aria-busy", String(running));
  }

  function showProgress(job) {
    const panel = $("#job-panel");
    panel.hidden = false;
    $("#job-title").textContent = `${job.command} is running…`;
    $("#job-detail").textContent = "Starting the local command";
    clearInterval(state.progressTimer);
    const started = Date.now();
    state.progressTimer = window.setInterval(() => {
      const seconds = Math.max(0, (Date.now() - started) / 1000);
      $("#job-detail").textContent = `Running locally · ${Math.floor(seconds)}s elapsed`;
    }, 700);
  }

  async function startJob(form) {
    if (state.activeJob) return toast("Another local job is already running.", "error");
    if (!validateSearchInput(form) || !form.reportValidity()) return;
    const command = form.dataset.command;
    const args = buildArgs(form);
    state.activeForm = form;
    setFormRunning(form, true);
    $("#results").hidden = true;
    try {
      const job = await request("/api/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command, args })
      });
      state.activeJob = job.id;
      showProgress(job);
      pollJob(job.id);
    } catch (error) {
      setFormRunning(form, false);
      state.activeForm = null;
      toast(error.message, "error");
    }
  }

  async function pollJob(id) {
    clearTimeout(state.pollTimer);
    try {
      const job = await request(`/api/jobs/${encodeURIComponent(id)}`);
      if (job.status === "running") {
        state.pollTimer = window.setTimeout(() => pollJob(id), 650);
        return;
      }
      finishJob(job);
    } catch (error) {
      clearInterval(state.progressTimer);
      state.activeJob = null;
      setFormRunning(state.activeForm, false);
      state.activeForm = null;
      $("#job-panel").hidden = true;
      toast(error.message, "error");
    }
  }

  function finishJob(job) {
    if (state.lastJob?.id === job.id && !state.activeJob) return;
    clearTimeout(state.pollTimer);
    clearInterval(state.progressTimer);
    window.setTimeout(() => { $("#job-panel").hidden = true; }, 350);
    setFormRunning(state.activeForm, false);
    state.activeForm = null;
    state.activeJob = null;
    state.lastJob = job;
    state.lastOutput = job.output;
    renderJob(job);
    addHistory(job);
    if (job.status === "completed") toast(`${job.command} completed.`);
    else if (job.status === "cancelled") toast(`${job.command} was cancelled.`, "error");
    else toast(job.stderr || `${job.command} failed.`, "error");
    if (["status", "sync", "build-index", "optimize-db"].includes(job.command)) loadStatus();
  }

  function displayValue(value) {
    if (value === null || value === undefined || value === "") return "—";
    if (typeof value === "boolean") return value ? "yes" : "no";
    if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString() : value.toPrecision(5).replace(/\.?0+$/, "");
    if (Array.isArray(value)) return value.map(displayValue).join(", ");
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  }

  function validId(value) { return typeof value === "string" && /^A\d{6}$/.test(value); }

  function appendId(parent, id) {
    if (!validId(id)) {
      parent.append(document.createTextNode(String(id)));
      return;
    }
    const link = node("a", "", id);
    link.href = `https://oeis.org/${id}`;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    parent.append(link);
  }

  function familyName(row, fallback) {
    const raw = row.family || (row.transform || row.transform_desc ? "transform" : fallback);
    return String(raw || "result").replaceAll("_", " ");
  }

  function appendDetails(parent, values) {
    const entries = Object.entries(values).filter(([, value]) => value !== null && value !== undefined && value !== "" && (!Array.isArray(value) || value.length));
    if (!entries.length) return;
    const details = node("details", "result-details");
    details.append(node("summary", "", "Details"));
    const body = node("div", "detail-list");
    entries.forEach(([label, value]) => {
      const row = node("div");
      row.append(node("b", "", label.replaceAll("_", " ")), node("span", "", typeof value === "object" ? JSON.stringify(value) : displayValue(value)));
      body.append(row);
    });
    details.append(body);
    parent.append(details);
  }

  function makeResultCard(row, index, fallbackFamily) {
    const card = node("article", "result-card");
    card.append(node("div", "rank", row.rank ?? index + 1));
    const main = node("div", "result-main");
    const kicker = node("div", "result-kicker");
    const familyText = familyName(row, fallbackFamily);
    kicker.append(node("span", `family ${familyText.split(" ")[0]}`, familyText));
    const scoreParts = [];
    if (row.score !== undefined && row.score !== null) scoreParts.push(`score ${displayValue(row.score)}`);
    if (row.corr !== undefined) scoreParts.push(`corr ${displayValue(row.corr)}`);
    if (row.ok !== undefined) scoreParts.push(row.ok ? "passed" : "failed");
    if (scoreParts.length) kicker.append(node("span", "score", scoreParts.join(" · ")));
    main.append(kicker);

    const ids = Array.isArray(row.ids) ? row.ids.filter(validId) : (validId(row.id) ? [row.id] : []);
    const names = Array.isArray(row.names) ? row.names.filter(Boolean) : (row.name ? [row.name] : []);
    const title = node("h4");
    const isCombination = ids.length > 1 && row.expression;
    if (isCombination) {
      title.textContent = row.expression;
    } else if (ids.length) {
      ids.forEach((id, i) => {
        if (i) title.append(document.createTextNode(" · "));
        appendId(title, id);
      });
      if (names.length) title.append(document.createTextNode(` — ${names.join(" + ")}`));
    } else {
      title.textContent = row.kind || row.title || row.name || row.expression || row.status || "Result";
    }
    main.append(title);

    if (isCombination) {
      const components = node("p", "expression");
      ids.forEach((id, i) => {
        if (i) components.append(document.createTextNode(" · "));
        appendId(components, id);
        if (row.names?.[i]) components.append(document.createTextNode(` ${row.names[i]}`));
      });
      main.append(components);
    }

    const expression = row.explanation || row.expression || row.symbolic || row.transform || row.transform_desc;
    if (expression && expression !== title.textContent) main.append(node("p", "expression", expression));
    if (row.symbolic && row.symbolic !== expression) main.append(node("p", "formula", row.symbolic));
    const meta = [];
    if (row.match_type) meta.push(`${row.match_type}${row.offset !== undefined ? ` @ ${row.offset}` : ""}`);
    if (row.length !== undefined) meta.push(`length ${displayValue(row.length)}`);
    if (row.scale !== undefined) meta.push(`scale ${displayValue(row.scale)}`);
    if (row.offset !== undefined && !row.match_type) meta.push(`offset ${displayValue(row.offset)}`);
    if (row.mse !== undefined) meta.push(`MSE ${displayValue(row.mse)}`);
    if (row.n !== undefined) meta.push(`n = ${displayValue(row.n)}`);
    if (row.status) meta.push(String(row.status));
    if (row.bytes !== undefined) meta.push(formatBytes(row.bytes));
    if (row.line !== undefined) meta.push(`line ${displayValue(row.line)}`);
    if (row.path) meta.push(String(row.path));
    if (row.cached !== undefined) meta.push(row.cached ? "cached" : "fresh scan");
    if (row.scan_seconds !== undefined) meta.push(`${displayValue(row.scan_seconds)}s scan`);
    if (row.coeffs) meta.push(`coefficients ${displayValue(row.coeffs)}`);
    if (row.shifts) meta.push(`shifts ${displayValue(row.shifts)}`);
    if (row.elapsed_s !== undefined) meta.push(`${displayValue(row.elapsed_s)}s`);
    if (row.keywords) meta.push(`keywords ${displayValue(row.keywords)}`);
    if (meta.length) {
      const metaRow = node("div", "meta");
      meta.forEach(value => metaRow.append(node("span", "", value)));
      main.append(metaRow);
    }
    if (row.formula) main.append(node("p", "formula", row.formula));
    const terms = row.combined_terms || row.transformed_terms || row.terms;
    if (Array.isArray(terms) && terms.length) main.append(node("div", "terms", terms.map(String).join(", ")));
    appendDetails(main, {
      source_terms: row.transformed_terms && row.terms ? row.terms : null,
      component_transforms: row.component_transforms,
      component_terms: row.component_terms,
      candidate_provenance: row.candidate_provenance,
      latex: row.symbolic_latex || row.latex_expression || row.latex,
      url: row.url,
      error: row.error,
      ...((row.details && typeof row.details === "object") ? row.details : {})
    });
    card.append(main);

    const actions = node("div", "result-actions");
    if (ids.length) {
      const link = node("a", "", "↗");
      link.href = `https://oeis.org/${ids[0]}`;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.title = `Open ${ids[0]} on OEIS`;
      actions.append(link);
    }
    const copy = node("button", "", "⎘");
    copy.type = "button";
    copy.title = "Copy this result";
    copy.dataset.copyText = expression || ids.join(", ") || JSON.stringify(row);
    actions.append(copy);
    card.append(actions);
    return card;
  }

  function resultSections(output) {
    if (Array.isArray(output)) return [["Results", output, "result"]];
    if (!output || typeof output !== "object") return [];
    const command = state.lastJob?.command;
    const sections = [];
    const summaries = [];
    if (command === "bsearch") summaries.push({ title: `Lookup for ${output.value}`, status: `${displayValue(output.total)} sequences`, cached: output.cached, scan_seconds: output.scan_seconds, details: { truncated: output.truncated, ranking: output.ranking, semantics: output.semantics, generation: output.generation } });
    if (command === "bfetch") summaries.push({ title: "B-file fetch", status: `${output.downloaded || 0} downloaded · ${output.skipped || 0} skipped · ${output.failed || 0} failed`, details: { dest_root: output.dest_root } });
    if (command === "bindex") summaries.push({ title: "B-file manifest", status: `${output.manifest_rows || 0} canonical files`, details: output });
    if (command === "optimize-db") summaries.push({ title: "Database optimization", status: (output.created || []).length ? `${output.created.length} indexes created` : "Already optimized", details: output });
    if (output.regressions?.summary) summaries.push({ title: "Regression suite", ok: !output.regressions.summary.fails, status: `${output.regressions.summary.passes}/${output.regressions.summary.cases} passed`, details: output.regressions.summary });
    if (output.random_trials?.summary) summaries.push({ title: "Random trials", ok: !output.random_trials.summary.fails, status: `${output.random_trials.summary.passes}/${output.random_trials.summary.trials} passed`, details: output.random_trials.summary });
    if (summaries.length) sections.push(["Run summary", summaries, "summary"]);

    const preferred = output.ranked_explanations?.length
      ? ["Top ranked explanations", output.ranked_explanations]
      : (output.combined_combinations?.length ? ["Combined shortlist", output.combined_combinations] : null);
    const signature = row => row?.expression && row?.ids
      ? `combo:${row.expression}:${row.ids.join(",")}`
      : `match:${row?.id || ""}:${row?.transform || row?.transform_desc || ""}:${row?.match_type || ""}`;
    const seen = new Set();
    if (preferred) {
      preferred[1].forEach(row => seen.add(signature(row)));
      sections.push([preferred[0], preferred[1], "explanation"]);
    }
    sectionDefinitions.filter(([key]) => key !== "ranked_explanations").forEach(([key, title, family]) => {
      if (!output[key]?.length) return;
      const rows = output[key].filter(row => !seen.has(signature(row)));
      if (!rows.length) return;
      rows.forEach(row => seen.add(signature(row)));
      sections.push([title, rows, key === "matches" && command === "tsearch" ? "transform" : family]);
    });
    if (output.regressions?.results?.length) sections.push(["Regression cases", output.regressions.results, "trial"]);
    if (output.random_trials?.results?.length) sections.push(["Random trials", output.random_trials.results, "trial"]);
    if (output.files?.length) sections.push(["Files", output.files, "file"]);
    return sections;
  }

  function renderSummary(sections) {
    const strip = $("#summary-strip");
    strip.replaceChildren();
    sections.slice(0, 7).forEach(([title, rows]) => {
      const item = node("div", "summary-item");
      item.append(node("b", "", rows.length), node("span", "", title));
      strip.append(item);
    });
    strip.hidden = sections.length === 0;
  }

  function renderCards(output) {
    const container = $("#result-cards");
    container.replaceChildren();
    const sections = resultSections(output);
    renderSummary(sections);
    const diagnostics = output && typeof output === "object" ? output.diagnostics || {} : {};
    const exhausted = Boolean(diagnostics.timed_out || diagnostics.time_budget_exhausted);
    if (exhausted) container.append(node("div", "warning-item", "The time limit was reached. Results found before the limit are shown below."));
    let total = 0;
    sections.forEach(([title, rows, family]) => {
      const section = node("section", "result-section");
      section.append(node("h3", "", title));
      rows.forEach((row, index) => {
        const safeRow = row && typeof row === "object" ? row : { title: displayValue(row) };
        section.append(makeResultCard(safeRow, index, family));
        total += 1;
      });
      container.append(section);
    });
    if (!sections.length) {
      const empty = node("div", "empty-output");
      const text = typeof output === "string" ? output.trim() : "";
      const boundedSearch = ["match", "tsearch", "combo", "analyze"].includes(state.lastJob?.command);
      empty.append(node("strong", "", text ? "Command output" : exhausted ? "Search stopped at its time limit" : boundedSearch ? "No explanation surfaced in this run" : "Command output"));
      if (text) empty.append(node("pre", "", text));
      else if (output && typeof output === "object") {
        if (boundedSearch) empty.append(node("p", "", "This bounded run is inconclusive: an empty result is not proof that no explanation exists."));
        const grid = node("div", "diagnostic-grid");
        flattenScalars(output).forEach(([label, value]) => {
          const card = node("div", "diagnostic-card");
          card.append(node("span", "", label.replaceAll("_", " ")), node("strong", "", value));
          grid.append(card);
        });
        empty.append(grid);
      } else empty.append(node("p", "", boundedSearch ? "This was a bounded search, not proof that no explanation exists. Try more terms or a broader preset." : "The command completed successfully but returned no result rows."));
      container.append(empty);
    }
    $("#result-count").textContent = total ? total : "";
  }

  function flattenScalars(value, prefix = "", depth = 0, result = []) {
    if (result.length >= 36) return result;
    if (value === null || typeof value !== "object") {
      result.push([prefix || "value", displayValue(value)]);
    } else if (Array.isArray(value)) {
      result.push([prefix || "items", `${value.length} item${value.length === 1 ? "" : "s"}`]);
    } else if (depth < 3) {
      Object.entries(value).forEach(([key, child]) => flattenScalars(child, prefix ? `${prefix} · ${key}` : key, depth + 1, result));
    }
    return result;
  }

  function renderDiagnostics(job) {
    const container = $("#diagnostic-cards");
    container.replaceChildren();
    const duration = job.started_at && job.finished_at ? Math.max(0, (new Date(job.finished_at) - new Date(job.started_at)) / 1000) : null;
    const values = [["command", job.command], ["status", job.status], ["return code", job.returncode], ["elapsed", duration === null ? null : `${duration.toFixed(2)}s`]];
    const diagnostics = job.output && typeof job.output === "object" ? job.output.diagnostics : null;
    values.push(...flattenScalars(diagnostics || {}));
    if (job.stderr) values.push(["stderr", job.stderr.trim()]);
    values.filter(([, value]) => value !== "—" && value !== "").forEach(([label, value]) => {
      const card = node("div", "diagnostic-card");
      card.append(node("span", "", label.replaceAll("_", " ")), node("strong", "", value));
      container.append(card);
    });
  }

  function renderJob(job) {
    const panel = $("#results");
    panel.hidden = false;
    const exhausted = Boolean(job.output?.diagnostics?.timed_out || job.output?.diagnostics?.time_budget_exhausted);
    $("#results-title").textContent = job.status === "completed" ? `${job.command}${exhausted ? " partial" : ""} results` : `${job.command} ${job.status}`;
    renderCards(job.output);
    renderDiagnostics(job);
    const raw = typeof job.output === "string" ? job.output : JSON.stringify(job.output, null, 2);
    $("#raw-output").textContent = `${raw || "(no stdout)"}${job.stderr ? `\n\nstderr:\n${job.stderr}` : ""}`;
    $("#copy-json").textContent = job.output_type === "json" ? "Copy JSON" : "Copy output";
    $("#download-json").textContent = job.output_type === "json" ? "Download JSON" : "Download text";
    showTab("cards");
    panel.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function showTab(name) {
    $$(".result-tabs button").forEach(button => {
      const active = button.dataset.tab === name;
      button.classList.toggle("active", active);
      button.setAttribute("aria-selected", String(active));
    });
    $$(".tab-panel").forEach(panel => panel.classList.toggle("active", panel.id === `tab-${name}`));
  }

  function loadHistory() {
    try {
      const value = JSON.parse(localStorage.getItem("oeis-ui-history") || "[]");
      return Array.isArray(value) ? value.slice(0, 10) : [];
    } catch { return []; }
  }

  function saveHistory(items) {
    try { localStorage.setItem("oeis-ui-history", JSON.stringify(items.slice(0, 10))); }
    catch { /* History is optional in privacy modes. */ }
  }

  function addHistory(job) {
    const query = (job.args || []).find(value => !value.startsWith("--")) || job.command;
    const item = { command: job.command, query: String(query).slice(0, 180), at: job.finished_at || new Date().toISOString() };
    const items = [item, ...loadHistory().filter(old => old.command !== item.command || old.query !== item.query)];
    saveHistory(items);
    renderHistory();
  }

  function renderHistory() {
    const container = $("#history-list");
    const items = loadHistory();
    container.replaceChildren();
    if (!items.length) {
      container.append(node("p", "sidebar-note", "Completed searches stay in this browser."));
      return;
    }
    items.forEach(item => {
      const button = node("button", "history-item");
      button.type = "button";
      button.dataset.command = item.command;
      button.dataset.query = item.query;
      button.append(node("strong", "", item.query), node("small", "", `${item.command} · ${new Date(item.at).toLocaleString()}`));
      container.append(button);
    });
  }

  function formatBytes(value) {
    const bytes = Number(value);
    if (!Number.isFinite(bytes)) return "Unknown size";
    const units = ["B", "KB", "MB", "GB"];
    let amount = bytes, unit = 0;
    while (amount >= 1024 && unit < units.length - 1) { amount /= 1024; unit += 1; }
    return `${amount.toFixed(amount >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
  }

  function statusCard(label, value, detail, pill, kind = "") {
    const card = node("article", "status-card");
    const head = node("div");
    head.append(node("span", "", label), node("span", `status-pill ${kind}`, pill));
    card.append(head, node("strong", "", value), node("small", "", detail));
    return card;
  }

  function renderStatus(report) {
    const dashboard = $("#status-dashboard");
    const ready = Boolean(report.ready);
    const freshness = report.freshness || {};
    const db = report.paths?.db || {};
    const stale = Boolean(freshness.is_stale);
    const age = freshness.age_days === null || freshness.age_days === undefined ? "Unknown age" : `${Number(freshness.age_days).toFixed(1)} days old`;
    const sequenceCount = db.sequence_count === null || db.sequence_count === undefined ? "No index" : `${Number(db.sequence_count).toLocaleString()} sequences`;
    const missing = Array.isArray(db.missing_recommended_indexes) ? db.missing_recommended_indexes.length : 0;
    dashboard.replaceChildren(
      statusCard("Search readiness", ready ? "Ready to search" : "Setup needed", ready ? "All required local files are available" : "See warnings and maintenance actions below", ready ? "ready" : "action", ready ? "" : "bad"),
      statusCard("OEIS snapshot", age, freshness.last_sync_utc ? `Last sync ${new Date(freshness.last_sync_utc).toLocaleString()}` : "No recorded sync", stale ? "stale" : "current", stale ? "warn" : ""),
      statusCard("SQLite index", sequenceCount, `${db.path || "data/processed/oeis.db"} · ${formatBytes(db.bytes)}`, missing ? `${missing} missing` : "optimized", missing ? "warn" : "")
    );
    const warnings = $("#status-warnings");
    warnings.replaceChildren();
    (report.warnings || []).forEach(message => warnings.append(node("div", "warning-item", message)));
    warnings.hidden = !(report.warnings || []).length;
    const mini = $("#mini-status");
    const light = $(".status-light", mini);
    light.className = `status-light ${ready && !stale ? "ready" : ready ? "pending" : "bad"}`;
    $("strong", mini).textContent = ready ? (stale ? "Ready · snapshot stale" : "Index ready") : "Setup needed";
    $("small", mini).textContent = db.path || "data/processed/oeis.db";
  }

  async function loadStatus() {
    try { renderStatus(await request("/api/status")); }
    catch (error) {
      const dashboard = $("#status-dashboard");
      dashboard.replaceChildren(statusCard("Local server", "Unavailable", error.message, "error", "bad"));
      const mini = $("#mini-status");
      $(".status-light", mini).className = "status-light bad";
      $("strong", mini).textContent = "Server unavailable";
      toast(error.message, "error");
    }
  }

  async function resumeActiveJob() {
    try {
      const listing = await request("/api/jobs");
      if (!listing.active_job_id) return;
      const job = (listing.jobs || []).find(item => item.id === listing.active_job_id);
      if (!job) return;
      state.activeJob = job.id;
      showProgress(job);
      pollJob(job.id);
    } catch { /* The status request gives the useful startup error. */ }
  }

  async function copyText(text) {
    try { await navigator.clipboard.writeText(text); toast("Copied to clipboard."); }
    catch { toast("Clipboard access was unavailable.", "error"); }
  }

  function openCommandDialog() {
    const dialog = $("#command-dialog");
    $("#command-filter").value = "";
    $$(".command-list button").forEach(button => { button.hidden = false; });
    dialog.showModal();
    $("#command-filter").focus();
  }

  $$(".nav-link[data-view]").forEach(button => button.addEventListener("click", () => switchView(button.dataset.view)));
  $$("form[data-command]").forEach(form => form.addEventListener("submit", event => { event.preventDefault(); startJob(form); }));
  $$('.sequence-field textarea').forEach(textarea => {
    textarea.addEventListener("input", () => { textarea.setCustomValidity(""); updateTermCount(textarea); });
    updateTermCount(textarea);
  });
  $('[data-flag="--checkpoint"]')?.addEventListener("input", event => event.target.setCustomValidity(""));
  [["--pairs-only", "--triples-only"]].forEach(([left, right]) => {
    const a = $(`[data-flag="${left}"]`), b = $(`[data-flag="${right}"]`);
    a?.addEventListener("change", () => { if (a.checked && b) b.checked = false; });
    b?.addEventListener("change", () => { if (b.checked && a) a.checked = false; });
  });
  $$("[data-sample]").forEach(button => button.addEventListener("click", () => {
    const textarea = $("textarea", button.closest("form"));
    textarea.value = button.dataset.sample;
    updateTermCount(textarea);
    textarea.focus();
  }));
  $$(".clear-button").forEach(button => button.addEventListener("click", () => {
    const input = document.getElementById(button.dataset.target);
    input.value = "";
    updateTermCount(input);
    input.focus();
  }));
  $$(".paste-button").forEach(button => button.addEventListener("click", async () => {
    try {
      const input = document.getElementById(button.dataset.target);
      input.value = await navigator.clipboard.readText();
      updateTermCount(input);
      input.focus();
    } catch { toast("Clipboard access was unavailable.", "error"); }
  }));
  $$(".result-tabs button").forEach(button => button.addEventListener("click", () => showTab(button.dataset.tab)));
  $("#result-cards").addEventListener("click", event => {
    const button = event.target.closest("[data-copy-text]");
    if (button) copyText(button.dataset.copyText);
  });
  $("#cancel-job").addEventListener("click", async () => {
    if (!state.activeJob) return;
    try {
      const job = await request(`/api/jobs/${encodeURIComponent(state.activeJob)}`, { method: "DELETE" });
      if (job.status === "running") {
        clearInterval(state.progressTimer);
        $("#job-detail").textContent = "Stopping the local command…";
        pollJob(job.id);
      } else finishJob(job);
    }
    catch (error) { toast(error.message, "error"); }
  });
  $("#copy-json").addEventListener("click", () => copyText(typeof state.lastOutput === "string" ? state.lastOutput : JSON.stringify(state.lastOutput, null, 2)));
  $("#download-json").addEventListener("click", () => {
    const text = typeof state.lastOutput === "string" ? state.lastOutput : JSON.stringify(state.lastOutput, null, 2);
    const isJson = state.lastJob?.output_type === "json";
    const url = URL.createObjectURL(new Blob([text || ""], { type: isJson ? "application/json" : "text/plain" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${state.lastJob?.command || "oeis"}-result.${isJson ? "json" : "txt"}`;
    link.click();
    URL.revokeObjectURL(url);
  });
  $("#refresh-status").addEventListener("click", loadStatus);
  $("#clear-history").addEventListener("click", () => { saveHistory([]); renderHistory(); });
  $("#history-list").addEventListener("click", event => {
    const button = event.target.closest(".history-item");
    if (!button) return;
    const viewName = commandViews[button.dataset.command] || "analyze";
    switchView(viewName);
    const view = $(`#view-${viewName}`);
    const input = $("[data-positional]", view);
    if (input && button.dataset.query !== button.dataset.command) {
      input.value = button.dataset.query;
      if (input.matches("textarea")) updateTermCount(input);
      input.focus();
    }
  });
  $("#command-button").addEventListener("click", openCommandDialog);
  $("#command-filter").addEventListener("input", event => {
    const query = event.target.value.toLowerCase();
    $$(".command-list button").forEach(button => { button.hidden = !button.textContent.toLowerCase().includes(query); });
  });
  $$("[data-command-view]").forEach(button => button.addEventListener("click", () => {
    $("#command-dialog").close();
    switchView(button.dataset.commandView, true);
  }));
  $("#command-dialog").addEventListener("click", event => {
    if (event.target === $("#command-dialog")) $("#command-dialog").close();
  });
  document.addEventListener("keydown", event => {
    const modifier = event.ctrlKey || event.metaKey;
    if (modifier && event.key.toLowerCase() === "k") { event.preventDefault(); openCommandDialog(); }
    if (modifier && event.key === "Enter") {
      const form = $(".view.active form.search-form, .view.active form.check-card");
      if (form) { event.preventDefault(); form.requestSubmit(); }
    }
    if (event.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) {
      const input = $("textarea, input", $(".view.active"));
      if (input) { event.preventDefault(); input.focus(); }
    }
  });

  const initialView = location.hash.slice(1);
  if ($(`#view-${initialView}`)) switchView(initialView);
  renderHistory();
  loadStatus();
  resumeActiveJob();
})();
