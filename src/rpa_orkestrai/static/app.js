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
    license: null,
    licenseTimer: null,
    page: "dashboard",
    workflow: null,
    selected: null,
    target: null,
    dirty: false,
    dryRun: false,
    drag: null,
    librarySearch: "",
    testValues: {},
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
    logout: "M15 4h4v16h-4 M10 16l-4-4 4-4 M6 12h10",
    grip: "M9 5h.01 M9 12h.01 M9 19h.01 M15 5h.01 M15 12h.01 M15 19h.01",
    record: "M7 12a5 5 0 1 0 10 0a5 5 0 1 0-10 0 M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0",
    mouse: "M12 3a6 6 0 0 1 6 6v6a6 6 0 0 1-12 0V9a6 6 0 0 1 6-6z M12 3v6",
    keyboard: "M3 6h18v12H3z M7 10h.01 M11 10h.01 M15 10h.01 M7 14h10",
    window: "M3 4h18v16H3z M3 8h18",
    shield2: "M12 2l8 3v7c0 5-8 10-8 10S4 17 4 12V5z",
    message: "M4 4h16v12H8l-4 4z",
    target: "M12 3v4 M12 17v4 M3 12h4 M17 12h4 M12 12h.01",
    key: "M14 10a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M13 12l8 8 M17 16l2-2 M19 18l2-2",
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
    if (/^input\.(mouse|drag|scroll)/.test(type)) return "mouse";
    if (/^input\./.test(type)) return "keyboard";
    if (/^window\.|find_window/.test(type)) return "window";
    if (/^ui\./.test(type)) return "message";
    if (/control\.try/.test(type)) return "shield2";
    if (/control\.repeat/.test(type)) return "loop";
    if (/^http\./.test(type)) return "globe";
    if (/^data\.calculate|^text\.|^data\.date|^data\.list/.test(type)) return "code";
    if (/^system\.|clipboard/.test(type)) return "terminal";
    if (/database|sql|query/.test(type)) return "database";
    if (/sheet/.test(type)) return "sheet";
    if (/browser|web|playwright/.test(type)) return "globe";
    if (/for_each|while|loop|dropdown/.test(type)) return "loop";
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
      let body = null;
      try {
        body = await response.json();
        detail =
          typeof body.detail === "string"
            ? body.detail
            : JSON.stringify(body.detail || body);
      } catch {
        detail = `HTTP ${response.status}`;
      }
      // The local API refuses work once the license is no longer valid.
      if (response.status === 403 && body?.license?.state && body.license.state !== "valid"
          && !root.querySelector(".license-screen"))
        showLicenseGate(body.license);
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
    const account = state.license?.license || {};
    const ownerName = account.full_name || account.user || "Lisanslı kullanıcı";
    owner.append(node("div", "avatar", initials(ownerName)));
    const ownerText = node("div", "owner-text");
    ownerText.append(
      node("strong", "", ownerName),
      node("small", "", [account.company, licenseTerm(account)].filter(Boolean).join(" · ")),
    );
    owner.append(
      ownerText,
      iconButton("Oturumu kapat", "logout", () => logoutLicense(), "owner-logout"),
    );
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
      node("span", "version", `v${state.version || "0.6.0"}`),
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
        "Önizlemeler hariç",
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
          `${when(run.started_at)}${run.test_step_id ? " · Adım testi" : run.dry_run ? " · Önizleme" : ""}`,
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
    dry.append(check, node("span", "", "Önizleme (ekranı kullanmadan)"));
    dry.title = "Açıkken fare, klavye, ekran, dosya ve bağlantı adımları atlanır; yalnız veri adımları hesaplanır.";
    const recorder = button("Hareketleri kaydet", "record", recordMovements);
    recorder.title = "Fare ve klavye hareketlerinizi kaydedip adımlara çevirir.";
    actions.append(
      dry,
      recorder,
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
    const search = textInput(state.librarySearch, "Adım ara: tıkla, excel, bekle, ocr…", "search");
    search.className = "field-input library-search";
    search.setAttribute("aria-label", "Adım ara");
    search.addEventListener("input", () => {
      state.librarySearch = search.value;
      filterLibrary(pane);
    });
    pane.append(search);
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
        action.draggable = true;
        action.addEventListener("dragstart", (event) => startDrag(event, { kind: "new", type: spec.type }));
        action.addEventListener("dragend", endDrag);
        row.dataset.search = searchText(`${spec.label} ${spec.description || ""} ${spec.category || ""} ${spec.type}`);
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
    filterLibrary(pane);
  }
  function searchText(value) {
    return String(value).replace(/[İIı]/g, "i").toLocaleLowerCase("tr");
  }
  function filterLibrary(pane) {
    const words = searchText(state.librarySearch).split(/\s+/).filter(Boolean);
    pane.querySelectorAll(".library-row").forEach((row) => {
      row.hidden = !words.every((word) => row.dataset.search.includes(word));
    });
    pane.querySelectorAll(".library-group").forEach((group) => {
      const rows = group.querySelectorAll(".library-row");
      group.hidden = words.length > 0 && rows.length > 0 && [...rows].every((row) => row.hidden);
      if (words.length && !rows.length) group.hidden = true;
    });
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
    const step = buildStep(spec, state.target?.id);
    let list = state.workflow.steps;
    if (state.target) {
      const parent = findStep(state.target.id);
      if (parent) {
        parent.step[state.target.branch] ||= [];
        list = parent.step[state.target.branch];
      }
    }
    list.push(step);
    selectNewStep(step);
  }
  function selectNewStep(step) {
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
  function buildStep(spec, parentId) {
    const params = {};
    (spec.fields || []).forEach((f) => {
      if (f.default !== undefined && f.default !== null)
        params[f.name] = clone(f.default);
    });
    if (spec.type === "desktop.window_fill" && parentId) {
      const loop = [...(enclosingSteps(parentId) || []), findStep(parentId)?.step].filter(Boolean).reverse()
        .find((step) => step.action === "control.for_each");
      const producer = loop && loopDataSource(loop);
      if (producer?.action === "sheets.read_rows") {
        const key = parameterValue(producer, "key");
        const item = parameterValue(loop, "item_name");
        if (key && item) params.text = "${" + item + "." + key + "}";
      }
    }
    return {
      id: uid(),
      title: spec.label,
      action: spec.type,
      params,
      children: [],
      otherwise: [],
    };
  }
  // ----- drag and drop -------------------------------------------------------
  function subtreeDepth(step) {
    const nested = [...(step.children || []), ...(step.otherwise || [])];
    return 1 + (nested.length ? Math.max(...nested.map(subtreeDepth)) : 0);
  }
  function containsStep(root, id) {
    return allSteps([root]).some((candidate) => candidate.id === id);
  }
  function clearDropMarks() {
    document.querySelectorAll(".drop-before, .drop-after, .drop-inside").forEach((el) =>
      el.classList.remove("drop-before", "drop-after", "drop-inside"));
  }
  function startDrag(event, payload) {
    state.drag = payload;
    event.dataTransfer.effectAllowed = payload.kind === "new" ? "copy" : "move";
    // Firefox/WebKit need data to start a drag; the payload itself stays in memory.
    event.dataTransfer.setData("text/plain", payload.kind === "new" ? payload.type : payload.id);
    document.body.classList.add("dragging-step");
  }
  function endDrag() {
    state.drag = null;
    clearDropMarks();
    document.body.classList.remove("dragging-step");
  }
  function dropInto(list, index, ownerId) {
    const drag = state.drag;
    endDrag();
    if (!drag || !state.workflow) return;
    const ownerDepth = ownerId ? (enclosingSteps(ownerId) || []).length + 1 : 0;
    if (drag.kind === "new") {
      const spec = state.catalog.find((item) => item.type === drag.type);
      if (!spec) return;
      if (ownerDepth + 1 > 12) return toast("Akış en fazla 12 seviye iç içe olabilir.", true);
      const step = buildStep(spec, ownerId);
      list.splice(Math.max(0, Math.min(index, list.length)), 0, step);
      selectNewStep(step);
      return;
    }
    const located = findStep(drag.id);
    if (!located) return;
    if (ownerId && containsStep(located.step, ownerId))
      return toast("Bir adım kendi içine taşınamaz.", true);
    if (ownerDepth + subtreeDepth(located.step) > 12)
      return toast("Akış en fazla 12 seviye iç içe olabilir.", true);
    let target = index;
    if (located.list === list && located.index < index) target -= 1;
    if (located.list === list && located.index === target) return;
    located.list.splice(located.index, 1);
    list.splice(Math.max(0, Math.min(target, list.length)), 0, located.step);
    state.selected = located.step.id;
    markDirty();
    renderCanvas();
    renderInspector();
  }
  function dropZone(el, resolve) {
    // resolve(event) → {list, index, ownerId, mark: "before" | "after" | "inside", target}
    el.addEventListener("dragover", (event) => {
      if (!state.drag) return;
      const place = resolve(event);
      if (!place) return;
      event.preventDefault();
      event.stopPropagation();
      event.dataTransfer.dropEffect = state.drag.kind === "new" ? "copy" : "move";
      clearDropMarks();
      place.target.classList.add(`drop-${place.mark}`);
    });
    el.addEventListener("dragleave", (event) => {
      if (!el.contains(event.relatedTarget)) el.classList.remove("drop-before", "drop-after", "drop-inside");
    });
    el.addEventListener("drop", (event) => {
      if (!state.drag) return;
      const place = resolve(event);
      if (!place) return;
      event.preventDefault();
      event.stopPropagation();
      dropInto(place.list, place.index, place.ownerId);
    });
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
      dropZone(placeholder, () => ({ list: state.workflow.steps, index: 0, ownerId: null, mark: "inside", target: placeholder }));
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
    dropZone(add, () => ({ list: state.workflow.steps, index: state.workflow.steps.length, ownerId: null,
      mark: "inside", target: add }));
    add.title = "Kütüphaneden adım seçin veya bir adımı buraya sürükleyin.";
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
    card.draggable = true;
    card.addEventListener("dragstart", (event) => {
      event.stopPropagation();
      startDrag(event, { kind: "move", id: step.id });
      requestAnimationFrame(() => card.classList.add("drag-source"));
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("drag-source");
      endDrag();
    });
    dropZone(card, (event) => {
      const bounds = card.getBoundingClientRect();
      const after = event.clientY > bounds.top + bounds.height / 2;
      const current = list.indexOf(step);
      const owner = (enclosingSteps(step.id) || []).at(-1);
      return { list, index: after ? current + 1 : current, ownerId: owner?.id || null,
        mark: after ? "after" : "before", target: card };
    });
    card.addEventListener("keydown", (event) => {
      if (event.target === card && ["Enter", " "].includes(event.key)) {
        event.preventDefault();
        select();
      }
    });
    const main = node("div", "step-card-main");
    const grip = node("span", "step-grip");
    grip.title = "Sürükleyerek taşıyın";
    grip.append(icon("grip"));
    main.append(
      grip,
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
      const labels = spec.branches || (container === "condition"
        ? { children: "KOŞUL DOĞRUYSA", otherwise: "DEĞİLSE" } : { children: "İÇ ADIMLAR" });
      const branches = Object.keys(labels);
      if (step.otherwise?.length && !branches.includes("otherwise")) branches.push("otherwise");
      branches.forEach((branch) => {
        step[branch] ||= [];
        const children = step[branch];
        const group = node(
          "div",
          `branch${children.length ? "" : " empty-branch"}${container === "try" && branch === "otherwise" ? " branch-error" : ""}`,
        );
        const label = labels[branch] || "DEĞİLSE";
        const head = node("div", "branch-heading");
        head.append(
          node("span", "", label),
          linkButton("Adım ekle", () => setTarget(step, branch), "plus"),
        );
        group.append(head);
        dropZone(head, () => ({ list: children, index: 0, ownerId: step.id, mark: "inside", target: group }));
        if (!children.length) {
          const placeholder = node(
            "button",
            "branch-placeholder",
            (container === "loop" ? "Her turda yapılacak işlemi ekle"
              : container === "try" && branch === "otherwise" ? "Hata olursa yapılacak işlemi ekle"
                : container === "try" ? "Denenecek adımları ekle" : "Bu dala adım ekle") + " · veya buraya sürükleyin",
          );
          placeholder.addEventListener("click", () => setTarget(step, branch));
          dropZone(placeholder, () => ({ list: children, index: 0, ownerId: step.id, mark: "inside", target: group }));
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

  // ----- screen tools: pointer, region and screen image ---------------------
  function stepExists(step) {
    return findStep(step.id)?.step === step;
  }
  function stepTools(step, spec) {
    const tools = node("div", "step-extra-tools");
    (spec.pointer || []).forEach(([xName, yName], index, all) => {
      const label = all.length > 1 ? (index === 0 ? "Başlangıç konumunu al" : "Bitiş konumunu al") : "Fare konumunu al";
      tools.append(button(`${label} (3 sn)`, "target", () => capturePointer(step, xName, yName), "small"));
    });
    if (spec.region) tools.append(button("Bölgeyi fareyle al (2 × 3 sn)", "target", () => captureRegion(step), "small"));
    if (spec.template) tools.append(button("Ekrandan görsel seç", "eye", () => pickScreenTemplate(step), "small"));
    if (!tools.children.length) return null;
    tools.append(node("p", "help", "Düğmeye bastıktan sonra 3 saniye içinde fareyi hedefin üzerine götürün; tıklamanız gerekmez. Masaüstü uygulamasında Studio bu sırada gizlenir; tarayıcıda hedef pencereye geçin."));
    return tools;
  }
  function readPointer(message) {
    toast(message);
    return api("/api/desktop/pointer", { method: "POST", body: JSON.stringify({ delay: 3 }) });
  }
  function capturePointer(step, xName, yName) {
    return attempt(async () => {
      const point = await readPointer("3 saniye içinde fareyi hedef noktaya götürün.");
      if (!stepExists(step)) return;
      applyStepParams(step, { [xName]: point.x, [yName]: point.y });
      toast(`Konum alındı: X ${point.x}, Y ${point.y}`);
    });
  }
  function captureRegion(step) {
    return attempt(async () => {
      const first = await readPointer("3 saniye içinde fareyi bölgenin SOL ÜST köşesine götürün.");
      const second = await readPointer("Şimdi 3 saniye içinde SAĞ ALT köşeye götürün.");
      let x = Math.min(first.x, second.x);
      let y = Math.min(first.y, second.y);
      const width = Math.abs(second.x - first.x);
      const height = Math.abs(second.y - first.y);
      if (width < 5 || height < 5) throw new Error("Bölge çok küçük; iki farklı köşe seçin.");
      if (parameterValue(step, "relative_to") === "window") {
        const recognized = recognizedWindowFor(step);
        if (!recognized) throw new Error("Pencereye göre bölge için bu adımdan önce Pencereyi tanı ekleyin.");
        const found = await api("/api/desktop/windows/check", {
          method: "POST",
          body: JSON.stringify({
            application: parameterValue(recognized, "application") || "",
            title: parameterValue(recognized, "title") || "",
            match: parameterValue(recognized, "match") || "exact",
          }),
        });
        if (!found.found) throw new Error("Tanıtılan pencere şu anda açık değil.");
        x -= found.x;
        y -= found.y;
      }
      if (!stepExists(step)) return;
      applyStepParams(step, { region: [x, y, width, height] });
      toast(`Bölge alındı: ${width} × ${height}`);
    });
  }
  function pickScreenTemplate(step) {
    const clickable = step.action === "screen.click_image";
    dialog("Ekrandan görsel seç", (body, d) => {
      d.classList.add("target-picker-dialog");
      let capture = null, image = null, rect = null, point = null, drag = null, saved = false;
      const delay = node("select");
      for (const seconds of [3, 5, 10]) {
        const option = node("option", "", `${seconds} saniye`);
        option.value = seconds;
        delay.append(option);
      }
      const start = button("Geri sayımı başlat ve ekranı yakala", "clock", grab, "primary");
      const status = node("div", "target-picker-status");
      status.setAttribute("role", "status");
      const frame = node("div", "target-picker-frame");
      const canvas = node("canvas", "target-picker-canvas");
      canvas.hidden = true;
      frame.append(canvas);
      const info = node("p", "help", clickable
        ? "Tıklanacak ikon veya düğmeyi çevreleyen küçük bir dikdörtgen sürükleyin. İsterseniz ardından tıklanacak noktaya tıklayın; boşsa görselin ortasına tıklanır."
        : "Aranacak işareti çevreleyen küçük bir dikdörtgen sürükleyin. Değişen yazıları (tarih, sayı) dahil etmeyin.");
      const reset = button("Seçimi temizle", "cross", () => { rect = point = null; draw(); }, "small");
      const save = button("Görseli kaydet", "check", commit, "primary");
      const actions = node("div", "target-picker-actions");
      actions.append(reset, save);
      body.append(
        node("p", "pane-caption", "Süre dolunca ana ekranın görüntüsü alınır. Masaüstü uygulamasında Studio bu sırada gizlenir; tarayıcıda hedef uygulamaya geçin."),
        field("Hazırlık süresi", delay), start, status, frame, info, actions,
      );
      d.addEventListener("close", () => {
        if (capture && !saved) api(`/api/desktop/captures/${encodeURIComponent(capture.id)}`, { method: "DELETE" }).catch(() => {});
      });
      function position(event) {
        const bounds = canvas.getBoundingClientRect();
        return {
          x: Math.max(0, Math.min(canvas.width - 1, Math.round((event.clientX - bounds.left) * canvas.width / bounds.width))),
          y: Math.max(0, Math.min(canvas.height - 1, Math.round((event.clientY - bounds.top) * canvas.height / bounds.height))),
        };
      }
      function draw() {
        save.disabled = !capture || !rect;
        reset.disabled = !rect && !point;
        if (!capture || !image) return;
        const context = canvas.getContext("2d");
        context.drawImage(image, 0, 0);
        context.lineWidth = Math.max(2, canvas.width / 600);
        if (rect) {
          context.strokeStyle = "#137c6b";
          context.fillStyle = "#137c6b26";
          context.fillRect(rect.x, rect.y, rect.width, rect.height);
          context.strokeRect(rect.x, rect.y, rect.width, rect.height);
        }
        if (point) {
          const radius = Math.max(7, canvas.width / 100);
          context.strokeStyle = "#d16a17";
          context.beginPath();
          context.arc(point.x, point.y, radius, 0, Math.PI * 2);
          context.stroke();
        }
      }
      canvas.addEventListener("pointerdown", (event) => {
        if (!capture || event.button !== 0) return;
        event.preventDefault();
        const at = position(event);
        if (!rect) {
          drag = at;
          canvas.setPointerCapture(event.pointerId);
        } else if (clickable) {
          point = at;
          draw();
        }
      });
      canvas.addEventListener("pointermove", (event) => {
        if (!drag) return;
        const at = position(event);
        rect = { x: Math.min(drag.x, at.x), y: Math.min(drag.y, at.y), width: Math.abs(drag.x - at.x), height: Math.abs(drag.y - at.y) };
        draw();
      });
      canvas.addEventListener("pointerup", () => {
        if (!drag) return;
        drag = null;
        if (!rect || rect.width < 8 || rect.height < 8) {
          rect = null;
          status.replaceChildren(note("En az 8 × 8 piksel bir alan seçin."));
        } else status.replaceChildren();
        draw();
      });
      async function grab() {
        start.disabled = true;
        status.replaceChildren(node("p", "help", `${delay.value} saniye içinde hedef ekranı hazırlayın…`));
        try {
          if (capture && !saved) api(`/api/desktop/captures/${encodeURIComponent(capture.id)}`, { method: "DELETE" }).catch(() => {});
          capture = await api("/api/desktop/capture-screen", { method: "POST", body: JSON.stringify({ delay: Number(delay.value) }) });
          const loaded = new Image();
          await new Promise((resolve, reject) => {
            loaded.onload = resolve;
            loaded.onerror = () => reject(new Error("Ekran görüntüsü açılamadı."));
            loaded.src = capture.image;
          });
          image = loaded;
          canvas.width = capture.width;
          canvas.height = capture.height;
          canvas.hidden = false;
          rect = point = null;
          status.replaceChildren(note("Şimdi görüntü üzerinde görseli seçin.", "info", "check"));
          draw();
        } catch (error) {
          status.replaceChildren(note(error.message));
        } finally {
          start.disabled = false;
        }
      }
      async function commit() {
        if (!capture || !rect || !stepExists(step)) return;
        save.disabled = true;
        try {
          const stored = await api("/api/desktop/templates", {
            method: "POST", body: JSON.stringify({ capture_id: capture.id, ...rect }),
          });
          saved = true;
          const values = { template: stored.template };
          if (clickable) {
            const centerX = rect.x + Math.floor(rect.width / 2);
            const centerY = rect.y + Math.floor(rect.height / 2);
            Object.assign(values, point ? { offset_x: point.x - centerX, offset_y: point.y - centerY }
              : { offset_x: 0, offset_y: 0 });
          }
          d.close();
          applyStepParams(step, values);
          toast("Referans görsel kaydedildi.");
        } catch (error) {
          status.replaceChildren(note(error.message));
          save.disabled = false;
        }
      }
      draw();
    });
  }
  // ----- macro recorder ---------------------------------------------------------
  function recordMovements() {
    const workflow = state.workflow;
    if (!workflow) return;
    dialog("Hareketleri kaydet", (body, d) => {
      d.classList.add("record-dialog");
      let job = null, timer = null, finished = false;
      const delay = node("select");
      for (const seconds of [3, 5, 10]) {
        const option = node("option", "", `${seconds} saniye`);
        option.value = seconds;
        delay.append(option);
      }
      const option = (text, checked) => {
        const label = node("label", "checkbox-label");
        const input = node("input");
        input.type = "checkbox";
        input.checked = checked;
        label.append(input, node("span", "", text));
        return { label, input };
      };
      const waits = option("Hareketler arasındaki beklemeleri kaydet (1,5 sn üzeri)", true);
      const relative = option("Tıklamaları pencereye göre kaydet (pencere taşınsa da doğru yere tıklar)", true);
      const status = node("div", "record-status");
      status.setAttribute("aria-live", "polite");
      const preview = node("div", "record-preview");
      const start = button("Kaydı başlat", "record", begin, "primary");
      const stop = button("Kaydı bitir", "stop", finish, "danger");
      const add = button("Akışa ekle", "plus", insert, "primary");
      stop.hidden = add.hidden = true;
      const controls = node("div", "target-picker-actions");
      controls.append(start, stop, add);
      body.append(
        node("p", "pane-caption", "Geri sayım bitince yaptığınız tıklamalar, yazdığınız metinler, kısayollar, sürüklemeler ve kaydırmalar kaydedilir. Kaydı F9 tuşuyla veya ekranın sağ altındaki Kaydı bitir düğmesiyle bitirin. Masaüstü uygulamasında Studio kayıt sırasında gizlenir."),
        note("Şifre gibi gizli bilgileri kayıt sırasında yazmayın; yazdığınız her şey akışa adım olarak eklenir.", "warning"),
        field("Hazırlık süresi", delay), waits.label, relative.label, controls, status, preview,
      );
      d.addEventListener("close", () => {
        clearTimeout(timer);
        if (job && !finished) api(`/api/desktop/record/${encodeURIComponent(job)}`, { method: "DELETE" }).catch(() => {});
      });
      async function begin() {
        start.disabled = true;
        preview.replaceChildren();
        add.hidden = true;
        try {
          const started = await api("/api/desktop/record", {
            method: "POST",
            body: JSON.stringify({ delay: Number(delay.value), record_waits: waits.input.checked,
              relative_windows: relative.input.checked }),
          });
          job = started.id;
          finished = false;
          stop.hidden = false;
          poll();
        } catch (error) {
          status.replaceChildren(note(error.message));
          start.disabled = false;
        }
      }
      async function finish() {
        if (job) await api(`/api/desktop/record/${encodeURIComponent(job)}/stop`, { method: "POST" }).catch(() => {});
      }
      async function poll() {
        let current;
        try {
          current = await api(`/api/desktop/record/${encodeURIComponent(job)}`);
        } catch (error) {
          status.replaceChildren(note(error.message));
          start.disabled = false;
          stop.hidden = true;
          return;
        }
        if (!d.isConnected) return;
        const text = current.status === "recording"
          ? `Kaydediliyor · ${current.events} hareket · F9 ile bitirin`
          : current.message;
        status.replaceChildren(node("p", current.status === "recording" ? "record-live" : "help", text));
        if (["starting", "countdown", "recording"].includes(current.status)) {
          timer = setTimeout(poll, 400);
          return;
        }
        finished = true;
        stop.hidden = true;
        start.disabled = false;
        start.querySelector("span").textContent = "Yeniden kaydet";
        if (current.status === "completed") showSteps(current.result?.steps || []);
        else status.replaceChildren(note(current.message, current.status === "cancelled" ? "" : "error"));
      }
      function showSteps(steps) {
        preview.replaceChildren();
        if (!steps.length) {
          preview.append(note("Kayıtta adım oluşmadı. Geri sayım bittikten sonra hedef uygulamada işlem yapın."));
          return;
        }
        preview.append(node("h3", "", `${steps.length} adım oluşturuldu`),
          node("p", "help", "Eklemek istemediğiniz adımların işaretini kaldırın. Ekledikten sonra her adımı sağ panelden düzenleyebilir veya test edebilirsiniz."));
        const list = node("ol", "record-steps");
        steps.forEach((step) => {
          const item = node("li");
          const label = node("label", "checkbox-label");
          const input = node("input");
          input.type = "checkbox";
          input.checked = true;
          input.dataset.stepId = step.id;
          label.append(input, icon(actionIcon(step.action)), node("span", "", step.title));
          item.append(label);
          list.append(item);
        });
        preview.append(list);
        preview.recorded = steps;
        add.hidden = false;
      }
      function insert() {
        if (state.workflow !== workflow) return d.close();
        const chosen = new Set([...preview.querySelectorAll("input[data-step-id]:checked")].map((el) => el.dataset.stepId));
        const steps = (preview.recorded || []).filter((step) => chosen.has(step.id)).map((step) => ({
          ...clone(step), id: uid(), children: [], otherwise: [],
        }));
        if (!steps.length) return toast("Eklenecek adım seçilmedi.", true);
        let list = state.workflow.steps;
        if (state.target) {
          const parent = findStep(state.target.id);
          if (parent) list = parent.step[state.target.branch] ||= [];
        }
        list.push(...steps);
        d.close();
        state.selected = steps[0].id;
        markDirty();
        renderCanvas();
        renderInspector();
        toast(`${steps.length} adım akışa eklendi. Kaydedip çalıştırmadan önce adımları kontrol edin.`);
      }
    });
  }
  // ----- single step test -----------------------------------------------------
  const EXPRESSION_WORDS = new Set(["and", "or", "not", "if", "else", "in", "is", "true", "false", "none",
    "round", "abs", "min", "max", "int", "float", "number", "str", "len", "sum", "floor", "ceil", "doğru", "yanlış"]);
  function referencedVariables(step) {
    const produced = new Set(["sistem"]);
    if (allSteps([step]).some((item) => ["control.for_each", "control.while", "control.repeat"].includes(item.action)))
      produced.add("loop_index");
    const found = new Set();
    allSteps([step]).forEach((item) => {
      ["output", "item_name", "error_name"].forEach((key) => {
        const value = parameterValue(item, key);
        if (typeof value === "string" && value) produced.add(value);
      });
    });
    const scan = (value) => {
      if (typeof value === "string") {
        for (const match of value.matchAll(/\$\{([A-Za-z][A-Za-z0-9_]*)/g)) found.add(match[1]);
      } else if (Array.isArray(value)) value.forEach(scan);
      else if (value && typeof value === "object") Object.values(value).forEach(scan);
    };
    allSteps([step]).forEach((item) => {
      scan(item.params || {});
      if (item.action === "data.calculate") {
        const expression = String(parameterValue(item, "expression") || "").replace(/\$\{[^}]*\}/g, " ")
          .replace(/'[^']*'|"[^"]*"/g, " ");
        for (const match of expression.matchAll(/(?<![\w.])([A-Za-zçğıöşüÇĞİÖŞÜ_][\wçğıöşüÇĞİÖŞÜ]*)/g))
          if (!EXPRESSION_WORDS.has(match[1].toLowerCase())) found.add(match[1]);
      }
    });
    return [...found].filter((name) => !produced.has(name));
  }
  function parseTestValue(raw) {
    const text = raw.trim();
    if (!text) return "";
    if (/^[\[{"]/.test(text) || /^(true|false|null|-?\d+(\.\d+)?)$/.test(text)) {
      try {
        return JSON.parse(text);
      } catch {
        return raw;
      }
    }
    return raw;
  }
  async function openStepTest(step) {
    if (!(await requireSaved())) return;
    if (!stepExists(step)) return;
    const workflowId = state.workflow.id;
    const spec = specFor(step.action);
    const external = allSteps([step]).some((item) =>
      /^(desktop|input|window|screen|system|clipboard|file|ui|http|sheets|database|browser)\./.test(item.action));
    const needed = referencedVariables(step);
    dialog(`Adımı test et: ${step.title || spec.label}`, (body, d) => {
      d.classList.add("step-test-dialog");
      const inputs = new Map();
      body.append(note(external
        ? "Bu test gerçek işlem yapar: fare, klavye, ekran, dosya veya bağlantı adımları uygulanır. Hedef uygulamayı hazırlayın."
        : "Bu adım yalnız veri işler; ekrana ve dosyalara dokunmaz.", external ? "warning" : "info"));
      if (needed.length) {
        body.append(node("h3", "", "Test değerleri"),
          node("p", "help", "Adımın kullandığı değişkenler için örnek değer girin. Metin yazabilir veya JSON kullanabilirsiniz: {\"form_id\": \"INV-1\"}, [1, 2], 42."));
        needed.forEach((name) => {
          const input = node("textarea", "mono");
          input.rows = 2;
          input.value = state.testValues[name] ?? "";
          inputs.set(name, input);
          body.append(field("${" + name + "}", input));
        });
      }
      const previewLabel = node("label", "checkbox-label");
      const preview = node("input");
      preview.type = "checkbox";
      previewLabel.append(preview, node("span", "", "Önizleme olarak çalıştır (ekrana dokunmadan)"));
      const result = node("div", "step-test-result");
      result.setAttribute("aria-live", "polite");
      const runButton = button("Testi çalıştır", "play", run, "primary");
      const cancelButton = button("Durdur", "stop", async () => {
        if (current) await api(`/api/runs/${encodeURIComponent(current)}/cancel`, { method: "POST" }).catch(() => {});
      }, "small");
      cancelButton.hidden = true;
      const controls = node("div", "target-picker-actions");
      controls.append(runButton, cancelButton);
      body.append(previewLabel, controls, result);
      let current = null, timer = null;
      d.addEventListener("close", () => clearTimeout(timer));
      async function run() {
        runButton.disabled = true;
        const variables = {};
        inputs.forEach((input, name) => {
          state.testValues[name] = input.value;
          variables[name] = parseTestValue(input.value);
        });
        result.replaceChildren(node("p", "help", "Test başlatılıyor…"));
        try {
          const started = await api(`/api/workflows/${encodeURIComponent(workflowId)}/steps/${encodeURIComponent(step.id)}/test`, {
            method: "POST", body: JSON.stringify({ variables, dry_run: preview.checked }),
          });
          current = started.id;
          cancelButton.hidden = false;
          poll();
        } catch (error) {
          result.replaceChildren(note(error.message));
          runButton.disabled = false;
        }
      }
      async function poll() {
        try {
          const test = await api(`/api/runs/${encodeURIComponent(current)}`);
          show(test);
          if (["queued", "running"].includes(test.status) && d.isConnected) {
            timer = setTimeout(poll, 400);
            return;
          }
          upsert(state.runs, test);
        } catch (error) {
          result.replaceChildren(note(error.message));
        }
        runButton.disabled = false;
        cancelButton.hidden = true;
        runButton.querySelector("span").textContent = "Tekrar test et";
      }
      function show(test) {
        result.replaceChildren();
        const head = node("div", "step-test-head");
        head.append(badge(test.status), node("span", "muted", duration(test)));
        result.append(head);
        if (test.error) result.append(note(test.error, "error"));
        const log = node("ol", "step-test-log mono");
        (test.events || []).slice(-40).forEach((event) => {
          const line = node("li", `level-${event.level}`, event.message);
          log.append(line);
        });
        result.append(log);
        const values = test.variables || {};
        const shown = Object.keys(values).filter((name) => !inputs.has(name));
        if (shown.length) {
          result.append(node("h3", "", "Adımın ürettiği değerler"));
          const list = node("dl", "step-test-values");
          shown.forEach((name) => {
            const value = values[name];
            list.append(node("dt", "mono", "${" + name + "}"),
              node("dd", "mono", typeof value === "string" ? value : JSON.stringify(value, null, 2)));
          });
          result.append(list);
        }
      }
    });
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
  function parameterValue(step, name) {
    // Older loops omitted this parameter and execute with the engine's "item"
    // binding. Newly added loops already have an explicit "row" catalog default.
    if (step.action === "control.for_each" && name === "item_name" &&
        !Object.hasOwn(step.params || {}, name)) return "item";
    return Object.hasOwn(step.params || {}, name)
      ? step.params[name]
      : specFor(step.action).fields?.find((field) => field.name === name)?.default;
  }
  function fieldVisible(step, definition) {
    if (["control.if", "control.while"].includes(step.action) && definition.name === "right" &&
        ["empty", "not_empty", "truthy"].includes(parameterValue(step, "operator"))) return false;
    return Object.entries(definition.visible_when || {}).every(([name, expected]) =>
      Array.isArray(expected) ? expected.includes(parameterValue(step, name)) : parameterValue(step, name) === expected,
    );
  }
  function enclosingSteps(id, steps = state.workflow?.steps || [], parents = []) {
    for (const step of steps) {
      if (step.id === id) return [...parents, step];
      const found = enclosingSteps(id, step.children || [], [...parents, step]) ||
        enclosingSteps(id, step.otherwise || [], [...parents, step]);
      if (found) return found;
    }
    return null;
  }
  function precedingSteps(id, steps = state.workflow?.steps || [], inherited = []) {
    const previous = [...inherited];
    for (const step of steps) {
      if (step.id === id) return previous;
      const nested = precedingSteps(id, step.children || [], previous) ||
        precedingSteps(id, step.otherwise || [], previous);
      if (nested) return nested;
      previous.push(step);
    }
    return null;
  }
  function recognizedWindowFor(step) {
    const reference = String(parameterValue(step, "window") || "").match(/^\$\{([^}.]+)\}$/);
    if (!reference) return null;
    return (precedingSteps(step.id) || []).reverse().find(
      (candidate) => candidate.action === "desktop.find_window" &&
        parameterValue(candidate, "output") === reference[1],
    ) || null;
  }
  function applyStepParams(step, values) {
    Object.assign(step.params, values);
    for (const name of Object.keys(values)) {
      state.fieldErrors.delete(`${step.id}:${name}`);
      state.drafts.delete(`${step.id}:${name}`);
    }
    markDirty();
    renderInspector();
    renderCanvas();
  }
  function windowTargetTools(step) {
    const tools = node("div", "window-target-tools");
    const recognized = recognizedWindowFor(step);
    const busy = state.runs.some((run) => ["queued", "running"].includes(run.status));
    const target = button("Ekranda seç", "desktop", () => pickWindowTarget(step, "native"));
    const snapshot = button("Görüntü üzerinde seç", "eye", () => pickWindowTarget(step, "snapshot"), "small");
    target.disabled = true;
    snapshot.disabled = !recognized || busy;
    const availability = node("p", "help");
    tools.append(target, snapshot);
    if (recognized) {
      tools.append(node("p", "help", `Pencere: ${recognized.params?.title || recognized.title}. Ekranda seç ile geri sayımdan sonra fare konumunu alın veya görsel alanını sürükleyerek seçin. Uygulama alan kimliği veriyorsa alan, ekran boyutundan bağımsız olarak kimliğiyle bulunur.`));
    } else {
      tools.append(node("p", "help", "Önce bu adımın önüne Pencereyi tanıt ekleyin. Pencere alanında onun çıktısını kullanın; örneğin ${erp_window}."));
    }
    tools.append(availability);
    if (busy) availability.textContent = "Hedef seçmeden önce çalışan akışın bitmesini bekleyin veya akışı durdurun.";
    else if (recognized) {
      availability.textContent = "Ekrandan seçim desteği kontrol ediliyor…";
      api("/api/desktop/pick/capabilities").then((capabilities) => {
        if (!tools.isConnected) return;
        target.disabled = !capabilities.native;
        availability.textContent = capabilities.native ? "" : "Ekranda seçim bu oturumda kullanılamıyor. Masaüstü uygulamasını açın veya Görüntü üzerinde seç yöntemini kullanın.";
      }).catch(() => {
        if (tools.isConnected) availability.textContent = "Ekranda seçim desteği doğrulanamadı. Görüntü üzerinde seç yöntemini kullanabilirsiniz.";
      });
    }
    return tools;
  }
  function pickWindowTarget(step, source = "native") {
    const workflow = state.workflow;
    const recognized = recognizedWindowFor(step);
    if (!recognized) {
      toast("Önceki Pencereyi tanıt adımını ve pencere değişkenini kontrol edin.", true);
      return;
    }
    const selector = {
      application: parameterValue(recognized, "application") || "",
      title: parameterValue(recognized, "title") || "",
      match: parameterValue(recognized, "match") || "exact",
    };
    if (!selector.title.trim() || /\$\{/.test(selector.title + selector.application)) {
      toast("Görüntü almak için Pencereyi tanıt adımında açık ERP penceresini seçin.", true);
      return;
    }
    const referenceOnly = step.action === "desktop.window_wait_image";
    dialog("ERP ekranında hedef seç", (body, d) => {
      d.classList.add("target-picker-dialog");
      // A saved field identity is re-picked through the pointer (Konum) selection.
      let mode = referenceOnly ? "image" : parameterValue(step, "target_mode") === "image" ? "image" : "coordinates";
      let capture = null, rectangle = null, point = null, drag = null, image = null;
      let element = null, useElement = false;
      let loading = false, saving = false, epoch = 0;
      let session = null, polling = null, nativeBusy = false, nativeStatus = null;
      const discard = (id) => {
        if (id) api(`/api/desktop/captures/${encodeURIComponent(id)}`, { method: "DELETE", keepalive: true }).catch(() => {});
      };
      const current = () => d.isConnected && state.workflow === workflow && findStep(step.id)?.step === step;
      const intro = node("p", "pane-caption", source === "native"
        ? "Önce süreyi seçip geri sayımı başlatın. ERP penceresi öne gelir; seçiminiz bitince burada kontrol edip kaydedebilirsiniz. Seçim sırasında ERP’ye tıklama veya metin gönderilmez."
        : "ERP penceresinin görüntüsü alınır. Konum için görüntüye tıklayın; görsel referans için fareyle bir dikdörtgen çizin. Studio arka planda kalırsa Alt+Tab (Mac: ⌘+Tab) ile geri dönün.");
      intro.append(" Bu sürümde ERP penceresini ana ekranda, tamamı görünür olacak şekilde tutun.");
      const toolbar = node("div", "target-picker-toolbar");
      const modeLabel = node("span", "field-label", "Hedef yöntemi");
      const coordinates = button("Konum", "desktop", () => changeMode("coordinates"), "small");
      const visual = button("Görsel referans", "eye", () => changeMode("image"), "small");
      if (!referenceOnly) toolbar.append(modeLabel, coordinates, visual);
      const preparation = node("div", "target-picker-preparation");
      const delay = node("select");
      for (const seconds of [3, 5, 10]) {
        const option = node("option", "", `${seconds} saniye`);
        option.value = seconds;
        delay.append(option);
      }
      delay.value = "5";
      const begin = button("Tamam, geri sayımı başlat", "clock", startNative, "primary");
      const cancelPick = button("Seçimi iptal et", "cross", cancelNative, "small");
      const preparationHelp = node("p", "help");
      preparation.append(field("Hazırlık süresi", delay), begin, cancelPick, preparationHelp);
      preparation.hidden = source !== "native";
      const instruction = node("p", "target-picker-instruction");
      instruction.setAttribute("aria-live", "polite");
      const status = node("div", "target-picker-status");
      status.setAttribute("role", "status");
      const structure = node("div", "target-picker-structure");
      const frame = node("div", "target-picker-frame");
      const canvas = node("canvas", "target-picker-canvas");
      canvas.setAttribute("aria-label", "ERP pencere görüntüsü. Konum için tıklayın; görsel referans için dikdörtgen çizin.");
      canvas.setAttribute("role", "img");
      canvas.hidden = true;
      frame.append(canvas);
      const selection = node("p", "target-picker-selection mono");
      const actions = node("div", "target-picker-actions");
      const refresh = button("Görüntüyü yenile", "refresh", load, "small");
      const repick = button("Yeniden ekranda seç", "desktop", () => {
        clearCapture();
        status.replaceChildren();
        draw();
        begin.focus();
      }, "small");
      const reset = button("Seçimi temizle", "cross", () => {
        rectangle = point = drag = null;
        draw();
      }, "small");
      const save = button("Hedefi kaydet", "check", commit, "primary");
      actions.append(source === "native" ? repick : refresh, reset, save);
      body.append(intro, toolbar, preparation, instruction, status, structure, frame, selection, actions);
      const unload = () => {
        epoch += 1;
        clearTimeout(polling);
        discardSession(session);
        discard(capture?.id);
      };
      window.addEventListener("pagehide", unload);
      d.addEventListener("close", () => {
        window.removeEventListener("pagehide", unload);
        epoch += 1;
        clearTimeout(polling);
        discardSession(session);
        session = null;
        discard(capture?.id);
        if (image) image.src = "";
        image = capture = null;
        canvas.width = canvas.height = 1;
      });
      function changeMode(next) {
        if (loading || saving || nativeBusy) return;
        mode = next;
        rectangle = point = drag = null;
        if (source === "native") clearCapture();
        draw();
      }
      function viewState() {
        const busy = loading || saving || nativeBusy;
        coordinates.setAttribute("aria-pressed", String(mode === "coordinates"));
        visual.setAttribute("aria-pressed", String(mode === "image"));
        coordinates.disabled = visual.disabled = busy;
        refresh.disabled = repick.disabled = busy;
        repick.hidden = !capture;
        delay.disabled = busy;
        begin.disabled = busy;
        begin.hidden = Boolean(capture) || nativeBusy;
        cancelPick.hidden = !nativeBusy;
        preparation.hidden = source !== "native" || Boolean(capture);
        frame.hidden = !capture;
        selection.hidden = !capture;
        actions.hidden = !capture;
        reset.disabled = busy || (!point && !rectangle);
        save.disabled = busy || !capture ||
          (mode === "coordinates" ? !point : !rectangle || (!referenceOnly && !point));
        preparationHelp.textContent = mode === "coordinates"
          ? "Süre dolmadan fareyi ERP’deki hedef alanın üzerine getirin ve orada tutun. Süre bittiğindeki konum alınır; tıklamanız gerekmez. Uygulama alana bir kimlik veriyorsa ekran boyutundan bağımsız alan kimliği de önerilir. Esc ile iptal edebilirsiniz."
          : `Süre bitince ERP görüntüsünde sabit bir etiketi (ör. FormID) fareyle sürükleyerek seçin.${referenceOnly ? "" : " Ardından işlem yapılacak alanın ortasına tıklayın."} Seçimi kullan ile önizlemeye dönün. Esc ile iptal edebilirsiniz.`;
        if (nativeBusy) {
          const countdown = nativeStatus?.countdown;
          instruction.textContent = nativeStatus?.status === "countdown"
            ? `Hazırlanın${Number.isFinite(countdown) ? ` · ${Math.max(0, Math.ceil(countdown))} saniye` : ""}. ${mode === "coordinates" ? "Fareyi hedef alanın üzerinde tutun." : "Görsel alanını seçmek için bekleyin."}`
            : nativeStatus?.message || "Ekranda seçim hazırlanıyor…";
        } else if (loading) instruction.textContent = "ERP penceresinin görüntüsü alınıyor…";
        else if (source === "native" && !capture) instruction.textContent = "Hedef yöntemini ve hazırlık süresini seçin. Hazır olduğunuzda geri sayımı başlatın.";
        else if (mode === "coordinates") instruction.textContent = "Yazılacak veya tıklanacak alanın ortasına tıklayın.";
        else if (!rectangle) instruction.textContent = "Sabit ve ayırt edici bir etiketi (ör. Form ID) çevreleyen dikdörtgen çizin. Değişen alan değerlerini referansa dahil etmeyin.";
        else if (!referenceOnly && !point) instruction.textContent = "Şimdi işlem yapılacak alanın ortasına tıklayın. Alan, seçtiğiniz referansın dışında olabilir.";
        else instruction.textContent = referenceOnly ? "Beklenecek görsel referans hazır. Kaydedebilirsiniz." : "Görsel referans ve işlem yapılacak alan hazır. Kaydedebilirsiniz.";
      }
      function discardSession(id) {
        if (id) api(`/api/desktop/pick/${encodeURIComponent(id)}`, { method: "DELETE", keepalive: true }).catch(() => {});
      }
      function paintStructure() {
        structure.replaceChildren();
        if (referenceOnly || mode !== "coordinates" || !capture || !element) return;
        if (!element.available) {
          structure.append(note(element.reason || "Uygulama yapısından alan okunamadı; konum kaydedilecek."));
          return;
        }
        const choice = (value, title, help) => {
          const label = node("label", "structure-choice");
          const input = node("input");
          input.type = "radio";
          input.name = `structure-${step.id}`;
          input.checked = useElement === value;
          input.addEventListener("change", () => { useElement = value; });
          const text = node("span");
          text.append(node("strong", "", title), node("small", "", help));
          label.append(input, text);
          return label;
        };
        structure.append(
          node("p", "structure-found", `Uygulama yapısında alan bulundu: ${element.summary}`),
          choice(true, "Alan kimliğiyle bul (önerilen)", "Pencere boyutu, konumu veya ekran ölçeği değişse de alan uygulamanın verdiği kimlikle bulunur."),
          choice(false, "Konumla bul (X / Y)", "Pencere düzeni değişmediği sürece aynı noktaya tıklanır."),
        );
        if (!element.unique)
          structure.append(note("Aynı kimlikte birden fazla alan var; seçtiğiniz sıradaki alan kaydedilir.", "warning"));
      }
      function clearCapture() {
        discard(capture?.id);
        if (image) image.src = "";
        element = null;
        useElement = false;
        structure.replaceChildren();
        image = capture = rectangle = point = drag = null;
        canvas.hidden = true;
        canvas.width = canvas.height = 1;
      }
      function cancelNative() {
        epoch += 1;
        clearTimeout(polling);
        discardSession(session);
        session = null;
        clearCapture();
        nativeBusy = loading = false;
        nativeStatus = null;
        status.replaceChildren(note("Seçim iptal edildi. Adımın kayıtlı hedefi değiştirilmedi."));
        draw();
      }
      function draw() {
        viewState();
        selection.textContent = "";
        if (!capture || !image?.complete || !image.naturalWidth) return;
        const context = canvas.getContext("2d");
        context.clearRect(0, 0, canvas.width, canvas.height);
        context.drawImage(image, 0, 0, canvas.width, canvas.height);
        const thickness = Math.max(2, canvas.width / 600);
        context.lineWidth = thickness;
        if (rectangle) {
          context.strokeStyle = "#137c6b";
          context.fillStyle = "#137c6b26";
          context.fillRect(rectangle.x, rectangle.y, rectangle.width, rectangle.height);
          context.strokeRect(rectangle.x, rectangle.y, rectangle.width, rectangle.height);
          selection.textContent = `Referans: ${rectangle.width} × ${rectangle.height}`;
        }
        if (point) {
          const radius = Math.max(7, canvas.width / 100);
          context.strokeStyle = "#d16a17";
          context.beginPath();
          context.arc(point.x, point.y, radius, 0, Math.PI * 2);
          context.moveTo(point.x - radius * 1.5, point.y);
          context.lineTo(point.x + radius * 1.5, point.y);
          context.moveTo(point.x, point.y - radius * 1.5);
          context.lineTo(point.x, point.y + radius * 1.5);
          context.stroke();
          const logical = toWindow(point);
          selection.textContent += `${rectangle ? " · " : ""}Alan: X ${logical.x}, Y ${logical.y}`;
        }
      }
      function location(event) {
        const bounds = canvas.getBoundingClientRect();
        return {
          x: Math.max(0, Math.min(canvas.width - 1, Math.round((event.clientX - bounds.left) * canvas.width / bounds.width))),
          y: Math.max(0, Math.min(canvas.height - 1, Math.round((event.clientY - bounds.top) * canvas.height / bounds.height))),
        };
      }
      function toWindow(position) {
        return {
          x: Math.min(capture.window.width - 1, Math.round(position.x * capture.window.width / canvas.width)),
          y: Math.min(capture.window.height - 1, Math.round(position.y * capture.window.height / canvas.height)),
        };
      }
      function dragged(start, end) {
        return { x: Math.min(start.x, end.x), y: Math.min(start.y, end.y),
          width: Math.abs(start.x - end.x), height: Math.abs(start.y - end.y) };
      }
      canvas.addEventListener("pointerdown", (event) => {
        if (loading || saving || nativeBusy || !capture || event.button !== 0) return;
        event.preventDefault();
        const position = location(event);
        if (mode === "image" && !rectangle) {
          drag = position;
          canvas.setPointerCapture(event.pointerId);
        } else {
          point = position;
          if (element?.available && mode === "coordinates") {
            // A point moved by hand no longer matches the field read from the screen.
            element = { available: false, reason: "Konumu görüntü üzerinde değiştirdiniz; alan kimliği yerine bu konum kaydedilecek." };
            useElement = false;
            paintStructure();
          }
          draw();
        }
      });
      canvas.addEventListener("pointermove", (event) => {
        if (!drag) return;
        rectangle = dragged(drag, location(event));
        draw();
      });
      canvas.addEventListener("pointerup", (event) => {
        if (!drag) return;
        rectangle = dragged(drag, location(event));
        drag = null;
        if (rectangle.width < 8 || rectangle.height < 8) {
          rectangle = null;
          status.replaceChildren(note("En az 8 × 8 piksel bir referans alanı seçin."));
        } else status.replaceChildren();
        draw();
      });
      canvas.addEventListener("pointercancel", () => {
        if (drag) rectangle = drag = null;
        draw();
      });
      async function showCapture(found, request, selection = {}) {
        if (!current() || epoch !== request) {
          discard(found?.id);
          return;
        }
        if (typeof found?.id !== "string" || !/^data:image\/png;base64,/.test(found.image || "") ||
            !(found.width > 0 && found.height > 0 && found.window?.width > 0 && found.window?.height > 0)) {
          discard(found?.id);
          throw new Error("ERP pencere görüntüsü okunamadı. Yeniden deneyin.");
        }
        capture = found;
        const loadedImage = new Image();
        image = loadedImage;
        const loaded = new Promise((resolve, reject) => {
          loadedImage.onload = resolve;
          loadedImage.onerror = () => reject(new Error("Pencere görüntüsü açılamadı. Yeniden deneyin."));
        });
        loadedImage.src = found.image;
        await loaded;
        if (!current() || epoch !== request) return;
        if (loadedImage.naturalWidth !== found.width || loadedImage.naturalHeight !== found.height)
          throw new Error("Görüntü boyutu doğrulanamadı. Yeniden deneyin.");
        const within = (p) => p && Number.isInteger(p.x) && Number.isInteger(p.y) &&
          p.x >= 0 && p.y >= 0 && p.x < found.width && p.y < found.height;
        if (selection.point && !within(selection.point)) throw new Error("Seçilen konum pencerenin dışında. Yeniden seçin.");
        const rect = selection.rectangle;
        if (rect && (!within(rect) || !Number.isInteger(rect.width) || !Number.isInteger(rect.height) ||
            rect.width < 8 || rect.height < 8 || rect.x + rect.width > found.width || rect.y + rect.height > found.height))
          throw new Error("Görsel alanı doğrulanamadı. Yeniden seçin.");
        if (source === "native" && (mode === "coordinates" ? !selection.point : !rect || (!referenceOnly && !selection.point)))
          throw new Error("Hedef seçimi tamamlanmadı. Yeniden seçin.");
        rectangle = rect || null;
        point = selection.point || null;
        canvas.width = found.width;
        canvas.height = found.height;
        canvas.hidden = false;
      }
      async function startNative() {
        if (loading || saving || nativeBusy || !current()) return;
        clearTimeout(polling);
        discardSession(session);
        session = null;
        clearCapture();
        const request = ++epoch;
        nativeBusy = true;
        nativeStatus = { status: "starting" };
        status.replaceChildren();
        draw();
        const startedAt = Date.now();
        let failures = 0;
        const fail = (error) => {
          if (!current() || epoch !== request) return;
          clearCapture();
          discardSession(session);
          session = null;
          nativeBusy = false;
          nativeStatus = null;
          status.replaceChildren(note(error.message || "Ekranda seçim tamamlanamadı. Yeniden deneyin."));
          draw();
        };
        const accept = async (job) => {
          if (!current() || epoch !== request) {
            discardSession(job.id);
            discard(job.result?.capture?.id);
            return;
          }
          nativeStatus = job;
          if (job.status === "completed") {
            await showCapture(job.result?.capture, request, job.result || {});
            if (!current() || epoch !== request) return;
            element = mode === "coordinates" && job.result?.element && typeof job.result.element === "object"
              ? job.result.element : null;
            useElement = Boolean(element?.available && element.locator);
            paintStructure();
            nativeBusy = false;
            status.replaceChildren(note("Seçimi kontrol edin. Hedefi kaydet dediğinizde adıma aktarılır; gerekirse görüntü üzerinde düzeltebilirsiniz.", "info", "check"));
            draw();
          } else if (job.status === "cancelled") {
            nativeBusy = false;
            status.replaceChildren(note("Seçim iptal edildi. Adımın kayıtlı hedefi değiştirilmedi."));
            draw();
          } else if (job.status === "error") {
            nativeBusy = false;
            throw new Error(job.message || "Ekranda seçim tamamlanamadı. Yeniden deneyin.");
          } else if (["starting", "countdown", "selecting"].includes(job.status)) {
            draw();
            polling = setTimeout(poll, 400);
          } else throw new Error("Seçim durumu doğrulanamadı. Yeniden deneyin.");
        };
        const poll = async () => {
          if (!current() || epoch !== request || !session) return;
          if (Date.now() - startedAt > 180000) {
            fail(new Error("Seçim süresi doldu. Hazır olduğunuzda yeniden başlatın."));
            return;
          }
          try {
            const job = await api(`/api/desktop/pick/${encodeURIComponent(session)}`);
            failures = 0;
            await accept(job);
          } catch (error) {
            if (!current() || epoch !== request) return;
            if (++failures < 3 && nativeBusy) polling = setTimeout(poll, 700);
            else fail(error);
          }
        };
        try {
          const job = await api("/api/desktop/pick", {
            method: "POST", body: JSON.stringify({ ...selector,
              mode: referenceOnly ? "image_only" : mode, delay: Number(delay.value) }),
          });
          if (!current() || epoch !== request) {
            discardSession(job.id);
            discard(job.result?.capture?.id);
            return;
          }
          if (typeof job.id !== "string" || !job.id) throw new Error("Seçim başlatılamadı. Yeniden deneyin.");
          session = job.id;
          await accept(job);
        } catch (error) { fail(error); }
      }
      async function load() {
        if (loading || saving || nativeBusy) return;
        const request = ++epoch;
        loading = true;
        clearCapture();
        status.replaceChildren();
        draw();
        try {
          const found = await api("/api/desktop/capture-window", { method: "POST", body: JSON.stringify(selector) });
          await showCapture(found, request);
        } catch (error) {
          if (current() && epoch === request) {
            discard(capture?.id);
            capture = null;
            status.replaceChildren(note(error.message));
          }
        } finally {
          if (current() && epoch === request) {
            loading = false;
            draw();
          }
        }
      }
      async function commit() {
        if (save.disabled || !current()) return;
        saving = true;
        viewState();
        status.replaceChildren(node("p", "help", "Hedef kaydediliyor…"));
        try {
          let values;
          const byStructure = mode === "coordinates" && useElement && element?.available && element.locator;
          if (byStructure) values = { target_mode: "element", element: element.locator, ...toWindow(point) };
          else if (mode === "coordinates") values = { target_mode: mode, ...toWindow(point) };
          else {
            const saved = await api("/api/desktop/templates", {
              method: "POST", body: JSON.stringify({ capture_id: capture.id, ...rectangle }),
            });
            if (!current()) return;
            if (typeof saved.template !== "string" || !saved.template)
              throw new Error("Görsel referans kaydedilemedi.");
            values = { template: saved.template };
            if (!referenceOnly) {
              const center = toWindow({ x: rectangle.x + Math.floor(rectangle.width / 2), y: rectangle.y + Math.floor(rectangle.height / 2) });
              const position = toWindow(point);
              Object.assign(values, { target_mode: "image", offset_x: position.x - center.x, offset_y: position.y - center.y });
            }
          }
          d.close();
          applyStepParams(step, values);
          toast(byStructure ? `Alan kimliği kaydedildi: ${element.summary}`
            : mode === "image" ? "Görsel referans ve hedef kaydedildi." : "Pencere içindeki hedef konum kaydedildi.");
        } catch (error) {
          if (current()) status.replaceChildren(note(error.message));
        } finally {
          saving = false;
          if (current()) viewState();
        }
      }
      viewState();
      if (source === "snapshot") queueMicrotask(load);
    });
  }
  const elementRoles = {
    Edit: "Metin kutusu", AXTextField: "Metin kutusu", AXTextArea: "Metin alanı", Document: "Metin alanı",
    ComboBox: "Açılır liste", AXComboBox: "Açılır liste", AXPopUpButton: "Açılır liste",
    Button: "Düğme", AXButton: "Düğme", CheckBox: "Onay kutusu", AXCheckBox: "Onay kutusu",
    Text: "Etiket", AXStaticText: "Etiket", DataItem: "Tablo hücresi", AXCell: "Tablo hücresi",
  };
  function elementLocatorField(step, definition) {
    const locator = parameterValue(step, definition.name);
    const wrap = node("div", "field element-locator");
    wrap.append(node("span", "field-label", definition.label));
    if (locator && typeof locator === "object" && (locator.automation_id || locator.name)) {
      const parts = [elementRoles[locator.role] || locator.role || "Alan"];
      if (locator.automation_id) parts.push(`kimlik ${locator.automation_id}`);
      if (locator.name) parts.push(`“${locator.name}”`);
      if (locator.index) parts.push(`${locator.index + 1}. sıra`);
      const card = node("div", "element-card");
      card.append(icon("code"), node("span", "", parts.join(" · ")));
      wrap.append(card);
      if (locator.platform && state.platform && locator.platform !== state.platform)
        wrap.append(note("Bu alan başka bir işletim sisteminde seçilmiş. Bu bilgisayarda Ekranda seç ile yeniden seçin.", "warning"));
    } else {
      wrap.append(note("Henüz alan seçilmedi. Ekranda seç → Konum ile fareyi alanın üzerine getirin; uygulama alan kimliği veriyorsa önerilir.", "warning"));
    }
    if (definition.help) wrap.append(node("p", "help", definition.help));
    return wrap;
  }
  function columnMappingField(step, definition) {
    const key = `${step.id}:${definition.name}`;
    const mapping = parameterValue(step, definition.name);
    let rows = state.drafts.get(key)?.mode === "columns"
      ? clone(state.drafts.get(key).value)
      : Object.entries(mapping && typeof mapping === "object" && !Array.isArray(mapping) ? mapping : {});
    if (!rows.length) rows = [["", ""]];
    const wrap = node("fieldset", "field column-mapping-field");
    wrap.append(node("legend", "field-label", definition.label));
    const list = node("div", "column-mapping");
    const error = node("div", "field-error");
    error.setAttribute("role", "status");
    const add = button("Sütun ekle", "plus", () => {
      if (rows.length >= 32) return;
      rows.push(["", ""]);
      update();
      render();
      list.lastElementChild?.querySelector("input")?.focus();
    }, "small");
    function update(mark = true) {
      const pairs = rows.map(([name, column]) => [name.trim(), column.trim().replace(/^\$/, "").toUpperCase()]);
      const names = pairs.map(([name]) => name);
      const columns = pairs.map(([, column]) => column);
      const columnNumber = (column) => [...column].reduce((n, char) => n * 26 + char.charCodeAt(0) - 64, 0);
      let message = "";
      if (names.some((name) => !/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(name) || ["row_number", "__proto__", "prototype", "constructor"].includes(name)))
        message = "Alan adında harf, rakam ve alt çizgi kullanın; harf veya alt çizgiyle başlayın. Örnek: form_id.";
      else if (new Set(names).size !== names.length) message = "Her alanın adı farklı olmalıdır.";
      else if (columns.some((column) => !/^[A-Z]{1,3}$/.test(column))) message = "Sütunu harfle belirtin: B, C veya AA gibi.";
      else if (new Set(columns).size !== columns.length) message = "Her sütunu yalnızca bir kez ekleyin.";
      else if (Math.max(...columns.map(columnNumber)) - Math.min(...columns.map(columnNumber)) >= 64)
        message = "Seçilen sütunları en fazla 64 sütunluk bir aralık içinde tutun.";
      error.textContent = message;
      wrap.classList.toggle("invalid", Boolean(message));
      if (message) {
        state.fieldErrors.add(key);
        state.drafts.set(key, { mode: "columns", value: clone(rows) });
      } else {
        state.fieldErrors.delete(key);
        state.drafts.delete(key);
        step.params[definition.name] = Object.fromEntries(pairs);
      }
      if (mark) markDirty();
    }
    function render() {
      list.replaceChildren();
      rows.forEach((entry, index) => {
        const line = node("div", "column-mapping-row");
        const name = textInput(entry[0], "form_id");
        name.maxLength = 64;
        name.setAttribute("aria-label", `Alan adı ${index + 1}`);
        const column = textInput(entry[1], "B");
        column.classList.add("column-letter");
        column.maxLength = 4;
        column.setAttribute("aria-label", `Sütun ${index + 1}`);
        name.addEventListener("input", () => { entry[0] = name.value; update(); });
        column.addEventListener("input", () => { entry[1] = column.value; update(); });
        const remove = iconButton(`Sütun eşlemesini kaldır ${index + 1}`, "trash", () => {
          rows.splice(index, 1);
          update();
          render();
        });
        remove.disabled = rows.length <= 1;
        line.append(name, node("span", "muted", "←"), column, remove);
        list.append(line);
      });
      add.disabled = rows.length >= 32;
    }
    wrap.append(node("p", "help column-mapping-hint", "Alan adı ← Sheets sütunu"), list, add, error);
    if (definition.help) wrap.append(node("p", "help", definition.help));
    render();
    update(false);
    return wrap;
  }
  function loopDataSource(step) {
    const reference = String(parameterValue(step, "items") || "").match(/^\$\{([^}.]+)\}$/);
    return reference && (precedingSteps(step.id) || []).reverse().find(
      (previous) => parameterValue(previous, "output") === reference[1]);
  }
  function loopVariableNames(step) {
    if (["control.repeat", "control.while"].includes(step.action)) return ["loop_index"];
    if (step.action === "control.try") return [parameterValue(step, "error_name") || "error_message"];
    if (step.action !== "control.for_each") return [];
    const item = parameterValue(step, "item_name") || "row";
    const producer = loopDataSource(step);
    const columns = producer?.action === "sheets.read_rows" ? parameterValue(producer, "columns") : null;
    const fields = columns && typeof columns === "object" && !Array.isArray(columns)
      ? Object.keys(columns) : ["value", "cell"];
    return [item, `${item}.row_number`, ...fields.map((name) => `${item}.${name}`)];
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
          "Çalıştır, adımları gerçekten uygular. Önizleme seçeneği ekran, dosya ve bağlantı adımlarını atlar. Bir adımı tek başına denemek için adımı seçip Bu adımı test et düğmesini kullanın.",
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
    pane.append(field("Adım adı", title));
    if (!["control.break", "control.continue"].includes(step.action)) {
      const tester = button("Bu adımı test et", "play", () => openStepTest(step), "small step-test-button");
      tester.title = "Yalnız bu adımı (iç adımlarıyla) örnek değerlerle çalıştırır.";
      pane.append(tester);
    }
    pane.append(node("div", "inspector-divider"));
    step.params ||= {};
    const extraTools = stepTools(step, spec);
    if (extraTools) pane.append(extraTools);
    if (step.action === "desktop.find_window") pane.append(windowRecognitionTools(step));
    const targetActions = ["desktop.window_click", "desktop.window_fill", "desktop.window_wait_image", "window.read_field"];
    let targetTools = targetActions.includes(step.action) ? windowTargetTools(step) : null;
    if (targetTools) pane.append(targetTools);
    if (step.action === "desktop.window_write" && state.catalog.some((item) => item.type === "desktop.window_fill")) {
      const conversion = node("div", "legacy-action-help");
      conversion.append(
        note("Bu eski adım odaklanmış alana yazar. Alanı doldur adımında hedef alanı da seçebilirsiniz."),
        button("Alanı doldur adımına dönüştür", "edit", () => {
          if ([...state.fieldErrors].some((key) => key.startsWith(`${step.id}:`))) {
            toast("Önce bu adımdaki geçersiz değerleri düzeltin.", true);
            return;
          }
          const replacement = specFor("desktop.window_fill");
          const previous = { ...step.params };
          const oldLabel = specFor(step.action).label;
          step.params = {};
          (replacement.fields || []).forEach((definition) => {
            if (definition.default !== undefined && definition.default !== null)
              step.params[definition.name] = clone(definition.default);
          });
          // Preserve existing values, and require the user to select a target.
          Object.assign(step.params, previous);
          delete step.params.x;
          delete step.params.y;
          step.params.target_mode = "coordinates";
          step.action = replacement.type;
          if (!step.title || step.title === oldLabel) step.title = replacement.label;
          for (const key of state.fieldErrors) if (key.startsWith(`${step.id}:`)) state.fieldErrors.delete(key);
          for (const key of state.drafts.keys()) if (key.startsWith(`${step.id}:`)) state.drafts.delete(key);
          markDirty();
          renderInspector();
          renderCanvas();
          toast("Yazılacak değer korundu. ERP ekranından hedef alanı seçin.");
        }, "small"),
      );
      pane.append(conversion);
    }
    if (["control.for_each", "control.while"].includes(step.action)) {
      const help = node("div", "loop-help");
      const conditional = step.action === "control.while";
      help.append(
        note(conditional ? "Koşul her turdan önce kontrol edilir. İç adımlarda koşulu etkileyen değeri yeniden okuyun veya değiştirin. Tekrar ve süre sınırına ulaşılırsa akış hata ile durur." : "Listedeki her satır için İç adımlar sırayla çalışır. Koşul veya başka bir döngü de ekleyebilirsiniz."),
        button(conditional ? "Her tekrarda yapılacak adımı ekle" : "Her satırda yapılacak adımı ekle", "plus", () => setTarget(step, "children"), "small"),
      );
      pane.append(help);
    }
    if (step.action === "sheets.read_column") pane.append(note("B2 başlangıcıyla B2, B3, B4… okunur. Çıktıyı Her satır için adımına bağlayın; ${row.value} o satırdaki hücrenin değeridir."));
    if (step.action === "sheets.read_rows") pane.append(note("FormID ve durum birlikte okunur. Durum boş olsa da FormID doluysa kayıt korunur. Döngünün içindeki Koşul adımında ${row.status} değerini kontrol edin."));
    (spec.fields || []).forEach((f) => {
      const key = `${step.id}:${f.name}`;
      if (!fieldVisible(step, f)) {
        state.fieldErrors.delete(key);
        return;
      }
      if (f.type === "columns") {
        pane.append(columnMappingField(step, f));
        return;
      }
      if (f.type === "element") {
        pane.append(elementLocatorField(step, f));
        return;
      }
      let control, jsonMode;
      const value = parameterValue(step, f.name);
      if (state.drafts.has(key)) state.fieldErrors.add(key);
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
      } else if (f.type === "workflow") {
        control = node("select");
        const blank = node("option", "", "Akış seçin…");
        blank.value = "";
        control.append(blank);
        state.workflows.filter((item) => item.id !== state.workflow.id).forEach((item) => {
          const option = node("option", "", item.name);
          option.value = item.id;
          control.append(option);
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
      if (f.type === "path") {
        const row = node("div", "path-row");
        control.replaceWith(row);
        const browse = button("Seç…", "folder", async () => {
          const kind = f.name === "folder" ? "folder"
            : ["file.write_text", "file.write_table"].includes(step.action) ? "save" : "open";
          try {
            const chosen = await api("/api/desktop/choose-path", { method: "POST", body: JSON.stringify({ kind }) });
            if (chosen.path) {
              control.value = chosen.path;
              control.dispatchEvent(new Event("input"));
            }
          } catch (error) {
            toast(error.message, true);
          }
        }, "small");
        row.append(control, browse);
      }
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
        if (f.name === "window" && targetTools) {
          const updated = windowTargetTools(step);
          targetTools.replaceWith(updated);
          targetTools = updated;
        }
        markDirty();
        if (f.name === "output") renderCanvas();
        if ((spec.fields || []).some((definition) => Object.hasOwn(definition.visible_when || {}, f.name)) ||
            (f.name === "operator" && ["control.if", "control.while"].includes(step.action)))
          renderInspector();
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
        ["select", "boolean", "workflow"].includes(f.type) ? "change" : "input",
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
            ...loopVariableNames(s),
          ])
          .filter(Boolean),
      ),
    ];
    for (const name of ["sistem.masaustu", "sistem.indirilenler", "sistem.belgeler", "sistem.bugun",
      "sistem.isletim_sistemi", "sistem.kullanici"])
      if (!names.includes(name)) names.push(name);
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
      ["dry", "Önizleme çalışmaları"],
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
            `${run.department || "Genel"}${run.test_step_id ? " · Adım testi" : ""}${run.dry_run ? " · Önizleme" : ""}`,
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
          "Önizleme: bu çalışmada fare, klavye, ekran, dosya ve bağlantı adımları atlandı; yalnız veri adımları hesaplandı. Gerçek işlem için Önizleme seçeneği kapalıyken çalıştırın.",
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
        node("span", "", run.test_step_id ? "Adım testi" : run.dry_run ? "Önizleme" : "Gerçek çalışma"),
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
    form.append(licensePanel(panel));
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

  function initials(name) {
    const parts = String(name || "").split(/[\s@._-]+/).filter(Boolean);
    return (parts.slice(0, 2).map((part) => part[0]).join("") || "RO").toLocaleUpperCase("tr-TR");
  }
  function licenseDate(value) {
    if (!value) return "";
    const [year, month, day] = String(value).slice(0, 10).split("-");
    return year && month && day ? `${day}.${month}.${year}` : "";
  }
  function licenseDaysLeft(account) {
    if (!account?.ends_on) return null;
    const end = new Date(`${account.ends_on}T23:59:59+03:00`);
    return Math.max(0, Math.ceil((end - Date.now()) / 86400000));
  }
  function licenseTerm(account) {
    const days = licenseDaysLeft(account);
    if (days === null) return account?.user ? "Süresiz lisans" : "";
    return days <= 30 ? `${days} gün kaldı` : `${licenseDate(account.ends_on)} tarihine kadar`;
  }
  function licensePanel(panel) {
    const account = state.license?.license || {};
    const section = panel(
      "RpaOrkestrAI lisansı", "key",
      "Lisans orkestrai.net hesabınıza bağlıdır. İnternet yokken son doğrulamadan sonra en fazla 7 gün kullanılabilir.",
    );
    const rows = node("dl", "license-facts");
    const days = licenseDaysLeft(account);
    for (const [label, value] of [
      ["Kullanıcı", account.full_name ? `${account.full_name} (${account.user})` : account.user],
      ["Firma", account.company],
      ["Bitiş", account.ends_on ? `${licenseDate(account.ends_on)}${days !== null ? ` · ${days} gün kaldı` : ""}` : "Süresiz"],
      ["Son doğrulama", state.license?.online === false
        ? `Çevrimdışı; ${when(account.valid_until)} tarihine kadar geçerli`
        : "orkestrai.net ile doğrulandı"],
    ]) {
      if (!value) continue;
      rows.append(node("dt", "", label), node("dd", "", value));
    }
    const actions = node("div", "update-actions");
    const verify = button("Lisansı şimdi doğrula", "refresh", () => attempt(async () => {
      verify.disabled = true;
      try {
        const result = await api("/api/license/refresh", { method: "POST" });
        if (result.state !== "valid") return showLicenseGate(result);
        state.license = result;
        toast(result.online === false ? "orkestrai.net'e ulaşılamadı; kayıtlı lisans kullanılıyor." : "Lisans doğrulandı.");
        render();
      } finally {
        verify.disabled = false;
      }
    }));
    actions.append(verify, button("Oturumu kapat", "logout", () => logoutLicense()));
    section.append(rows, actions);
    return section;
  }
  async function logoutLicense() {
    const ok = await confirmDialog(
      "Oturumu kapat",
      "Bu bilgisayardaki lisans oturumu kapatılır. Akışlarınız ve bağlantı ayarlarınız korunur; yeniden giriş için internet gerekir.",
      "Oturumu kapat",
    );
    if (!ok) return;
    if (state.dirty && !(await confirmDialog(
      "Kaydedilmemiş değişiklikler",
      "Açık akıştaki kaydedilmemiş değişiklikler kaybolacak. Devam edilsin mi?",
      "Kaydetmeden çık",
      true,
    ))) return;
    await attempt(async () => showLicenseGate(await api("/api/license/logout", { method: "POST" })));
  }
  function showLicenseGate(status) {
    stopPolling();
    clearTimeout(state.updatePoll);
    clearInterval(state.licenseTimer);
    document.querySelectorAll("dialog").forEach((el) => el.close());
    state.license = status;
    state.dirty = false;
    root.replaceChildren();
    root.setAttribute("aria-busy", "false");
    const screen = node("main", "boot-screen license-screen");
    const card = node("section", "license-card");
    const mark = node("span", "brand-mark", "O");
    mark.append(node("span"));
    card.append(mark);
    if (status.state === "expired" || status.state === "denied") closingNotice(card, status);
    else loginForm(card, status);
    screen.append(card);
    root.append(screen);
  }
  function loginForm(card, status) {
    card.append(
      node("h1", "", "RpaOrkestrAI"),
      node("p", "", "orkestrai.net kullanıcı adınız ve şifrenizle giriş yapın. Şifreniz bu bilgisayara kaydedilmez."),
    );
    const message = node("div", "license-message");
    message.setAttribute("role", "alert");
    const show = (text, variant = "error") => message.replaceChildren(text ? note(text, variant) : "");
    if (status.message) show(status.message, "warning");
    card.append(message);
    if (status.state === "verification_required" && status.remembered) {
      const retry = button("Yeniden doğrula", "refresh", async () => {
        retry.disabled = true;
        try {
          const result = await api("/api/license/refresh", { method: "POST" });
          if (result.state === "valid") return boot();
          if (result.state !== "verification_required") return showLicenseGate(result);
          show(result.online === false
            ? "orkestrai.net'e hâlâ ulaşılamıyor. Bağlantıyı kontrol edip tekrar deneyin."
            : result.message, "warning");
        } catch (error) {
          show(error.message);
        } finally {
          retry.disabled = false;
        }
      });
      card.append(retry);
    }
    const form = node("form", "license-form");
    const username = textInput(status.license?.user || "", "kullanıcı adı veya e-posta");
    username.autocomplete = "username";
    username.spellcheck = false;
    username.autocapitalize = "none";
    username.required = true;
    const password = textInput("", "", "password");
    password.autocomplete = "current-password";
    password.required = true;
    const submit = button("Giriş yap", "arrow", null, "primary");
    submit.type = "submit";
    form.append(
      field("Kullanıcı adı", username, "E-posta adresinizin @ işaretinden önceki kısmı veya e-postanın tamamı."),
      field("Şifre", password),
      submit,
    );
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      submit.disabled = true;
      show("");
      try {
        const result = await api("/api/license/login", {
          method: "POST",
          body: JSON.stringify({ username: username.value.trim(), password: password.value }),
        });
        password.value = "";
        if (result.state === "valid") return boot();
        showLicenseGate(result);
      } catch (error) {
        show(error.message);
        password.select();
      } finally {
        submit.disabled = false;
      }
    });
    card.append(form, node("p", "license-footnote", "Hesap ve lisans işlemleri için firma yöneticinize başvurun."));
    queueMicrotask(() => (username.value ? password : username).focus());
  }
  function closingNotice(card, status) {
    const expired = status.state === "expired";
    card.append(
      node("h1", "", expired ? "Kullanım süreniz dolmuştur" : "Lisans tanımlı değil"),
      node("p", "", status.message || (expired
        ? "RpaOrkestrAI kullanım süreniz dolmuştur."
        : "Bu kullanıcı için RpaOrkestrAI lisansı tanımlı değil.")),
    );
    if (status.license?.user) card.append(node("p", "license-footnote", `Kullanıcı: ${status.license.user}`));
    card.append(node("p", "", "Lisansınızı yenilemek veya yetki almak için firma yöneticinize başvurun."));
    const countdown = node("p", "license-countdown");
    countdown.setAttribute("aria-live", "polite");
    const actions = node("div", "license-actions");
    const quit = async () => {
      clearInterval(state.licenseTimer);
      try {
        await api("/api/license/quit", { method: "POST" });
        countdown.textContent = "Uygulama kapanıyor…";
      } catch (error) {
        countdown.textContent = error.message;
      }
    };
    if (status.can_quit) {
      let remaining = 15;
      const paint = () => { countdown.textContent = `Uygulama ${remaining} saniye içinde kapanacak.`; };
      paint();
      state.licenseTimer = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) quit();
        else paint();
      }, 1000);
      actions.append(button("Şimdi kapat", "cross", quit, "primary"));
    } else {
      countdown.textContent = "Bu tarayıcı sekmesini kapatabilirsiniz.";
    }
    const recheck = button("Yeniden kontrol et", "refresh", async () => {
      recheck.disabled = true;
      try {
        const result = await api("/api/license/refresh", { method: "POST" });
        if (result.state === "valid") {
          clearInterval(state.licenseTimer);
          return boot();
        }
        toast(result.online === false ? "orkestrai.net'e ulaşılamadı." : "Lisans durumu değişmedi.", true);
      } catch (error) {
        toast(error.message, true);
      } finally {
        recheck.disabled = false;
      }
    });
    if (status.remembered) actions.append(recheck);
    actions.append(button("Farklı kullanıcıyla giriş yap", "logout", async () => {
      clearInterval(state.licenseTimer);
      await attempt(async () => showLicenseGate(await api("/api/license/logout", { method: "POST" })));
    }));
    card.append(countdown, actions);
  }
  async function boot() {
    try {
      const license = await api("/api/license");
      if (license.state !== "valid") {
        showLicenseGate(license);
        return;
      }
      state.license = license;
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
    if (!state.updates.enabled || root.querySelector(".license-screen")) return;
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
