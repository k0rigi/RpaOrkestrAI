"use strict";

(() => {
  const root = document.getElementById("app");
  const state = {
    workflows: [],
    runs: [],
    catalog: [],
    actionDefinitions: [],
    favorites: [],
    favoriteSaving: false,
    settings: {},
    platform: "",
    version: "",
    updates: {},
    updatePoll: null,
    page: "dashboard",
    workflow: null,
    selected: null,
    target: null,
    dirty: false,
    dryRun: true,
    run: null,
    poll: null,
    pollEpoch: 0,
    fieldErrors: new Set(),
    drafts: new Map(),
    search: "",
    runFilter: "all",
    saving: false,
    starting: false,
    revision: 0,
  };
  const statusLabels = {
    queued: "Sırada",
    running: "Çalışıyor",
    succeeded: "Tamamlandı",
    failed: "Hata",
    cancelled: "Durduruldu",
  };
  const paths = {
    grid: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
    flow: "M5 3h6v5H5z M13 16h6v5h-6z M8 8v5h8v3 M16 3h5v5h-5z M18.5 8v5H8",
    clock: "M12 8v5l3 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    settings:
      "M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
    plus: "M12 5v14 M5 12h14",
    star: "M12 3l2.8 5.7 6.3.9-4.5 4.4 1.1 6.2-5.7-3-5.7 3 1.1-6.2L3.2 9.6l6.3-.9z",
    arrow: "M5 12h14 M14 7l5 5-5 5",
    back: "M19 12H5 M10 7l-5 5 5 5",
    chevron: "M9 5l7 7-7 7",
    down: "M6 9l6 6 6-6",
    up: "M6 15l6-6 6 6",
    play: "M8 4l12 8-12 8z",
    stop: "M5 5h14v14H5z",
    check: "M5 12l4 4L19 6",
    cross: "M6 6l12 12 M18 6L6 18",
    search: "M17 17l4 4 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
    database:
      "M20 5c0 2-4 3-8 3S4 7 4 5s4-3 8-3 8 1 8 3z M4 5v7c0 2 4 3 8 3s8-1 8-3V5 M4 12v7c0 2 4 3 8 3s8-1 8-3v-7",
    desktop: "M3 3h18v13H3z M12 16v5 M8 21h8",
    globe:
      "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c5 5 5 13 0 18-5-5-5-13 0-18",
    sheet: "M4 3h16v18H4z M4 8h16 M4 13h16 M4 18h16 M10 3v18",
    branch: "M7 3v12c0 3 2 4 5 4h6 M7 8h5c3 0 4-2 4-5 M15 16l3 3-3 3",
    loop: "M20 7h-9a6 6 0 0 0 0 12h9 M16 3l4 4-4 4 M20 13v6h-6",
    eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12 M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0",
    file: "M5 2h9l5 5v15H5z M14 2v6h5 M8 12h8 M8 16h6",
    download: "M12 3v12 M7 10l5 5 5-5 M4 15v6h16v-6",
    upload: "M12 16V4 M7 9l5-5 5 5 M4 16v5h16v-5",
    edit: "M4 16l12-12 4 4L8 20H4z M13 7l4 4",
    trash: "M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7",
    copy: "M8 8h13v13H8z M16 8V3H3v13h5",
    save: "M4 3h13l4 4v14H3V3z M7 3v6h10V3 M7 21v-8h10v8",
    link: "M9 15l6-6 M8 16l-2 2a4 4 0 0 1-6-6l5-5a4 4 0 0 1 6 0 M16 8l2-2a4 4 0 0 1 6 6l-5 5a4 4 0 0 1-6 0",
    info: "M12 11v6 M12 7v1 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
    terminal: "M3 4h18v16H3z M6 8l4 4-4 4 M13 16h5",
    menu: "M4 6h16 M4 12h16 M4 18h16",
    shield: "M12 2l8 3v7c0 5-8 10-8 10S4 17 4 12V5z M8 12l3 3 5-6",
    folder: "M3 5h7l2 3h9v13H3z",
    code: "M8 7l-5 5 5 5 M16 7l5 5-5 5 M14 4l-4 16",
    spark: "M12 3l2 6 7 3-7 2-2 7-3-7-6-2 6-3z",
    refresh:
      "M20 7v5h-5 M4 17v-5h5 M19 12a7 7 0 0 0-12-6L4 9 M5 12a7 7 0 0 0 12 6l3-3",
  };

  function node(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  }
  function icon(name) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    el.setAttribute("viewBox", "0 0 24 24");
    el.setAttribute("fill", "none");
    el.setAttribute("stroke", "currentColor");
    el.setAttribute("stroke-linecap", "round");
    el.setAttribute("stroke-linejoin", "round");
    el.setAttribute("aria-hidden", "true");
    const path = document.createElementNS(el.namespaceURI, "path");
    path.setAttribute("d", paths[name] || paths.flow);
    el.append(path);
    return el;
  }
  function button(label, glyph, handler, variant = "") {
    const el = node("button", `button ${variant}`);
    el.type = "button";
    if (glyph) el.append(icon(glyph));
    el.append(node("span", "", label));
    if (handler) el.addEventListener("click", handler);
    return el;
  }
  function iconButton(label, glyph, handler, extra = "") {
    const el = node("button", `icon-button ${extra}`);
    el.type = "button";
    el.title = label;
    el.setAttribute("aria-label", label);
    el.append(icon(glyph));
    el.addEventListener("click", (event) => {
      event.stopPropagation();
      handler(event);
    });
    return el;
  }
  function linkButton(label, handler, glyph = "arrow") {
    const el = node("button", "link-button");
    el.type = "button";
    el.append(node("span", "", label));
    if (glyph) el.append(icon(glyph));
    el.addEventListener("click", handler);
    return el;
  }
  function textInput(value, placeholder = "", type = "text") {
    const el = node("input", "field-input");
    el.type = type;
    el.value = value ?? "";
    el.placeholder = placeholder;
    return el;
  }
  function field(label, control, help, required = false) {
    const wrap = node("div", "field");
    const l = node("label", "field-label", label);
    control.id ||= `field-${uid()}`;
    l.htmlFor = control.id;
    if (required) l.append(node("span", "required-star", "*"));
    wrap.append(l, control);
    if (help) wrap.append(node("p", "help", help));
    return wrap;
  }
  function note(text, variant = "", glyph = "info") {
    const el = node("div", `note ${variant}`);
    el.append(icon(glyph), node("span", "", text));
    return el;
  }
  function empty(title, message, action) {
    const el = node("div", "empty");
    el.append(icon("flow"), node("strong", "", title), node("p", "", message));
    if (action) el.append(action);
    return el;
  }
  function badge(status) {
    return node(
      "span",
      `pill ${status === "succeeded" ? "success" : status}`,
      statusLabels[status] || status,
    );
  }
  function uid() {
    return (
      globalThis.crypto?.randomUUID?.() ||
      `id-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
    );
  }
  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }
  function when(value, time = false) {
    if (!value) return "—";
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return "—";
    return new Intl.DateTimeFormat(
      "tr-TR",
      time
        ? { hour: "2-digit", minute: "2-digit", second: "2-digit" }
        : {
            day: "numeric",
            month: "short",
            hour: "2-digit",
            minute: "2-digit",
          },
    ).format(d);
  }
  function duration(run) {
    if (!run.started_at) return "—";
    const ms =
      new Date(run.finished_at || Date.now()) - new Date(run.started_at);
    if (!Number.isFinite(ms) || ms < 0) return "—";
    const seconds = Math.round(ms / 1000);
    return seconds < 60
      ? `${seconds} sn`
      : `${Math.floor(seconds / 60)} dk ${seconds % 60} sn`;
  }
  function countSteps(steps) {
    return (steps || []).reduce(
      (sum, step) =>
        sum + 1 + countSteps(step.children) + countSteps(step.otherwise),
      0,
    );
  }
  function allSteps(steps) {
    return (steps || []).flatMap((step) => [
      step,
      ...allSteps(step.children),
      ...allSteps(step.otherwise),
    ]);
  }
  function specFor(action) {
    return (
      state.catalog.find((a) => a.type === action) ||
      state.actionDefinitions.find((a) => a.type === action) || {
        type: action,
        label: action,
        category: "Diğer",
        description: "Bu eylemin katalog bilgisi bulunamadı.",
        fields: [],
      }
    );
  }
  function actionIcon(action) {
    const type = String(action).toLowerCase();
    if (/database|sql|query/.test(type)) return "database";
    if (/sheet/.test(type)) return "sheet";
    if (/browser|web|playwright/.test(type)) return "globe";
    if (/for_each|loop|dropdown/.test(type)) return "loop";
    if (/control\.if|^if$|condition|decision|branch/.test(type)) return "branch";
    if (/ocr|vision|detect|screen/.test(type)) return "eye";
    if (/desktop|click|type|hotkey/.test(type)) return "desktop";
    if (/export|report|csv|file/.test(type)) return "file";
    if (/wait|sleep/.test(type)) return "clock";
    if (/log/.test(type)) return "terminal";
    return "code";
  }
  function toast(message, error = false) {
    const el = node("div", `toast${error ? " error" : ""}`, message);
    document.getElementById("toast-region").append(el);
    setTimeout(() => el.remove(), error ? 8500 : 4500);
  }
  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options.headers || {}),
      },
    });
    if (!response.ok) {
      let detail;
      try {
        const body = await response.json();
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail || body);
      } catch {
        detail = `HTTP ${response.status}`;
      }
      throw new Error(detail || "İşlem tamamlanamadı.");
    }
    if (response.status === 204) return null;
    return response.json();
  }
  async function attempt(fn) {
    try {
      return await fn();
    } catch (error) {
      toast(error.message || "Beklenmeyen bir hata oluştu.", true);
      return null;
    }
  }
  function upsert(list, item) {
    const index = list.findIndex((x) => x.id === item.id);
    if (index < 0) list.unshift(item);
    else list[index] = item;
  }
  function markDirty() {
    state.dirty = true;
    state.revision += 1;
    updateSavedLabel();
  }
  function updateSavedLabel() {
    const label = document.getElementById("saved-label");
    if (label) {
      label.className = `saved-indicator${state.dirty ? " dirty" : ""}`;
      label.replaceChildren(
        icon(state.dirty ? "edit" : "check"),
        node(
          "span",
          "",
          state.dirty
            ? "Kaydedilmemiş değişiklikler"
            : "Tüm değişiklikler kaydedildi",
        ),
      );
    }
  }

  function dialog(title, build, actions = []) {
    const el = node("dialog", "dialog-backdrop");
    const head = node("div", "dialog-head");
    head.append(
      node("h2", "", title),
      iconButton("Kapat", "cross", () => el.close()),
    );
    const body = node("div", "dialog-body");
    build(body, el);
    const foot = node("div", "dialog-footer");
    for (const action of actions)
      foot.append(
        button(
          action.label,
          action.icon,
          () => action.fn(el, body),
          action.variant,
        ),
      );
    el.append(head, body);
    if (actions.length) el.append(foot);
    document.body.append(el);
    el.addEventListener("close", () => el.remove());
    el.addEventListener("click", (event) => {
      if (event.target === el) {
        const rect = el.getBoundingClientRect();
        if (
          event.clientX < rect.left ||
          event.clientX > rect.right ||
          event.clientY < rect.top ||
          event.clientY > rect.bottom
        )
          el.close();
      }
    });
    el.showModal();
    return el;
  }
  function confirmDialog(title, message, label = "Devam et", danger = false) {
    return new Promise((resolve) => {
      let settled = false;
      const settle = (value, el) => {
        if (!settled) {
          settled = true;
          resolve(value);
        }
        el.close();
      };
      const el = dialog(
        title,
        (body) => body.append(node("p", "small muted", message)),
        [
          { label: "Vazgeç", fn: (d) => settle(false, d) },
          {
            label,
            variant: danger ? "danger" : "primary",
            fn: (d) => settle(true, d),
          },
        ],
      );
      el.addEventListener("close", () => {
        if (!settled) resolve(false);
      });
    });
  }
  async function guardUnsaved() {
    if (!state.dirty) return true;
    return confirmDialog(
      "Kaydedilmemiş değişiklikler",
      "Bu akışta kaydetmediğiniz değişiklikler var. Sayfadan ayrılırsanız değişiklikler kaybolacak.",
      "Kaydetmeden ayrıl",
      true,
    );
  }
  async function navigate(page, options = {}) {
    if (!options.force && !(await guardUnsaved())) return;
    stopPolling();
    const epoch = state.pollEpoch;
    state.page = page;
    state.dirty = false;
    state.fieldErrors.clear();
    state.drafts.clear();
    state.search = "";
    if (page !== "editor") {
      state.workflow = null;
      state.selected = null;
      state.target = null;
    }
    render();
    if (page === "runs" || page === "dashboard") {
      await attempt(async () => {
        const runs = await api("/api/runs");
        if (state.page !== page || state.pollEpoch !== epoch) return;
        state.runs = runs;
        renderPage();
      });
      if (state.page === page && state.pollEpoch === epoch) pollRunList();
    }
  }
  async function openWorkflow(id) {
    if (!(await guardUnsaved())) return;
    stopPolling();
    const epoch = state.pollEpoch;
    await attempt(async () => {
      const workflow = await api(`/api/workflows/${encodeURIComponent(id)}`);
      if (state.pollEpoch !== epoch) return;
      state.page = "editor";
      state.workflow = clone(workflow);
      state.selected = null;
      state.target = null;
      state.dirty = false;
      state.fieldErrors.clear();
      state.drafts.clear();
      render();
    });
  }
  async function openRun(id) {
    if (!(await guardUnsaved())) return;
    stopPolling();
    const epoch = state.pollEpoch;
    await attempt(async () => {
      const run = await api(`/api/runs/${encodeURIComponent(id)}`);
      if (state.pollEpoch !== epoch) return;
      state.run = run;
      state.page = "run";
      state.dirty = false;
      render();
      pollRun();
    });
  }

  function render() {
    root.replaceChildren();
    root.setAttribute("aria-busy", "false");
    const sidebar = node("aside", "sidebar");
    sidebar.id = "sidebar";
    const brand = node("div", "brand");
    const mark = node("span", "brand-mark", "O");
    mark.append(node("span"));
    const brandText = node("div");
    brandText.append(
      node("div", "brand-name", "RpaOrkestrAI"),
      node("div", "brand-caption", "AKIŞ STÜDYOSU"),
    );
    brand.append(mark, brandText);
    sidebar.append(brand, node("div", "nav-label", "ÇALIŞMA ALANI"));
    const nav = node("nav");
    nav.setAttribute("aria-label", "Ana menü");
    for (const [page, label, glyph] of [
      ["dashboard", "Genel bakış", "grid"],
      ["workflows", "Akışlarım", "flow"],
      ["runs", "Çalışma geçmişi", "clock"],
    ]) {
      const selected =
        state.page === page ||
        (page === "workflows" && state.page === "editor") ||
        (page === "runs" && state.page === "run");
      const item = node("button", `nav-button${selected ? " active" : ""}`);
      item.append(icon(glyph), node("span", "", label));
      if (page === "workflows")
        item.append(node("span", "nav-count", state.workflows.length));
      item.addEventListener("click", () => navigate(page));
      if (selected) item.setAttribute("aria-current", "page");
      nav.append(item);
    }
    sidebar.append(nav);
    const bottom = node("div", "sidebar-bottom");
    bottom.append(node("div", "nav-label", "YÖNETİM"));
    const settings = node(
      "button",
      `nav-button${state.page === "settings" ? " active" : ""}`,
    );
    settings.append(
      icon("settings"),
      node("span", "", "Bağlantılar ve ayarlar"),
    );
    settings.addEventListener("click", () => navigate("settings"));
    bottom.append(settings);
    const local = node("div", "local-label");
    local.append(
      node("span", "status-dot"),
      node("span", "", "Yerel çalışma alanı"),
    );
    bottom.append(local);
    const owner = node("div", "workspace-owner");
    owner.append(node("div", "avatar", "YS"));
    const ownerText = node("div");
    ownerText.append(
      node("strong", "", "Yönetici stüdyosu"),
      node("small", "", "Otomasyon çalışma alanı"),
    );
    owner.append(ownerText);
    bottom.append(owner);
    sidebar.append(bottom);
    const main = node("div", "main-shell");
    const top = node("header", "topbar");
    const left = node("div", "topbar-left");
    left.append(
      iconButton(
        "Menüyü aç / kapat",
        "menu",
        () => sidebar.classList.toggle("open"),
        "mobile-nav-toggle",
      ),
    );
    const crumbs = node("div", "breadcrumbs");
    crumbs.append(
      node("span", "", "Çalışma alanı"),
      icon("chevron"),
      node(
        "span",
        "current",
        {
          dashboard: "Genel bakış",
          workflows: "Akışlarım",
          editor: "Akış düzenleyici",
          runs: "Çalışma geçmişi",
          run: "Çalışma ayrıntısı",
          settings: "Bağlantılar ve ayarlar",
        }[state.page],
      ),
    );
    left.append(crumbs);
    const right = node("div", "topbar-right");
    const platform = node("span", "platform-label");
    platform.append(
      icon("desktop"),
      node(
        "span",
        "",
        typeof state.platform === "string"
          ? { Darwin: "macOS", Windows: "Windows", Linux: "Linux" }[
              state.platform
            ] || state.platform
          : state.platform?.system || "Yerel ortam",
      ),
    );
    right.append(
      platform,
      node("span", "version", `v${state.version || "0.2.0"}`),
    );
    const updateNotice = button("Güncelleme hazır", "download", () => navigate("settings"));
    updateNotice.id = "update-notice";
    updateNotice.hidden = state.updates.status !== "ready";
    right.append(updateNotice);
    top.append(left, right);
    main.append(top, node("main", "page-content"));
    root.append(sidebar, main);
    renderPage();
  }
  function renderPage() {
    const target = document.querySelector(".page-content");
    if (!target) return;
    target.replaceChildren();
    const views = {
      dashboard: dashboardPage,
      workflows: workflowsPage,
      editor: editorPage,
      runs: runsPage,
      run: runPage,
      settings: settingsPage,
    };
    target.append((views[state.page] || dashboardPage)());
  }
  function heading(eyebrow, title, subtitle, actions) {
    const el = node("div", "page-heading");
    const copy = node("div");
    copy.append(node("div", "eyebrow", eyebrow), node("h1", "", title));
    if (subtitle) copy.append(node("p", "", subtitle));
    el.append(copy);
    if (actions) el.append(actions);
    return el;
  }
  function sectionHeading(title, subtitle, action) {
    const el = node("div", "section-heading");
    const text = node("div");
    text.append(node("h2", "", title));
    if (subtitle) text.append(node("p", "", subtitle));
    el.append(text);
    if (action) el.append(action);
    return el;
  }
  function dashboardPage() {
    const page = node("div", "page");
    page.append(
      heading(
        "OTOMASYON MERKEZİ",
        "İşlerinize akış kazandırın.",
        "Akışlarınızı oluşturun, süreçlerinizi izleyin ve sonuçları ekibinizle paylaşın.",
        button("Yeni akış oluştur", "plus", newWorkflow, "primary"),
      ),
    );
    const hero = node("section", "hero");
    const heroCopy = node("div");
    heroCopy.append(
      node("div", "eyebrow", "TEK STÜDYO. BAĞLI SÜREÇLER."),
      node("h2", "", "Veriden işleme,\nişlemden sonuca."),
      node(
        "p",
        "",
        "Veritabanınızı, masaüstü uygulamalarınızı ve web servislerinizi tek bir akışta buluşturun.",
      ),
      button(
        "Akışlarımı keşfet",
        "arrow",
        () => navigate("workflows"),
        "small",
      ),
    );
    const visual = node("div", "hero-flow");
    visual.setAttribute("aria-hidden", "true");
    [
      ["database", "Veriyi oku"],
      ["flow", "Süreci çalıştır"],
      ["file", "Çıktıyı paylaş"],
    ].forEach(([glyph, label], index) => {
      if (index) visual.append(node("div", "hero-wire"));
      const card = node("div", "hero-node");
      card.append(icon(glyph), node("span", "", label));
      visual.append(card);
    });
    hero.append(heroCopy, visual);
    page.append(hero);
    const stats = node("div", "stats-grid");
    const actualRuns = state.runs.filter((r) => !r.dry_run);
    const artifacts = state.runs.flatMap((r) => r.artifacts || []);
    for (const [label, value, foot, glyph] of [
      [
        "Toplam akış",
        state.workflows.length,
        "Çalışma alanındaki akışlar",
        "flow",
      ],
      [
        "Tamamlanan çalışma",
        actualRuns.filter((r) => r.status === "succeeded").length,
        "Denemeler hariç",
        "check",
      ],
      [
        "Aktif çalışma",
        state.runs.filter((r) => ["queued", "running"].includes(r.status))
          .length,
        "Sırada veya çalışıyor",
        "play",
      ],
      [
        "Üretilen çıktı",
        artifacts.length,
        "Çalışma arşivindeki dosyalar",
        "file",
      ],
    ]) {
      const stat = node("div", "stat-card");
      const text = node("div");
      text.append(
        node("div", "stat-label", label),
        node("div", "stat-value", value),
        node("div", "stat-foot", foot),
      );
      const glyphEl = node("div", "stat-icon");
      glyphEl.append(icon(glyph));
      stat.append(text, glyphEl);
      stats.append(stat);
    }
    page.append(stats);
    const columns = node("div", "dashboard-grid");
    const flows = node("section");
    flows.append(
      sectionHeading(
        "Akışlarınız",
        "Bir sonraki işleminiz buradan başlar.",
        linkButton("Tümünü gör", () => navigate("workflows")),
      ),
    );
    const flowPanel = node("div", "panel");
    if (!state.workflows.length)
      flowPanel.append(
        empty(
          "İlk akışınızı oluşturun",
          "Adımları bir araya getirerek tekrarlayan işlerinizi otomatikleştirin.",
          button("Akış oluştur", "plus", newWorkflow, "small primary"),
        ),
      );
    state.workflows
      .slice(0, 4)
      .forEach((w) => flowPanel.append(workflowRow(w)));
    flows.append(flowPanel);
    const recent = node("section");
    recent.append(
      sectionHeading(
        "Son hareketler",
        "Akışlarınızın çalışma günlüğü.",
        linkButton("Geçmiş", () => navigate("runs")),
      ),
    );
    const recentPanel = node("div", "panel");
    if (!state.runs.length)
      recentPanel.append(
        empty(
          "Henüz çalışma yok",
          "Bir akışı çalıştırdığınızda sonuçları burada görünür.",
        ),
      );
    state.runs.slice(0, 4).forEach((run) => {
      const row = node("div", "activity-row");
      const glyph = node("div", `activity-icon ${run.status}`);
      glyph.append(
        icon(
          run.status === "succeeded"
            ? "check"
            : run.status === "failed"
              ? "cross"
              : "clock",
        ),
      );
      const copy = node("div", "activity-content");
      copy.append(
        node("div", "activity-name", run.workflow_name),
        node(
          "div",
          "activity-meta",
          `${when(run.started_at)}${run.dry_run ? " · Deneme" : ""}`,
        ),
      );
      const go = iconButton("Çalışmayı görüntüle", "chevron", () =>
        openRun(run.id),
      );
      row.append(glyph, copy, go);
      recentPanel.append(row);
    });
    recent.append(recentPanel);
    columns.append(flows, recent);
    page.append(columns);
    const foot = node("div", "footer-note");
    foot.append(
      icon("shield"),
      node(
        "span",
        "",
        "Akışlar ve bağlantı ayarları bu bilgisayarda saklanır.",
      ),
    );
    page.append(foot);
    return page;
  }
  function workflowRow(workflow) {
    const row = node("div", "workflow-row");
    const glyph = node("div", "workflow-symbol");
    glyph.append(icon("flow"));
    const copy = node("div", "workflow-info");
    const name = node("button", "workflow-name", workflow.name);
    name.addEventListener("click", () => openWorkflow(workflow.id));
    const meta = node("div", "workflow-meta");
    meta.append(
      node("span", "", workflow.department || "Genel"),
      node("span", "", "·"),
      node("span", "", `${countSteps(workflow.steps)} adım`),
    );
    copy.append(name, meta);
    row.append(
      glyph,
      copy,
      node("span", "pill", "Akış"),
      iconButton("Akışı düzenle", "chevron", () => openWorkflow(workflow.id)),
    );
    return row;
  }

  function workflowsPage() {
    const page = node("div", "page");
    const actions = node("div", "actions");
    actions.append(
      button("İçe aktar", "upload", importWorkflow),
      button("Yeni akış", "plus", newWorkflow, "primary"),
    );
    page.append(
      heading(
        "AKIŞ KÜTÜPHANESİ",
        "Akışlarım",
        "Otomasyonlarınızı tasarlayın ve her departman için yeniden kullanın.",
        actions,
      ),
    );
    const toolbar = node("div", "toolbar");
    const search = node("div", "search");
    const input = textInput(state.search, "Akış veya departman ara…", "search");
    input.setAttribute("aria-label", "Akış veya departman ara");
    search.append(icon("search"), input);
    toolbar.append(
      search,
      node("span", "small muted", `${state.workflows.length} akış`),
    );
    page.append(toolbar);
    const grid = node("div", "workflow-grid");
    page.append(grid);
    const update = () => {
      grid.replaceChildren();
      const q = state.search.toLocaleLowerCase("tr");
      const rows = state.workflows.filter((w) =>
        `${w.name} ${w.department || ""} ${w.description || ""}`
          .toLocaleLowerCase("tr")
          .includes(q),
      );
      if (!rows.length) {
        grid.append(
          empty(
            q ? "Akış bulunamadı" : "Henüz bir akış yok",
            q
              ? "Farklı bir arama yapabilirsiniz."
              : "Yeni bir akış oluşturun veya dışa aktarılmış bir akışı içe alın.",
          ),
        );
        return;
      }
      rows.forEach((w) => {
        const card = node("article", "panel workflow-card");
        const top = node("div", "workflow-card-top");
        const glyph = node("div", "workflow-symbol");
        glyph.append(icon("flow"));
        const tools = node("div", "actions");
        tools.append(
          iconButton("Akışı çoğalt", "copy", () => duplicateWorkflow(w.id)),
          iconButton("Akışı sil", "trash", () => deleteWorkflow(w), "danger"),
        );
        top.append(glyph, tools);
        card.append(
          top,
          node("h3", "", w.name),
          node(
            "p",
            "",
            w.description || "Bu akış için henüz açıklama eklenmedi.",
          ),
        );
        const meta = node("div", "workflow-meta");
        meta.append(
          node("span", "pill", w.department || "Genel"),
          node("span", "", `${countSteps(w.steps)} adım`),
        );
        card.append(meta);
        const footer = node("div", "workflow-card-footer");
        footer.append(
          node("span", "small muted", when(w.updated_at)),
          linkButton("Akışı aç", () => openWorkflow(w.id)),
        );
        card.append(footer);
        grid.append(card);
      });
    };
    input.addEventListener("input", () => {
      state.search = input.value;
      update();
    });
    update();
    return page;
  }
  function workflowMetadata(existing, onSubmit) {
    let name, description, department;
    dialog(
      existing ? "Akış bilgileri" : "Yeni bir akış oluştur",
      (body) => {
        name = textInput(existing?.name || "", "Örn. Günlük satış raporu");
        name.required = true;
        name.maxLength = 120;
        description = node("textarea");
        description.value = existing?.description || "";
        description.maxLength = 2000;
        description.placeholder = "Bu akış hangi işi otomatikleştiriyor?";
        department = textInput(
          existing?.department || "",
          "Örn. Satış, Finans, Operasyon",
        );
        department.maxLength = 120;
        body.append(
          field("Akış adı", name, null, true),
          field("Açıklama", description),
          field(
            "Departman",
            department,
            "Çıktıların ait olduğu departmanı belirtin. Boş bırakılırsa Genel kullanılır.",
          ),
        );
      },
      [
        { label: "Vazgeç", fn: (d) => d.close() },
        {
          label: existing ? "Uygula" : "Akış oluştur",
          icon: existing ? "check" : "plus",
          variant: "primary",
          fn: (d) => {
            if (!name.value.trim()) {
              name.reportValidity();
              name.focus();
              return;
            }
            onSubmit(
              {
                name: name.value.trim(),
                description: description.value.trim(),
                department: department.value.trim() || "Genel",
              },
              d,
            );
          },
        },
      ],
    );
  }
  async function newWorkflow() {
    if (!(await guardUnsaved())) return;
    workflowMetadata(null, (data, d) =>
      attempt(async () => {
        const w = await api("/api/workflows", {
          method: "POST",
          body: JSON.stringify({ ...data, steps: [] }),
        });
        upsert(state.workflows, w);
        d.close();
        state.dirty = false;
        await openWorkflow(w.id);
        toast("Yeni akış oluşturuldu. Soldaki kütüphaneden adım ekleyin.");
      }),
    );
  }
  async function duplicateWorkflow(id) {
    await attempt(async () => {
      const w = await api(
        `/api/workflows/${encodeURIComponent(id)}/duplicate`,
        { method: "POST" },
      );
      upsert(state.workflows, w);
      render();
      toast("Akışın kopyası oluşturuldu.");
    });
  }
  async function deleteWorkflow(workflow) {
    if (
      !(await confirmDialog(
        "Akışı sil",
        `“${workflow.name}” akışı silinecek. Bu işlem geri alınamaz.`,
        "Akışı sil",
        true,
      ))
    )
      return;
    await attempt(async () => {
      await api(`/api/workflows/${encodeURIComponent(workflow.id)}`, {
        method: "DELETE",
      });
      state.workflows = state.workflows.filter((w) => w.id !== workflow.id);
      render();
      toast("Akış silindi.");
    });
  }
  function importWorkflow() {
    const input = node("input", "import-input");
    input.type = "file";
    input.accept = ".json,application/json";
    input.addEventListener("change", () =>
      attempt(async () => {
        const file = input.files?.[0];
        if (!file) return;
        if (file.size > 2 * 1024 * 1024)
          throw new Error("Akış dosyası en fazla 2 MB olabilir.");
        let data;
        try {
          data = JSON.parse(await file.text());
        } catch {
          throw new Error("Geçerli bir JSON akış dosyası seçin.");
        }
        const w = await api("/api/workflows/import", {
          method: "POST",
          body: JSON.stringify(data),
        });
        upsert(state.workflows, w);
        await openWorkflow(w.id);
        toast("Akış içe aktarıldı.");
      }),
    );
    input.click();
  }

  // Editor: all workflow mutations stay local until the owner explicitly saves.
  function editorPage() {
    if (!state.workflow)
      return empty("Akış bulunamadı", "Akış kütüphanesinden bir akış seçin.");
    const wrapper = node("div", "editor");
    const head = node("div", "editor-heading");
    const title = node("div", "editor-title");
    title.append(
      iconButton("Akışlara dön", "back", () => navigate("workflows")),
    );
    const titleCopy = node("div");
    titleCopy.append(node("h1", "", state.workflow.name));
    const saved = node("div");
    saved.id = "saved-label";
    titleCopy.append(saved);
    title.append(
      titleCopy,
      iconButton("Akış bilgilerini düzenle", "edit", () =>
        workflowMetadata(state.workflow, (data, d) => {
          Object.assign(state.workflow, data);
          markDirty();
          d.close();
          renderPage();
        }),
      ),
    );
    const actions = node("div", "editor-actions");
    const dry = node("label", "checkbox-label");
    const check = node("input");
    check.type = "checkbox";
    check.checked = state.dryRun;
    check.addEventListener("change", () => {
      state.dryRun = check.checked;
    });
    dry.append(check, node("span", "", "Deneme modu"));
    actions.append(
      dry,
      iconButton("Akışı JSON olarak dışa aktar", "download", exportWorkflow),
      button("Kaydet", "save", saveWorkflow),
      button("Çalıştır", "play", runWorkflow, "primary"),
    );
    head.append(title, actions);
    wrapper.append(head);
    const workspace = node("div", "editor-workspace");
    const library = node("aside", "step-library");
    library.id = "step-library";
    const canvas = node("section", "flow-canvas");
    canvas.id = "flow-canvas";
    canvas.setAttribute("aria-label", "Akış adımları");
    const inspector = node("aside", "inspector");
    inspector.id = "inspector";
    workspace.append(library, canvas, inspector);
    wrapper.append(workspace);
    queueMicrotask(() => {
      updateSavedLabel();
      renderLibrary();
      renderCanvas();
      renderInspector();
    });
    return wrapper;
  }
  function renderLibrary() {
    const pane = document.getElementById("step-library");
    if (!pane) return;
    pane.replaceChildren(
      node("div", "pane-heading", "Adım kütüphanesi"),
      node("p", "pane-caption", "Akışınıza eklemek için bir adım seçin."),
    );
    const target = node("div", "library-target");
    if (state.target) {
      const parent = allSteps(state.workflow.steps).find(
        (s) => s.id === state.target.id,
      );
      if (!parent) state.target = null;
      else {
        target.append(
          node(
            "div",
            "",
            `Eklenecek yer: ${parent.title || specFor(parent.action).label} / ${state.target.branch === "otherwise" ? "Değilse" : "İç adımlar"}`,
          ),
          linkButton(
            "Ana akışa dön",
            () => {
              state.target = null;
              renderLibrary();
            },
            "back",
          ),
        );
      }
    }
    if (!state.target)
      target.append(node("span", "", "Eklenecek yer: Ana akışın sonu"));
    pane.append(target);
    if (!state.catalog.length) {
      pane.append(empty(
        "Kütüphane henüz boş",
        "İhtiyacınıza göre geliştirilen adımlar burada yer alacak. Eklenen adımları yıldızlayarak sık kullanılanlara taşıyabilirsiniz.",
      ));
      return;
    }
    const favorites = new Set(state.favorites);
    const pinned = state.favorites
      .map((type) => state.catalog.find((spec) => spec.type === type))
      .filter(Boolean);
    const groups = new Map([["Sık kullanılanlar", pinned]]);
    state.catalog.forEach((spec) => {
      if (favorites.has(spec.type)) return;
      const group = spec.category || "Genel";
      if (!groups.has(group)) groups.set(group, []);
      groups.get(group).push(spec);
    });
    for (const [category, specs] of groups) {
      const group = node("div", "library-group");
      group.append(node("h3", "", category));
      if (!specs.length)
        group.append(node("p", "pane-caption", "Sık kullandığınız adımları yıldızlayın; burada görünsün."));
      specs.forEach((spec) => {
        const row = node("div", "library-row");
        const action = node("button", "library-action");
        action.type = "button";
        action.title = spec.description || spec.label;
        action.append(
          icon(actionIcon(spec.type)),
          node("span", "", spec.label),
          node("span", "add-symbol", "+"),
        );
        action.addEventListener("click", () => addStep(spec));
        const favorite = favorites.has(spec.type);
        const star = iconButton(
          `${spec.label}: ${favorite ? "Favorilerden çıkar" : "Favoriye ekle"}`,
          "star",
          () => toggleFavorite(spec.type),
          `favorite-button${favorite ? " is-favorite" : ""}`,
        );
        star.dataset.favoriteType = spec.type;
        star.setAttribute("aria-pressed", String(favorite));
        star.disabled = state.favoriteSaving;
        row.append(action, star);
        group.append(row);
      });
      pane.append(group);
    }
  }
  async function toggleFavorite(type) {
    if (state.favoriteSaving) return;
    const favorite = !state.favorites.includes(type);
    state.favoriteSaving = true;
    document.querySelectorAll(".favorite-button").forEach((button) => {
      button.disabled = true;
    });
    try {
      state.favorites = await api(`/api/favorites/${encodeURIComponent(type)}`, {
        method: "PUT",
        body: JSON.stringify({ favorite }),
      });
      toast(favorite ? "Adım sık kullanılanlara eklendi." : "Adım favorilerden çıkarıldı.");
    } catch (error) {
      toast(error.message, true);
    } finally {
      state.favoriteSaving = false;
      const pane = document.getElementById("step-library");
      if (pane) {
        const scroll = pane.scrollTop;
        const restoreFocus = pane.contains(document.activeElement);
        renderLibrary();
        if (restoreFocus)
          pane.querySelector(`[data-favorite-type="${CSS.escape(type)}"]`)?.focus({ preventScroll: true });
        pane.scrollTop = scroll;
      }
    }
  }
  function findStep(id, steps = state.workflow?.steps || []) {
    for (let index = 0; index < steps.length; index++) {
      const step = steps[index];
      if (step.id === id) return { step, list: steps, index };
      const nested =
        findStep(id, step.children || []) || findStep(id, step.otherwise || []);
      if (nested) return nested;
    }
    return null;
  }
  function addStep(spec) {
    const params = {};
    (spec.fields || []).forEach((f) => {
      if (f.default !== undefined && f.default !== null)
        params[f.name] = clone(f.default);
    });
    const step = {
      id: uid(),
      title: spec.label,
      action: spec.type,
      params,
      children: [],
      otherwise: [],
    };
    let list = state.workflow.steps;
    if (state.target) {
      const parent = findStep(state.target.id);
      if (parent) {
        parent.step[state.target.branch] ||= [];
        list = parent.step[state.target.branch];
      }
    }
    list.push(step);
    state.selected = step.id;
    markDirty();
    renderCanvas();
    renderInspector();
    requestAnimationFrame(() =>
      document
        .querySelector(`[data-step-id="${CSS.escape(step.id)}"]`)
        ?.scrollIntoView({ block: "nearest", behavior: "smooth" }),
    );
  }
  function setTarget(step, branch) {
    state.target = { id: step.id, branch };
    renderLibrary();
    document
      .getElementById("step-library")
      ?.scrollTo({ top: 0, behavior: "smooth" });
    toast(
      `${branch === "otherwise" ? "Değilse" : "İç adımlar"} dalına eklemek için kütüphaneden adım seçin.`,
    );
  }
  function renderCanvas() {
    const pane = document.getElementById("flow-canvas");
    if (!pane) return;
    const oldScroll = pane.scrollTop;
    pane.replaceChildren();
    const caption = node("div", "canvas-caption");
    caption.append(
      node("span", "", "AKIŞ TASARIMI"),
      node(
        "span",
        "steps-total",
        `${countSteps(state.workflow.steps)} adım · ${state.workflow.department || "Genel"}`,
      ),
    );
    pane.append(caption);
    const stack = node("div", "flow-stack");
    const start = node("div", "flow-terminal");
    start.append(icon("play"), node("span", "", "Başlangıç"));
    stack.append(start, node("div", "flow-line"));
    if (!state.workflow.steps.length) {
      const placeholder = node("div", "flow-empty");
      placeholder.append(
        icon("flow"),
        node("h3", "", "İlk adımınızla başlayın"),
        node(
          "p",
          "",
          "Soldaki kütüphaneden bir eylem seçin. Sonra parametrelerini sağ panelde düzenleyin.",
        ),
      );
      stack.append(placeholder);
    } else
      state.workflow.steps.forEach((step, index) => {
        stack.append(
          stepCard(step, state.workflow.steps, index),
          node("div", "flow-line"),
        );
      });
    const add = node("button", "canvas-add");
    add.append(icon("plus"), node("span", "", "Ana akışa adım ekle"));
    add.addEventListener("click", () => {
      state.target = null;
      renderLibrary();
      document
        .getElementById("step-library")
        ?.scrollTo({ top: 0, behavior: "smooth" });
      toast("Soldaki kütüphaneden bir adım seçin.");
    });
    stack.append(add, node("div", "flow-line"));
    const end = node("div", "flow-terminal");
    end.append(icon("check"), node("span", "", "Bitiş"));
    stack.append(end);
    pane.append(stack);
    pane.scrollTop = oldScroll;
  }
  function stepCard(step, list, index) {
    const wrap = node("div", "step-wrap");
    const spec = specFor(step.action);
    const card = node(
      "div",
      `step-card${state.selected === step.id ? " selected" : ""}`,
    );
    card.dataset.stepId = step.id;
    card.tabIndex = 0;
    card.setAttribute("role", "button");
    card.setAttribute(
      "aria-label",
      `${step.title || spec.label} adımını düzenle`,
    );
    const select = () => {
      state.selected = step.id;
      renderCanvas();
      renderInspector();
    };
    card.addEventListener("click", select);
    card.addEventListener("keydown", (event) => {
      if (event.target === card && ["Enter", " "].includes(event.key)) {
        event.preventDefault();
        select();
      }
    });
    const main = node("div", "step-card-main");
    main.append(
      node("span", "step-number", String(index + 1).padStart(2, "0")),
    );
    const glyph = node("div", "step-icon");
    glyph.append(icon(actionIcon(step.action)));
    const copy = node("div", "step-copy");
    copy.append(
      node("strong", "", step.title || spec.label),
      node("small", "", spec.label),
    );
    const tools = node("div", "step-tools");
    const up = iconButton("Adımı yukarı taşı", "up", () =>
      moveStep(step.id, -1),
    );
    up.disabled = index === 0;
    const down = iconButton("Adımı aşağı taşı", "down", () =>
      moveStep(step.id, 1),
    );
    down.disabled = index === list.length - 1;
    tools.append(
      up,
      down,
      iconButton("Adımı sil", "cross", () => removeStep(step.id), "danger"),
    );
    main.append(glyph, copy, tools);
    card.append(main);
    if (step.params?.output) {
      const out = node("div", "step-output mono");
      out.append(
        icon("arrow"),
        node("span", "", "${" + step.params.output + "}"),
      );
      card.append(out);
    }
    wrap.append(card);
    const container =
      spec.container ||
      (/for_each|loop/.test(step.action)
        ? "loop"
        : /^if$|condition/.test(step.action)
          ? "condition"
          : null);
    if (container || step.children?.length || step.otherwise?.length) {
      const branches =
        container === "condition" || step.otherwise?.length
          ? ["children", "otherwise"]
          : ["children"];
      branches.forEach((branch) => {
        const children = step[branch] || [];
        const group = node(
          "div",
          `branch${children.length ? "" : " empty-branch"}`,
        );
        const label =
          branch === "otherwise"
            ? "DEĞİLSE"
            : container === "loop"
              ? "HER ÖĞE İÇİN"
              : "KOŞUL DOĞRUYSA";
        const head = node("div", "branch-heading");
        head.append(
          node("span", "", label),
          linkButton("Adım ekle", () => setTarget(step, branch), "plus"),
        );
        group.append(head);
        if (!children.length) {
          const placeholder = node(
            "button",
            "branch-placeholder",
            "Bu dala adım ekle",
          );
          placeholder.addEventListener("click", () => setTarget(step, branch));
          group.append(placeholder);
        }
        children.forEach((child, childIndex) => {
          if (childIndex) group.append(node("div", "flow-line"));
          group.append(stepCard(child, children, childIndex));
        });
        wrap.append(group);
      });
    }
    return wrap;
  }
  function moveStep(id, direction) {
    const located = findStep(id);
    if (!located) return;
    const to = located.index + direction;
    if (to < 0 || to >= located.list.length) return;
    [located.list[located.index], located.list[to]] = [
      located.list[to],
      located.list[located.index],
    ];
    markDirty();
    renderCanvas();
  }
  async function removeStep(id) {
    const located = findStep(id);
    if (!located) return;
    if (
      (located.step.children?.length || located.step.otherwise?.length) &&
      !(await confirmDialog(
        "Adımı ve alt adımlarını sil",
        "Bu adımın içindeki bütün alt adımlar da kaldırılacak.",
        "Adımı sil",
        true,
      ))
    )
      return;
    const removedIds = new Set(allSteps([located.step]).map((s) => s.id));
    located.list.splice(located.index, 1);
    for (const key of state.fieldErrors)
      if ([...removedIds].some((removed) => key.startsWith(`${removed}:`)))
        state.fieldErrors.delete(key);
    if (removedIds.has(state.selected)) state.selected = null;
    if (state.target && removedIds.has(state.target.id)) state.target = null;
    markDirty();
    renderLibrary();
    renderCanvas();
    renderInspector();
  }
  function duplicateStep(id) {
    const located = findStep(id);
    if (!located) return;
    const copied = clone(located.step);
    allSteps([copied]).forEach((s) => {
      s.id = uid();
    });
    copied.title = `${copied.title || specFor(copied.action).label} (kopya)`;
    located.list.splice(located.index + 1, 0, copied);
    state.selected = copied.id;
    markDirty();
    renderCanvas();
    renderInspector();
  }

  function windowRecognitionTools(step) {
    const tools = node("div", "window-recognition-tools");
    const result = node("div");
    result.id = "window-check-result";
    result.setAttribute("role", "status");
    const check = button("Şimdi kontrol et", "eye", async () => {
      check.disabled = true;
      const selector = {
        application: step.params.application || "",
        title: step.params.title || "",
        match: step.params.match || "exact",
      };
      const unchanged = () => tools.isConnected &&
        selector.application === (step.params.application || "") &&
        selector.title === (step.params.title || "") &&
        selector.match === (step.params.match || "exact");
      result.replaceChildren(node("p", "help", "Pencere kontrol ediliyor…"));
      try {
        if (!selector.title.trim()) throw new Error("Önce bir pencere seçin veya başlığını yazın.");
        const found = await api("/api/desktop/windows/check", {
          method: "POST", body: JSON.stringify(selector),
        });
        if (unchanged()) result.replaceChildren(note(
          found.found
            ? `Pencere bulundu: ${found.title} (${found.width} × ${found.height}).`
            : "Pencere bulunamadı. ERP ekranını açın veya başlık eşleşmesini düzenleyin.",
          found.found ? "info" : "", found.found ? "check" : "info",
        ));
      } catch (error) {
        if (unchanged()) result.replaceChildren(note(error.message));
      } finally {
        check.disabled = false;
      }
    });
    tools.append(
      button("Açık pencerelerden seç", "desktop", () => pickWindow(step)),
      check,
      node("p", "pane-caption", "Kontrol pencere başlığını arar; içeriğini incelemez. ERP penceresini görünür tutun."),
      result,
    );
    return tools;
  }
  function pickWindow(step) {
    const workflow = state.workflow;
    dialog("ERP penceresini tanıt", (body, d) => {
      body.append(node("p", "pane-caption", "ERP penceresini açık tutun ve listeden seçin. Başlık ve uygulama adı adıma aktarılacak."));
      const search = textInput("", "Uygulama veya pencere başlığı ara…", "search");
      search.setAttribute("aria-label", "Açık pencerelerde ara");
      const list = node("div", "window-picker-list");
      const status = node("div");
      status.setAttribute("role", "status");
      let windows = [];
      const render = () => {
        list.replaceChildren();
        const query = search.value.toLocaleLowerCase("tr");
        const filtered = windows.filter((w) => `${w.application} ${w.title}`.toLocaleLowerCase("tr").includes(query));
        if (!filtered.length) list.append(node("p", "help", "Eşleşen pencere yok. ERP ekranını görünür hale getirip listeyi yenileyin."));
        filtered.forEach((w) => {
          const choose = button(w.title, "desktop", () => {
            if (state.workflow !== workflow || findStep(step.id)?.step !== step) {
              d.close();
              return;
            }
            Object.assign(step.params, { application: w.application, title: w.title, match: "exact" });
            for (const name of ["application", "title", "match"]) {
              state.fieldErrors.delete(`${step.id}:${name}`);
              state.drafts.delete(`${step.id}:${name}`);
            }
            markDirty();
            d.close();
            renderInspector();
            renderCanvas();
            toast("Pencere tanıtıldı. Şimdi kontrol et ile eşleşmeyi doğrulayabilirsiniz.");
          }, "window-picker-choice");
          choose.append(node("small", "", `${w.application || "Uygulama adı okunamadı"} · ${w.width} × ${w.height}`));
          list.append(choose);
        });
      };
      const refresh = button("Listeyi yenile", "refresh", load);
      async function load() {
        refresh.disabled = true;
        list.replaceChildren();
        status.replaceChildren(node("p", "help", "Açık pencereler okunuyor…"));
        try {
          windows = await api("/api/desktop/windows");
          if (!d.isConnected) return;
          status.replaceChildren();
          render();
        } catch (error) {
          windows = [];
          status.replaceChildren(note(error.message));
        } finally {
          refresh.disabled = false;
        }
      }
      search.addEventListener("input", render);
      body.append(search, refresh, status, list);
      queueMicrotask(load);
    });
  }
  function renderInspector() {
    const pane = document.getElementById("inspector");
    if (!pane) return;
    pane.replaceChildren();
    const located = findStep(state.selected);
    if (!located) {
      pane.append(
        node("div", "pane-heading", "Adım ayarları"),
        node("p", "pane-caption", "Her adımın davranışını buradan tanımlayın."),
      );
      const blank = node("div", "inspector-empty");
      blank.append(
        icon("settings"),
        node("h3", "", "Bir adım seçin"),
        node(
          "p",
          "",
          "Parametrelerini düzenlemek için akıştaki bir adıma tıklayın.",
        ),
      );
      pane.append(
        blank,
        node("div", "inspector-divider"),
        note(
          "Deneme modu, dış sistemlerde işlem yapmadan akışınızın yapısını kontrol eder.",
        ),
      );
      return;
    }
    const step = located.step;
    const spec = specFor(step.action);
    pane.append(
      node("div", "eyebrow", "ADIM AYARLARI"),
      node("div", "pane-heading", spec.label),
      node("p", "pane-caption", spec.description),
    );
    const title = textInput(step.title || spec.label);
    title.maxLength = 200;
    title.addEventListener("input", () => {
      step.title = title.value;
      markDirty();
      renderCanvas();
    });
    pane.append(field("Adım adı", title), node("div", "inspector-divider"));
    step.params ||= {};
    if (step.action === "desktop.find_window") pane.append(windowRecognitionTools(step));
    (spec.fields || []).forEach((f) => {
      let control, jsonMode;
      const value = Object.hasOwn(step.params, f.name)
        ? step.params[f.name]
        : f.default;
      const key = `${step.id}:${f.name}`;
      if (f.type === "boolean") {
        control = node("input");
        control.type = "checkbox";
        control.checked = Boolean(value);
      } else if (f.type === "select") {
        control = node("select");
        if (!f.required) {
          const blank = node("option", "", "Seçin…");
          blank.value = "";
          control.append(blank);
        }
        (f.options || []).forEach((option) => {
          const opt = node(
            "option",
            "",
            typeof option === "string" ? option : option.label,
          );
          opt.value = typeof option === "string" ? option : option.value;
          control.append(opt);
        });
        control.value = value ?? "";
      } else if (f.type === "json") {
        control = node("textarea", "mono");
        control.rows = 3;
        control.spellcheck = false;
        jsonMode = node("select", "value-type");
        jsonMode.setAttribute("aria-label", `${f.label || f.name} değer türü`);
        for (const [kind, label] of [
          ["variable", "Akış değişkeni"],
          ["text", "Metin"],
          ["number", "Sayı"],
          ["boolean", "Doğru / yanlış"],
          ["json", "JSON (liste / nesne)"],
          ["null", "Boş (null)"],
        ]) {
          const option = node("option", "", label);
          option.value = kind;
          jsonMode.append(option);
        }
        jsonMode.value =
          value === null || value === undefined
            ? "null"
            : typeof value === "string"
              ? /^\$\{[^}]+\}$/.test(value)
                ? "variable"
                : "text"
              : typeof value === "number"
                ? "number"
                : typeof value === "boolean"
                  ? "boolean"
                  : "json";
        control.value = state.drafts.has(key)
          ? state.drafts.get(key).value
          : typeof value === "string"
            ? value
            : value === undefined || value === null
              ? ""
              : JSON.stringify(value, null, 2);
        if (state.drafts.has(key)) jsonMode.value = state.drafts.get(key).mode;
        control.placeholder = f.placeholder || "Değer girin";
      } else {
        control = textInput(
          value ?? "",
          f.placeholder || "",
          f.type === "number"
            ? "number"
            : f.type === "password"
              ? "password"
              : "text",
        );
        if (f.type === "number") {
          control.step = "any";
          if (f.min !== undefined) control.min = String(f.min);
          if (f.max !== undefined) control.max = String(f.max);
        }
      }
      const wrap = field(f.label || f.name, control, f.help, f.required);
      if (jsonMode) wrap.insertBefore(jsonMode, control);
      if (f.type === "boolean") {
        const label = wrap.querySelector("label");
        label.className = "checkbox-label";
        control.remove();
        label.prepend(control);
      }
      const error = node("div", "field-error");
      wrap.append(error);
      if (state.fieldErrors.has(key)) {
        control.classList.add("invalid");
        error.textContent = "Değer, seçilen veri türüne uygun değil.";
      }
      const change = () => {
        let next = control.value;
        const invalid = (message) => {
          state.fieldErrors.add(key);
          if (jsonMode)
            state.drafts.set(key, {
              value: control.value,
              mode: jsonMode.value,
            });
          error.textContent = message;
          control.classList.add("invalid");
          markDirty();
        };
        if (f.type === "boolean") next = control.checked;
        else if (f.type === "number") {
          if (next === "") next = undefined;
          else {
            next = Number(next);
            if (!Number.isFinite(next)) {
              invalid("Geçerli bir sayı girin.");
              return;
            }
          }
        } else if (jsonMode) {
          const kind = jsonMode.value;
          if (kind === "null") next = null;
          else if (kind === "variable") {
            next = next.trim();
            if (!/^\$\{[^}]+\}$/.test(next)) {
              invalid("Örnek değişken: ${orders} veya ${item.amount}");
              return;
            }
          } else if (kind === "number") {
            if (!next.trim() || !Number.isFinite(Number(next))) {
              invalid("Geçerli bir sayı girin.");
              return;
            }
            next = Number(next);
          } else if (kind === "boolean") {
            if (!["true", "false"].includes(next.trim())) {
              invalid("true (doğru) veya false (yanlış) girin.");
              return;
            }
            next = next.trim() === "true";
          } else if (kind === "json") {
            try {
              next = JSON.parse(next);
            } catch {
              invalid("Geçerli bir JSON listesi veya nesnesi girin.");
              return;
            }
          }
        }
        state.fieldErrors.delete(key);
        state.drafts.delete(key);
        error.textContent = "";
        control.classList.remove("invalid");
        if (next === undefined) delete step.params[f.name];
        else step.params[f.name] = next;
        if (step.action === "desktop.find_window")
          document.getElementById("window-check-result")?.replaceChildren();
        markDirty();
        if (f.name === "output") renderCanvas();
      };
      if (jsonMode) {
        const setModeView = () => {
          control.disabled = jsonMode.value === "null";
          control.placeholder = {
            variable: "${orders} veya ${item.amount}",
            text: "Metninizi tırnak işareti kullanmadan yazın",
            number: "Örn. 1000",
            boolean: "true veya false",
            json: '[{"alan": "değer"}]',
            null: "Boş değer",
          }[jsonMode.value];
          control.rows = jsonMode.value === "json" ? 5 : 2;
        };
        setModeView();
        jsonMode.addEventListener("change", () => {
          setModeView();
          change();
        });
      }
      control.addEventListener(
        f.type === "select" || f.type === "boolean" ? "change" : "input",
        change,
      );
      pane.append(wrap);
    });
    if (!spec.fields?.length)
      pane.append(note("Bu adım için ek parametre bulunmuyor."));
    pane.append(node("div", "inspector-divider"));
    const variables = node("div", "variables");
    variables.append(
      node("h3", "pane-heading", "Akış değişkenleri"),
      node(
        "p",
        "",
        "Önceki adımların çıktısını ${degisken} biçiminde kullanın. Bir etikete tıklayarak kopyalayın.",
      ),
    );
    const names = [
      ...new Set(
        allSteps(state.workflow.steps)
          .flatMap((s) => [
            s.params?.output,
            s.action === "desktop.find_window" && s.params?.output
              ? `${s.params.output}.found`
              : null,
            ["core.set", "data.append"].includes(s.action)
              ? s.params?.name
              : null,
            s.action === "control.for_each" ? s.params?.item_name : null,
          ])
          .filter(Boolean),
      ),
    ];
    names.push("item", "item.field");
    names.forEach((name) => {
      const expression = "${" + name + "}";
      const chip = node("button", "variable-chip mono", expression);
      chip.title = "Değişkeni kopyala";
      chip.addEventListener("click", () =>
        attempt(async () => {
          await navigator.clipboard.writeText(expression);
          toast("Değişken kopyalandı.");
        }),
      );
      variables.append(chip);
    });
    pane.append(
      variables,
      node("div", "inspector-divider"),
      button("Adımı çoğalt", "copy", () => duplicateStep(step.id), "small"),
    );
  }
  function workflowPayload() {
    const { name, description, department, steps } = state.workflow;
    return { name, description, department, steps };
  }
  async function saveWorkflow() {
    if (state.saving) return false;
    if (state.fieldErrors.size) {
      toast("Kaydetmeden önce geçersiz parametreleri düzeltin.", true);
      return false;
    }
    state.saving = true;
    const revision = state.revision;
    const id = state.workflow.id;
    try {
      const saved = await api(`/api/workflows/${encodeURIComponent(id)}`, {
        method: "PUT",
        body: JSON.stringify(workflowPayload()),
      });
      upsert(state.workflows, saved);
      if (state.workflow?.id === id && state.revision === revision) {
        // Inspector listeners reference the current step objects. Keep those
        // objects alive so editing immediately after saving still edits the flow.
        state.workflow.updated_at = saved.updated_at;
        state.workflow.created_at = saved.created_at;
        state.dirty = false;
      }
      updateSavedLabel();
      toast("Akış kaydedildi.");
      return !state.dirty;
    } catch (error) {
      toast(error.message, true);
      return false;
    } finally {
      state.saving = false;
    }
  }
  async function requireSaved() {
    if (!state.dirty) return true;
    if (
      !(await confirmDialog(
        "Önce değişiklikleri kaydedin",
        "Bu işlem akışın kaydedilmiş sürümünü kullanır. Son değişikliklerinizi kaydedip devam edebilirsiniz.",
        "Kaydet ve devam et",
      ))
    )
      return false;
    return saveWorkflow();
  }
  async function exportWorkflow() {
    const id = state.workflow?.id;
    if (!(await requireSaved())) return;
    if (state.page !== "editor" || state.workflow?.id !== id) return;
    const a = node("a");
    a.href = `/api/workflows/${encodeURIComponent(state.workflow.id)}/export`;
    a.download = "";
    document.body.append(a);
    a.click();
    a.remove();
  }
  async function runWorkflow() {
    if (state.starting) return;
    const id = state.workflow?.id;
    const dryRun = state.dryRun;
    if (!(await requireSaved())) return;
    if (state.page !== "editor" || state.workflow?.id !== id) return;
    if (!state.workflow.steps.length) {
      toast("Çalıştırmak için akışınıza en az bir adım ekleyin.", true);
      return;
    }
    state.starting = true;
    try {
      await attempt(async () => {
        const run = await api(`/api/workflows/${encodeURIComponent(id)}/run`, {
          method: "POST",
          body: JSON.stringify({ dry_run: dryRun }),
        });
        upsert(state.runs, run);
        if (state.page !== "editor" || state.workflow?.id !== id) {
          toast(
            "Akış başlatıldı. Durumunu çalışma geçmişinden izleyebilirsiniz.",
          );
          return;
        }
        stopPolling();
        state.run = run;
        state.page = "run";
        state.dirty = false;
        render();
        pollRun();
      });
    } finally {
      state.starting = false;
    }
  }

  function runsPage() {
    const page = node("div", "page");
    page.append(
      heading(
        "ÇALIŞMA ARŞİVİ",
        "Her çalışmanın bir izi var.",
        "Çalışma durumlarını inceleyin, günlükleri okuyun ve çıktıları indirin.",
        button("Yenile", "refresh", () =>
          attempt(async () => {
            state.runs = await api("/api/runs");
            renderPage();
          }),
        ),
      ),
    );
    const toolbar = node("div", "toolbar");
    const filter = node("select", "inline-select");
    filter.setAttribute("aria-label", "Çalışma durumunu filtrele");
    for (const [value, label] of [
      ["all", "Tüm çalışmalar"],
      ["succeeded", "Tamamlananlar"],
      ["failed", "Hatalı çalışmalar"],
      ["running", "Aktif çalışmalar"],
      ["dry", "Deneme çalışmaları"],
    ]) {
      const option = node("option", "", label);
      option.value = value;
      filter.append(option);
    }
    filter.value = state.runFilter;
    filter.addEventListener("change", () => {
      state.runFilter = filter.value;
      renderPage();
    });
    toolbar.append(
      node("span", "small muted", `${state.runs.length} çalışma kaydı`),
      filter,
    );
    page.append(toolbar);
    const panel = node("div", "panel table-wrap");
    const rows = state.runs.filter(
      (run) =>
        state.runFilter === "all" ||
        (state.runFilter === "dry"
          ? run.dry_run
          : state.runFilter === "running"
            ? ["queued", "running"].includes(run.status)
            : run.status === state.runFilter),
    );
    if (!rows.length)
      panel.append(
        empty(
          "Çalışma bulunamadı",
          "Akışınızı çalıştırdıktan sonra günlüğünü ve çıktılarını burada inceleyebilirsiniz.",
        ),
      );
    else {
      const table = node("table", "data-table");
      const head = node("thead");
      const tr = node("tr");
      ["Akış", "Durum", "Başlangıç", "Süre", "Çıktı", ""].forEach((title) =>
        tr.append(node("th", "", title)),
      );
      head.append(tr);
      const body = node("tbody");
      rows.forEach((run) => {
        const row = node("tr");
        const name = node("td");
        name.append(
          node("div", "table-name", run.workflow_name),
          node(
            "div",
            "table-sub",
            `${run.department || "Genel"}${run.dry_run ? " · Deneme modu" : ""}`,
          ),
        );
        const status = node("td");
        status.append(badge(run.status));
        const go = node("td");
        go.append(linkButton("İncele", () => openRun(run.id)));
        row.append(
          name,
          status,
          node("td", "muted", when(run.started_at)),
          node("td", "muted", duration(run)),
          node("td", "muted", `${run.artifacts?.length || 0} dosya`),
          go,
        );
        body.append(row);
      });
      table.append(head, body);
      panel.append(table);
    }
    page.append(panel);
    return page;
  }
  function runPage() {
    const run = state.run;
    const page = node("div", "page");
    if (!run) return page;
    const actions = node("div", "actions");
    if (["queued", "running"].includes(run.status))
      actions.append(button("Durdur", "stop", cancelRun, "danger"));
    actions.append(
      button("Akışı aç", "flow", () => openWorkflow(run.workflow_id)),
    );
    page.append(
      heading(
        "ÇALIŞMA AYRINTISI",
        run.workflow_name,
        `${run.department || "Genel"} · ${when(run.started_at)}`,
        actions,
      ),
    );
    if (run.dry_run)
      page.append(
        note(
          "Deneme modu: bu çalışma dış sistemlerde gerçek işlem yapmaz. Adım yapısı ve yönlendirme doğrulanır; örnek çıktılar gerçek departman verisi değildir.",
          "warning",
        ),
      );
    if (run.error) {
      const err = note(run.error, "error");
      err.classList.add("run-error-note");
      page.append(err);
    }
    const layout = node("div", "run-layout");
    const logs = node("section", "panel");
    const summary = node("div", "run-summary");
    [
      ["Durum", badge(run.status)],
      ["Geçen süre", node("span", "", duration(run))],
      [
        "Çalışma türü",
        node("span", "", run.dry_run ? "Deneme" : "Gerçek çalışma"),
      ],
    ].forEach(([title, value]) => {
      const item = node("dl");
      const dd = node("dd");
      dd.append(value);
      item.append(node("dt", "", title), dd);
      summary.append(item);
    });
    logs.append(summary);
    const head = node("div", "log-head");
    head.append(
      node("h2", "", "Çalışma günlüğü"),
      node("span", "small muted", `${run.events?.length || 0} kayıt`),
    );
    logs.append(head);
    const list = node("div", "log-list");
    list.id = "run-log-list";
    list.setAttribute("aria-label", "Çalışma günlüğü");
    if (!run.events?.length)
      list.append(
        empty(
          "Çalışma hazırlanıyor",
          "Adımlar ilerledikçe günlük kayıtları burada görünecek.",
        ),
      );
    (run.events || []).forEach((event) => {
      const row = node("div", `log-row ${event.level || "info"}`);
      row.append(
        node("span", "log-time mono", when(event.timestamp, true)),
        node("span", "log-level mono", event.level || "info"),
        node("span", "log-message", event.message),
      );
      list.append(row);
    });
    logs.append(list);
    const outputs = node("section");
    outputs.append(
      sectionHeading(
        "Departman çıktıları",
        "Dosyaları indirip ilgili ekiple paylaşın.",
      ),
    );
    const artifacts = node("div", "panel");
    if (!run.artifacts?.length)
      artifacts.append(
        empty(
          "Henüz çıktı yok",
          "Dışa aktarma adımları çalıştığında oluşturulan dosyalar burada görünür.",
        ),
      );
    (run.artifacts || []).forEach((artifact) => {
      const item = node("div", "artifact-row");
      const title = node("div", "artifact-title");
      title.append(icon("file"), node("span", "", artifact.name));
      item.append(
        title,
        node(
          "p",
          "",
          `${artifact.department || run.department || "Genel"}${artifact.rows !== undefined ? ` · ${artifact.rows} satır` : ""}`,
        ),
      );
      const download = node("a", "button small");
      download.href = `/api/runs/${encodeURIComponent(run.id)}/artifacts/${encodeURIComponent(artifact.id)}`;
      download.download = artifact.name || "";
      download.append(icon("download"), node("span", "", "Dosyayı indir"));
      item.append(download);
      artifacts.append(item);
    });
    outputs.append(artifacts);
    if (run.dry_run && run.artifacts?.length) {
      const hint = note("Bu dosyalar deneme çalışmasına aittir.", "warning");
      hint.classList.add("artifact-note");
      outputs.append(hint);
    }
    layout.append(logs, outputs);
    page.append(layout);
    return page;
  }
  function stopPolling() {
    clearTimeout(state.poll);
    state.poll = null;
    state.pollEpoch += 1;
  }
  function pollRunList() {
    clearTimeout(state.poll);
    if (!["dashboard", "runs"].includes(state.page)) return;
    const epoch = state.pollEpoch;
    const page = state.page;
    const active = state.runs.some((run) =>
      ["queued", "running"].includes(run.status),
    );
    state.poll = setTimeout(
      async () => {
        try {
          const runs = await api("/api/runs");
          if (state.pollEpoch !== epoch || state.page !== page) return;
          const changed = JSON.stringify(state.runs) !== JSON.stringify(runs);
          state.runs = runs;
          if (changed && document.activeElement?.tagName !== "SELECT")
            renderPage();
        } catch (error) {
          if (state.pollEpoch !== epoch || state.page !== page) return;
          toast(`Çalışma listesi güncellenemedi: ${error.message}`, true);
        }
        if (state.pollEpoch === epoch && state.page === page) pollRunList();
      },
      active ? 2500 : 10000,
    );
  }
  function pollRun() {
    clearTimeout(state.poll);
    if (
      state.page !== "run" ||
      !state.run ||
      !["queued", "running"].includes(state.run.status)
    )
      return;
    const id = state.run.id;
    const epoch = state.pollEpoch;
    state.poll = setTimeout(async () => {
      try {
        const run = await api(`/api/runs/${encodeURIComponent(id)}`);
        if (
          state.page !== "run" ||
          state.run?.id !== id ||
          state.pollEpoch !== epoch
        )
          return;
        const list = document.getElementById("run-log-list");
        const atBottom =
          !list || list.scrollTop + list.clientHeight >= list.scrollHeight - 40;
        const scroll = list?.scrollTop || 0;
        state.run = run;
        upsert(state.runs, run);
        renderPage();
        const newList = document.getElementById("run-log-list");
        if (newList)
          newList.scrollTop = atBottom ? newList.scrollHeight : scroll;
        pollRun();
      } catch (error) {
        if (
          state.page !== "run" ||
          state.run?.id !== id ||
          state.pollEpoch !== epoch
        )
          return;
        toast(`Çalışma durumu alınamadı: ${error.message}`, true);
        if (state.page === "run" && state.run?.id === id)
          state.poll = setTimeout(pollRun, 5000);
      }
    }, 1200);
  }
  async function cancelRun() {
    const id = state.run?.id;
    if (!id) return;
    await attempt(async () => {
      const run = await api(`/api/runs/${encodeURIComponent(id)}/cancel`, {
        method: "POST",
      });
      upsert(state.runs, run);
      if (state.page === "run" && state.run?.id === id) {
        state.run = run;
        renderPage();
        pollRun();
      }
      toast("Durdurma isteği gönderildi.");
    });
  }

  function settingsPage() {
    const page = node("div", "page");
    page.append(
      heading(
        "ÇALIŞMA ALANI AYARLARI",
        "Sistemlerinizi bağlayın.",
        "Otomasyonlarınızın kullanacağı bağlantıları ve çalışma ortamını yönetin.",
      ),
    );
    const layout = node("div", "settings-layout");
    const form = node("form");
    const controls = {};
    const removals = {};
    function setting(name, label, value, help, options = {}) {
      const input = options.multiline
        ? node("textarea", options.mono ? "mono" : "")
        : textInput(value, options.placeholder || "", options.type || "text");
      if (options.multiline) input.value = value || "";
      if (options.secret) {
        input.autocomplete = "new-password";
        input.spellcheck = false;
      }
      controls[name] = input;
      return field(label, input, help);
    }
    function removeConnection(name, label) {
      const wrap = node("div", "connection-removal");
      const checkbox = node("input");
      checkbox.type = "checkbox";
      const text = node("label", "checkbox-label");
      text.append(checkbox, node("span", "", label));
      wrap.append(
        text,
        node(
          "p",
          "help",
          "Ayarları kaydettiğinizde kayıtlı bağlantı bilgisi temizlenir.",
        ),
      );
      removals[name] = checkbox;
      checkbox.addEventListener("change", () => {
        controls[name].disabled = checkbox.checked;
      });
      return wrap;
    }
    function panel(title, glyph, description, status) {
      const el = node("section", "panel settings-panel");
      const h = node("h2");
      h.append(icon(glyph), node("span", "", title));
      if (status !== undefined)
        h.append(
          node(
            "span",
            `pill${status ? " success" : ""}`,
            status ? "Yapılandırıldı" : "Bağlantı yok",
          ),
        );
      el.append(h, node("p", "", description));
      return el;
    }
    const updatePanel = panel(
      "Uygulama güncellemeleri", "refresh",
      "Yeni sürümler arka planda indirilir; indirilen sürüm bir sonraki açılışta kurulur. Akışlarınız ve bağlantı ayarlarınız korunur.",
    );
    updatePanel.append(node("p", "", `Yüklü sürüm: ${state.version}`));
    const updateMessage = node("p", "update-message", state.updates.message || "Güncelleme durumu yükleniyor…");
    updateMessage.id = "update-message";
    updateMessage.setAttribute("role", "status");
    const checkUpdate = button("Güncellemeleri kontrol et", "refresh", () => attempt(async () => {
      checkUpdate.disabled = true;
      try {
        state.updates = await api("/api/updates/check", { method: "POST" });
        paintUpdates();
      } finally {
        checkUpdate.disabled = !state.updates.enabled;
      }
    }));
    checkUpdate.id = "check-update";
    checkUpdate.disabled = !state.updates.enabled;
    const downloads = node("a", "button", "İndirme sayfası");
    downloads.href = "https://orkestrai.net/rpa/";
    downloads.target = "_blank";
    downloads.rel = "noopener noreferrer";
    const updateActions = node("div", "update-actions");
    updateActions.append(checkUpdate, downloads);
    updatePanel.append(updateMessage, updateActions);
    form.append(updatePanel);
    const db = panel(
      "Veritabanı",
      "database",
      "PostgreSQL veya SQL Server için yalnızca SELECT yetkili bir hesap kullanın.",
      state.settings.database_configured,
    );
    db.append(
      setting(
        "database_url",
        "Bağlantı adresi",
        "",
        state.settings.database_configured
          ? "Kayıtlı bağlantı gizlenir. Değiştirmek istemiyorsanız boş bırakın."
          : "Bağlantı bilgisi bu bilgisayarda saklanır; akış dosyalarına eklenmez.",
        {
          type: "password",
          secret: true,
          placeholder:
            "postgresql+psycopg://kullanici:parola@sunucu/veritabani",
        },
      ),
      setting(
        "allowed_tables",
        "İzin verilen tablolar",
        Array.isArray(state.settings.allowed_tables)
          ? state.settings.allowed_tables.join(", ")
          : state.settings.allowed_tables || "",
        "Tablo adlarını şemasıyla, virgülle ayırın. Örnek: public.IASSALITEM, public.IASINVITEM",
      ),
    );
    if (state.settings.database_configured)
      db.append(
        removeConnection(
          "database_url",
          "Kayıtlı veritabanı bağlantısını kaldır",
        ),
      );
    const sheets = panel(
      "Google Sheets",
      "sheet",
      "Servis hesabınızın erişebildiği elektronik tablolarda çalışın.",
      state.settings.sheets_configured,
    );
    sheets.append(
      setting(
        "google_credentials_path",
        "Servis hesabı anahtar dosyası",
        "",
        state.settings.sheets_configured
          ? "Kayıtlı dosya yolu gizlenir. Mevcut ayarı korumak için boş bırakın."
          : "Yerel JSON anahtar dosyasının tam yolu. Tablonuzu servis hesabı e-postasıyla paylaşın.",
        {
          secret: true,
          placeholder: "/…/credentials/google-service-account.json",
        },
      ),
    );
    if (state.settings.sheets_configured)
      sheets.append(
        removeConnection(
          "google_credentials_path",
          "Kayıtlı Google Sheets bağlantısını kaldır",
        ),
      );
    const vision = panel(
      "Masaüstü ve görsel algılama",
      "eye",
      "OCR ve şablon eşleştirmenin kullanacağı yerel kaynakları belirleyin.",
    );
    vision.append(
      setting(
        "tesseract_cmd",
        "Tesseract çalıştırılabilir dosyası",
        state.settings.tesseract_cmd || "",
        "Sistem PATH ayarını kullanmak için boş bırakın.",
        { placeholder: "Örn. /opt/homebrew/bin/tesseract" },
      ),
      setting(
        "ocr_language",
        "OCR dili",
        state.settings.ocr_language || "tur+eng",
        "Tesseract içinde ilgili dil paketlerinin kurulu olması gerekir.",
        { placeholder: "tur+eng" },
      ),
      setting(
        "template_dir",
        "Görsel şablon klasörü",
        state.settings.template_dir || "",
        "Buton ve pencere eşleştirmede kullanılacak görsellerin bulunduğu klasör.",
        { placeholder: "assets/templates" },
      ),
    );
    form.append(db, sheets, vision);
    const foot = node("div", "settings-actions");
    const save = button("Ayarları kaydet", "save", null, "primary");
    save.type = "submit";
    foot.append(save);
    form.append(foot);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      attempt(async () => {
        const payload = {
          allowed_tables: controls.allowed_tables.value
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          tesseract_cmd: controls.tesseract_cmd.value.trim(),
          ocr_language: controls.ocr_language.value.trim(),
          template_dir: controls.template_dir.value.trim(),
        };
        if (removals.database_url?.checked) payload.database_url = "";
        else if (controls.database_url.value.trim())
          payload.database_url = controls.database_url.value.trim();
        if (removals.google_credentials_path?.checked)
          payload.google_credentials_path = "";
        else if (controls.google_credentials_path.value.trim())
          payload.google_credentials_path =
            controls.google_credentials_path.value.trim();
        save.disabled = true;
        try {
          state.settings = await api("/api/settings", {
            method: "PUT",
            body: JSON.stringify(payload),
          });
          renderPage();
          toast("Bağlantı ayarları kaydedildi.");
        } finally {
          save.disabled = false;
        }
      });
    });
    const aside = node("aside", "settings-aside");
    aside.append(
      note(
        "Gizli bağlantı bilgileri dışa aktarılan akışlara eklenmez. Her bilgisayar kendi bağlantı ayarlarını kullanır.",
        "",
        "shield",
      ),
      node("h3", "", "Masaüstü otomasyonu"),
      node(
        "p",
        "",
        "Masaüstü adımları, bu uygulamanın çalıştığı bilgisayardaki açık kullanıcı oturumunu kontrol eder. Çalışma sırasında ekranı kilitlemeyin ve fareyi başka işler için kullanmayın.",
      ),
      node("h3", "", "macOS izinleri"),
      node(
        "p",
        "",
        "Kurulu RpaOrkestrAI uygulamasına Sistem Ayarları içinden Erişilebilirlik ve Ekran Kaydı izinleri verin. Kaynak kodla çalışıyorsanız izinler kullandığınız Python veya Terminal için gerekir.",
      ),
      node("h3", "", "Windows ve ekran ölçeği"),
      node(
        "p",
        "",
        "Görsel şablonları kullanacağınız ekran ölçeğinde hazırlayın. Koordinata dayalı adımlarda pencere konumunu sabit tutun.",
      ),
      node("h3", "", "Web otomasyonu"),
      node(
        "p",
        "",
        "Playwright tarayıcısı arka planda çalışabilir. Kurulum sırasında Chromium tarayıcısını indirdiğinizden emin olun.",
      ),
      note(
        "Yapılandırıldı etiketi, ayarın kaydedildiğini belirtir. Bağlantıya erişim ilgili adım çalıştırıldığında doğrulanır.",
        "info",
      ),
    );
    layout.append(form, aside);
    page.append(layout);
    return page;
  }

  async function boot() {
    try {
      const data = await api("/api/bootstrap");
      state.workflows = data.workflows || [];
      state.runs = data.runs || [];
      state.catalog = data.catalog || [];
      state.actionDefinitions = data.action_definitions || [];
      state.favorites = data.favorites || [];
      state.settings = data.settings || {};
      state.platform = data.platform || state.settings.platform || "";
      state.version = data.version || "";
      state.updates = data.updates || {};
      render();
      pollRunList();
      pollUpdates();
    } catch (error) {
      root.replaceChildren();
      root.setAttribute("aria-busy", "false");
      const screen = node("main", "boot-screen");
      const content = node("div", "connection-error");
      content.append(
        icon("info"),
        node("h1", "", "Stüdyoya bağlanılamadı"),
        node("p", "", error.message),
        button("Yeniden dene", "refresh", boot, "primary"),
      );
      screen.append(content);
      root.append(screen);
    }
  }
  function paintUpdates() {
    const message = document.getElementById("update-message");
    if (message) message.textContent = state.updates.message || "";
    const notice = document.getElementById("update-notice");
    if (notice) notice.hidden = state.updates.status !== "ready";
    const check = document.getElementById("check-update");
    if (check) check.disabled = !state.updates.enabled || ["checking", "downloading"].includes(state.updates.status);
  }
  function pollUpdates() {
    clearTimeout(state.updatePoll);
    if (!state.updates.enabled) return;
    state.updatePoll = setTimeout(async () => {
      try {
        state.updates = await api("/api/updates");
        paintUpdates();
      } catch (_) {
        // An offline update check must not interrupt the editor or its unsaved work.
      }
      pollUpdates();
    }, 10000);
  }
  window.addEventListener("beforeunload", (event) => {
    if (state.dirty) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  boot();
})();
