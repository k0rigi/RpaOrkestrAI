"use strict";

(() => {
  const statuses = { queued: "Sırada", running: "Çalışıyor", waiting_user: "Yanıt bekliyor",
    waiting_approval: "Onay bekliyor", succeeded: "Tamamlandı", failed: "Hata", cancelled: "Durduruldu" };
  const terminal = new Set(["succeeded", "failed", "cancelled"]);
  const providers = { shared: "Kurum sunucusu", ollama: "Ollama · bu bilgisayar", local_openai: "Yerel OpenAI uyumlu sunucu",
    openai: "OpenAI", gemini: "Google Gemini", anthropic: "Anthropic Claude" };
  const defaultLimits = { max_turns: 20, max_workflow_runs: 10, max_seconds: 1800, max_tokens: 50000,
    max_retries: 1, max_tasks: 20, busy_wait_seconds: 60, approval_timeout_seconds: 900, question_timeout_seconds: 900 };
  const limitLabels = { max_turns: "En fazla karar turu", max_workflow_runs: "En fazla akış çalıştırma",
    max_seconds: "En fazla süre (saniye)", max_tokens: "En fazla token", max_retries: "En fazla yeniden deneme", max_tasks: "En fazla alt görev",
    busy_wait_seconds: "Masaüstü sırası bekleme (saniye)", approval_timeout_seconds: "Onay bekleme (saniye)",
    question_timeout_seconds: "Yanıt bekleme (saniye)" };
  const limitMax = { max_turns: 1000, max_workflow_runs: 1000, max_seconds: 86400, max_tokens: 10000000,
    max_retries: 10, max_tasks: 1000, busy_wait_seconds: 3600, approval_timeout_seconds: 86400, question_timeout_seconds: 86400 };
  const extensions = new Map();
  let active = null;
  let sequence = 0;

  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined && text !== null) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function identify(node, hint = node.tagName.toLowerCase()) {
    node.id = `rpa-agent-${hint}-${++sequence}`;
    return node;
  }
  function action(label, callback, variant = "") {
    const button = identify(element("button", label, `button ${variant}`), "button");
    button.type = "button";
    button.addEventListener("click", callback);
    return button;
  }
  function field(label, value = "", kind = "text", help = "") {
    const wrapper = element("div", null, "agent-field");
    const input = identify(element(kind === "textarea" ? "textarea" : "input"), "field");
    if (kind !== "textarea") input.type = kind;
    else input.rows = 4;
    input.value = value ?? "";
    const caption = element("label", label);
    caption.htmlFor = input.id;
    wrapper.append(caption, input);
    if (help) {
      const hint = identify(element("p", help, "agent-help"), "hint");
      wrapper.append(hint);
      input.setAttribute("aria-describedby", hint.id);
    }
    return { wrapper, input };
  }
  function select(label, choices, value = "", help = "") {
    const result = field(label, "", "text", help);
    const input = document.createElement("select");
    input.id = result.input.id;
    for (const [key, text] of choices) {
      const option = element("option", text);
      option.value = key;
      input.append(option);
    }
    input.value = value ?? "";
    if (result.input.hasAttribute("aria-describedby")) input.setAttribute("aria-describedby", result.input.getAttribute("aria-describedby"));
    result.input.replaceWith(input);
    return { wrapper: result.wrapper, input };
  }
  function toggle(label, checked = false) {
    const wrapper = element("label", null, "agent-toggle");
    const input = identify(element("input"), "check");
    input.type = "checkbox";
    input.checked = Boolean(checked);
    wrapper.htmlFor = input.id;
    wrapper.append(input, element("span", label));
    return { wrapper, input };
  }
  function disclosure(title, content) {
    const details = element("details", null, "agent-details");
    details.append(identify(element("summary", title), "summary"), content);
    return details;
  }
  function timeLabel(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("tr-TR");
  }
  function jsonBlock(value) {
    return element("pre", JSON.stringify(value, null, 2), "agent-json");
  }
  function status(value) {
    return element("span", statuses[value] || "Bilinmiyor", `agent-status agent-status-${Object.hasOwn(statuses, value) ? value : "unknown"}`);
  }
  function empty(title, description) {
    const card = element("div", null, "agent-empty");
    card.append(element("h3", title), element("p", description, "muted"));
    return card;
  }
  function objectInput(input) {
    let value;
    try { value = JSON.parse(input.value.trim() || "{}"); }
    catch { throw new Error("Girdileri geçerli JSON biçiminde yazın. Örnek: {\"dosya\": \"rapor.csv\"}"); }
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Girdiler bir JSON nesnesi olmalıdır.");
    if (Object.keys(value).length > 100 || new TextEncoder().encode(JSON.stringify(value)).length > 65536) {
      throw new Error("En fazla 100 girdi ve toplam 64 KB kullanılabilir.");
    }
    return value;
  }

  function unmount() {
    if (!active) return;
    active.alive = false;
    clearTimeout(active.timer);
    document.removeEventListener("visibilitychange", active.visibility);
    active.extensionCleanup?.();
    active = null;
  }

  async function mount(container, options) {
    unmount();
    const view = { container, options, alive: true, tab: "agents", agents: [], connections: [], workflows: [], runs: [],
      session: {}, selectedRun: null, timer: null, polling: false, pane: null, runView: null, extensionCleanup: null };
    active = view;
    container.classList.add("agent-root");
    container.replaceChildren(element("p", "Ajanlar yükleniyor…", "muted"));
    const request = (path, method = "GET", body) => options.api(path, {
      method, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    view.request = request;
    view.error = (error) => { if (view.alive) options.toast(error?.message || "İşlem tamamlanamadı.", true); };
    view.confirm = async (title, message, label, danger) => {
      if (options.confirmDialog) return options.confirmDialog(title, message, label, danger);
      return window.confirm(`${title}\n\n${message}`);
    };
    view.busy = async (button, work) => {
      if (button.disabled || !view.alive) return;
      button.disabled = true;
      button.setAttribute("aria-busy", "true");
      try { await work(); }
      catch (error) { view.error(error); }
      finally { button.disabled = false; button.removeAttribute("aria-busy"); }
    };
    view.visibility = () => {
      clearTimeout(view.timer);
      if (!document.hidden && view.alive) schedulePoll(view, 0);
    };
    document.addEventListener("visibilitychange", view.visibility);
    try {
      const values = await Promise.all([
        request("/api/agents/session"), request("/api/agents"), request("/api/agents/connections"),
        request("/api/agents/workflows"),
      ]);
      if (!view.alive) return;
      [view.session, view.agents, view.connections, view.workflows] = values;
      shell(view);
      showTab(view, view.tabButtons.has(options.initialTab) ? options.initialTab : "agents");
    } catch (error) {
      if (!view.alive) return;
      const notice = empty("Ajanlar açılamadı", error?.message || "Lisansı ve bağlantıyı kontrol edin.");
      notice.append(action("Yeniden dene", () => mount(container, options)));
      container.replaceChildren(notice);
    }
  }

  function shell(view) {
    const header = element("header", null, "agent-page-head");
    const title = element("div");
    title.append(element("h1", "Ajanlar"), element("p", "Hedefi tanımlayın; izin verdiğiniz akışlarla ilerlemeyi izleyin.", "muted"));
    const user = view.session.actor?.name || "Oturum açık";
    header.append(title, element("span", user, "agent-user"));
    const tabs = element("nav", null, "agent-tabs");
    tabs.setAttribute("aria-label", "Ajan sayfaları");
    view.tabButtons = new Map();
    for (const [id, label] of [["agents", "Ajanlar"], ["runs", "Çalışmalar"], ["connections", "Bağlantılar"],
      ...[...extensions.values()].map((item) => [item.id, item.label])]) {
      const button = action(label, () => showTab(view, id));
      button.dataset.agentTab = id;
      view.tabButtons.set(id, button);
      tabs.append(button);
    }
    view.pane = element("div", null, "agent-pane");
    view.container.replaceChildren(header, tabs, view.pane);
  }

  function showTab(view, tab) {
    if (!view.alive) return;
    view.extensionCleanup?.();
    view.extensionCleanup = null;
    view.tab = tab;
    view.runView = null;
    clearTimeout(view.timer);
    for (const [key, button] of view.tabButtons) {
      button.classList.toggle("active", key === tab);
      button.setAttribute("aria-current", key === tab ? "page" : "false");
    }
    if (tab === "agents") renderAgents(view);
    else if (tab === "runs") renderRuns(view);
    else if (tab === "connections") renderConnections(view);
    else if (extensions.has(tab)) {
      view.pane.replaceChildren();
      const result = extensions.get(tab).mount(view.pane, { ...view.options, session: view.session,
        agents: view.agents, openAgentRun: (identity) => openRun(view, identity),
        openTab: (name) => { if (view.tabButtons.has(name)) showTab(view, name); } });
      if (typeof result === "function") view.extensionCleanup = result;
      else if (result?.then) result.then((cleanup) => {
        if (!view.alive || view.tab !== tab) cleanup?.();
        else view.extensionCleanup = cleanup;
      }).catch(view.error);
    }
    schedulePoll(view, 0);
  }

  function renderAgents(view) {
    const toolbar = element("div", null, "agent-toolbar");
    toolbar.append(element("p", `${view.agents.length} ajan`, "muted"));
    if (view.session.can_manage) toolbar.append(action("Ajan ekle", () => editAgent(view), "primary"));
    const cards = element("div", null, "agent-cards");
    for (const agent of view.agents) {
      const card = element("article", null, "agent-card");
      card.append(element("span", agent.role === "manager" ? "Yönetici ajan" : agent.department, "agent-eyebrow"),
        element("h2", agent.name), element("p", agent.description || "Henüz açıklama eklenmedi.", "muted"),
        element("p", `${agent.workflows.length} izinli akış · ${agent.model || "Model seçilmedi"}`, "agent-help"));
      const buttons = element("div", null, "agent-actions");
      buttons.append(action("Görev ver", () => runForm(view, agent), "primary"));
      if (view.session.can_manage) buttons.append(action("Düzenle", () => editAgent(view, agent)));
      buttons.append(action("Çalışmaları gör", () => { view.filterAgent = agent.id; showTab(view, "runs"); }));
      card.append(buttons);
      cards.append(card);
    }
    if (!view.agents.length) cards.append(empty("İlk ajanınızı oluşturun", "Önce bir model bağlantısı ekleyin, sonra ajanın kullanabileceği akışları seçin."));
    view.pane.replaceChildren(toolbar, cards);
  }

  function editAgent(view, original = null) {
    const agent = original || { name: "", description: "", instructions: "", department: "Genel", role: "department",
      manager_id: null, provider_connection_id: null, model: "", workflows: [], limits: { ...defaultLimits } };
    const form = identify(element("form", null, "agent-form"), "editor");
    const heading = element("div", null, "agent-toolbar");
    heading.append(element("h2", original ? "Ajanı düzenle" : "Yeni ajan"), action("Listeye dön", () => renderAgents(view)));
    const grid = element("div", null, "agent-form-grid");
    const name = field("Ajan adı", agent.name);
    name.input.required = true; name.input.maxLength = 120;
    const department = field("Departman", agent.department, "text", "Firmanızdaki departman adını yazın.");
    department.input.required = true; department.input.maxLength = 120;
    const list = identify(element("datalist"), "departments");
    for (const text of [...new Set(view.workflows.map((w) => w.department))]) {
      const option = element("option"); option.value = text; list.append(option);
    }
    department.input.setAttribute("list", list.id); department.wrapper.append(list);
    const role = select("Rol", [["department", "Departman ajanı"], ["manager", "Yönetici ajan"]], agent.role);
    const manager = select("Bağlı yönetici", [["", "Seçilmedi"], ...view.agents.filter((item) => item.role === "manager" && item.id !== agent.id)
      .map((item) => [item.id, item.name])], agent.manager_id || "");
    const connection = select("Model bağlantısı", [["", "Bağlantı seçin"], ...view.connections.map((item) => [item.id, item.name])],
      agent.provider_connection_id || "", "Bağlantılar bölümünden yerel veya bulut sağlayıcı ekleyebilirsiniz.");
    connection.input.required = true;
    const model = field("Model adı", agent.model, "text", "Sunucuda bulunan model adını yazın; model adı serbesttir.");
    model.input.required = true; model.input.maxLength = 200;
    connection.input.addEventListener("change", () => {
      const selected = view.connections.find((item) => item.id === connection.input.value);
      if (!model.input.value.trim() && selected?.model) model.input.value = selected.model;
      cloudWarning.textContent = providerNotice(selected?.provider);
      cloudWarning.hidden = !cloudWarning.textContent;
    });
    const description = field("Kısa açıklama", agent.description, "textarea");
    description.input.maxLength = 2000;
    const instructions = field("Talimatlar", agent.instructions, "textarea", "Ajanın amacı, çalışma şekli ve belirsizlikte size sorması gereken konular.");
    instructions.input.maxLength = 16000; instructions.input.rows = 6;
    grid.append(name.wrapper, department.wrapper, role.wrapper, manager.wrapper, connection.wrapper, model.wrapper);
    const cloudWarning = element("p", providerNotice(view.connections.find((item) => item.id === connection.input.value)?.provider), "agent-notice");
    cloudWarning.hidden = !cloudWarning.textContent;
    const grants = element("section", null, "agent-grants");
    grants.append(element("h3", "İzin verilen akışlar"), element("p", "Alt akışları da açıkça seçin. Başka departmanın akışı yalnız seçtiğinizde eklenir.", "agent-help"));
    const allDepartments = toggle("Diğer departmanların akışlarını da göster", false);
    grants.append(allDepartments.wrapper);
    const grantRows = [];
    for (const workflow of view.workflows) {
      const grant = agent.workflows.find((item) => item.workflow_id === workflow.id);
      const row = element("div", null, "agent-grant-row");
      const allowed = toggle(workflow.name, Boolean(grant));
      const highRisk = workflow.risk === "geri_alinamaz";
      row.append(allowed.wrapper, element("span", highRisk ? "Onay gerektiren işlem" : "Okuma / analiz", `agent-risk ${highRisk ? "high" : "low"}`));
      row.append(element("p", `${workflow.department} · ${workflow.description || "Açıklama yok"}`, "agent-help"));
      const blocked = workflow.agent_supported === false;
      allowed.input.disabled = blocked && !grant;
      if (blocked) row.append(element("p", workflow.blocked_reason || "Bu akış ajanla çalıştırılmaya uygun değil.", "agent-notice"));
      const settings = element("div", null, "agent-grant-settings");
      const automatic = toggle("Onaysız çalışabilir", grant?.allow_without_approval || false);
      automatic.input.disabled = !view.session.can_approve;
      const roots = field("İzin verilen dosya klasörleri", (grant?.allowed_roots || []).join("\n"), "textarea",
        "Dosya kullanan akışlarda her satıra tam bir klasör yolu yazın. Bu klasörlerin dışına erişilemez.");
      roots.input.rows = 2;
      settings.append(automatic.wrapper, element("p", "Bu tercih yalnız onay yetkilisi tarafından değiştirilir ve kayda geçer.", "agent-help"), roots.wrapper);
      row.append(settings);
      const update = () => { settings.hidden = !allowed.input.checked; };
      allowed.input.addEventListener("change", update); update();
      grantRows.push({ row, workflow, grant, allowed, automatic, roots });
      grants.append(row);
    }
    const filterGrants = () => {
      for (const item of grantRows) item.row.hidden = !allDepartments.input.checked && !item.allowed.input.checked
        && item.workflow.department !== department.input.value;
    };
    department.input.addEventListener("input", filterGrants);
    allDepartments.input.addEventListener("change", filterGrants);
    filterGrants();
    const updateRole = () => { grants.hidden = role.input.value === "manager"; manager.wrapper.hidden = role.input.value === "manager"; };
    role.input.addEventListener("change", updateRole); updateRole();
    const limits = element("div", null, "agent-form-grid");
    const limitFields = {};
    for (const [key, initial] of Object.entries(defaultLimits)) {
      const item = field(limitLabels[key], agent.limits?.[key] ?? initial, "number");
      item.input.min = ["max_retries", "max_workflow_runs", "busy_wait_seconds"].includes(key) ? "0" : "1";
      item.input.max = String(limitMax[key]); item.input.required = true;
      limits.append(item.wrapper); limitFields[key] = item.input;
    }
    const buttons = element("div", null, "agent-actions");
    const save = action("Ajanı kaydet", () => form.requestSubmit(), "primary");
    buttons.append(save, action("Vazgeç", () => renderAgents(view)));
    if (original) {
      const remove = action("Ajanı kaldır", () => view.busy(remove, async () => {
        if (!await view.confirm("Ajan kaldırılsın mı?", "Bu ajanın etkin çalışmaları durdurulur. Geçmiş kayıtlar korunur.", "Kaldır", true)) return;
        await view.request(`/api/agents/${original.id}`, "DELETE");
        view.agents = view.agents.filter((item) => item.id !== original.id);
        if (view.alive) renderAgents(view);
      }), "danger");
      buttons.append(remove);
    }
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      view.busy(save, async () => {
        const body = { name: name.input.value.trim(), description: description.input.value, instructions: instructions.input.value,
          department: department.input.value.trim(), role: role.input.value,
          manager_id: role.input.value === "manager" ? null : manager.input.value || null,
          provider_connection_id: connection.input.value || null, model: model.input.value.trim(),
          workflows: role.input.value === "manager" ? [] : grantRows.filter((item) => item.allowed.input.checked).map((item) => ({
            workflow_id: item.workflow.id, allow_without_approval: item.automatic.input.checked,
            allowed_roots: item.roots.input.value.split("\n").map((line) => line.trim()).filter(Boolean),
            allowed_hosts: item.grant?.allowed_hosts || [],
          })), limits: Object.fromEntries(Object.entries(limitFields).map(([key, input]) => [key, Number(input.value)])) };
        const saved = await view.request(original ? `/api/agents/${original.id}` : "/api/agents", original ? "PUT" : "POST", body);
        view.agents = [...view.agents.filter((item) => item.id !== saved.id), saved];
        if (view.alive) { view.options.toast("Ajan kaydedildi."); renderAgents(view); }
      });
    });
    form.append(heading, grid, cloudWarning, description.wrapper, instructions.wrapper, grants,
      disclosure("Çalışma sınırları", limits), buttons);
    view.pane.replaceChildren(form);
    name.input.focus();
  }

  function runForm(view, agent) {
    const form = identify(element("form", null, "agent-form"), "task");
    form.append(element("h2", `${agent.name} için görev`));
    const task = field("Hedefiniz", "", "textarea", "Beklediğiniz sonucu yazın. Ajan yalnız izin verdiğiniz akışları kullanır.");
    task.input.required = true; task.input.maxLength = 16000; task.input.rows = 6;
    const inputs = field("Başlangıç girdileri (JSON)", "{}", "textarea", "Gerekmiyorsa boş nesne olarak bırakın.");
    const start = action("Görevi başlat", () => form.requestSubmit(), "primary");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      view.busy(start, async () => {
        const run = await view.request(`/api/agents/${agent.id}/runs`, "POST", { task: task.input.value, inputs: objectInput(inputs.input) });
        view.runs = [run, ...view.runs.filter((item) => item.id !== run.id)];
        if (view.alive) openRun(view, run.id);
      });
    });
    const buttons = element("div", null, "agent-actions");
    buttons.append(start, action("Vazgeç", () => renderAgents(view)));
    form.append(task.wrapper, disclosure("Girdi değişkenleri", inputs.wrapper), buttons);
    view.pane.replaceChildren(form); task.input.focus();
  }

  function renderRuns(view) {
    const layout = element("div", null, "agent-run-layout");
    const aside = element("aside", null, "agent-run-list");
    const filter = select("Ajan", [["", "Tüm ajanlar"], ...view.agents.map((item) => [item.id, item.name])], view.filterAgent || "");
    filter.input.addEventListener("change", () => { view.filterAgent = filter.input.value; updateRunsList(view); });
    view.runList = element("div"); aside.append(filter.wrapper, view.runList);
    view.runPane = element("section", null, "agent-run-pane");
    layout.append(aside, view.runPane); view.pane.replaceChildren(layout);
    updateRunsList(view);
    const selected = view.runs.find((item) => item.id === view.selectedRun);
    if (selected) updateRun(view, selected);
    else view.runPane.append(empty("Bir çalışma seçin", "Ajanın kararları, akışları ve bekleyen soruları burada görünür."));
  }
  function updateRunsList(view) {
    if (view.tab !== "runs" || !view.runList) return;
    const nodes = view.runs.filter((item) => !view.filterAgent || item.agent_id === view.filterAgent).map((run) => {
      const button = action("", () => openRun(view, run.id), "agent-run-choice");
      button.classList.toggle("selected", run.id === view.selectedRun);
      button.append(element("strong", run.title || run.task?.slice(0, 100) || "Ajan görevi"), status(run.status),
        element("small", timeLabel(run.created_at), "muted"));
      return button;
    });
    view.runList.replaceChildren(...(nodes.length ? nodes : [empty("Çalışma yok", "Ajanlar bölümünden bir görev başlatabilirsiniz.")]));
  }
  async function openRun(view, identity) {
    view.selectedRun = identity;
    if (view.tab !== "runs") showTab(view, "runs");
    try {
      const run = await view.request(`/api/agents/runs/${identity}`);
      if (!view.alive || view.selectedRun !== identity || view.tab !== "runs") return;
      updateRun(view, run); updateRunsList(view);
    } catch (error) { view.error(error); }
  }
  function updateRun(view, run) {
    if (!view.runView || view.runView.id !== run.id) {
      const header = element("div", null, "agent-toolbar");
      const title = element("h2", run.title || "Ajan çalışması");
      const stop = action("Durdur", () => view.busy(stop, async () => {
        await view.request(`/api/agents/runs/${run.id}/cancel`, "POST");
        if (view.alive) await openRun(view, run.id);
      }), "danger");
      const statusBox = element("div", null, "agent-actions"); header.append(title, statusBox, stop);
      const task = element("p", run.task, "agent-task-text");
      const stats = element("p", "", "agent-help");
      const pending = element("div");
      const timeline = element("ol", null, "agent-timeline"); timeline.setAttribute("aria-label", "Çalışma zaman çizelgesi");
      const result = element("section", null, "agent-run-result");
      view.runPane.replaceChildren(header, task, stats, pending, timeline, result);
      view.runView = { id: run.id, title, task, stop, statusBox, stats, pending, pendingKey: null,
        questionId: null, answerInput: null, timeline, events: new Map(), result, resultKey: null };
    }
    const ui = view.runView;
    ui.title.textContent = run.title || "Ajan çalışması";
    ui.task.textContent = run.task || "";
    ui.statusBox.replaceChildren(status(run.status));
    ui.stop.hidden = terminal.has(run.status);
    ui.stats.textContent = `${run.workflow_count || 0} akış · ${run.turns || 0} karar turu · ${run.total_tokens || 0} token · Başlangıç: ${timeLabel(run.started_at)}`;
    updatePending(view, run, ui);
    const visibleEvents = new Set();
    for (const event of run.events || []) {
      visibleEvents.add(event.id);
      const signature = JSON.stringify([event.kind, event.message, event.timestamp, event.data]);
      const previous = ui.events.get(event.id);
      if (previous?.signature === signature) continue;
      const item = element("li", null, "agent-event");
      item.append(element("small", timeLabel(event.timestamp), "muted"), element("p", event.message || event.kind));
      const runId = event.kind === "workflow_started" ? event.data?.run_id : null;
      if (typeof runId === "string" && /^[a-f0-9]{32}$/.test(runId)) {
        item.append(action("Akış çalışma kaydını aç", () => Promise.resolve(view.options.openRun(runId)).catch(view.error)));
      }
      if (event.data && Object.keys(event.data).length) item.append(disclosure("Ayrıntı", jsonBlock(event.data)));
      if (previous) previous.item.replaceWith(item);
      else ui.timeline.append(item);
      ui.events.set(event.id, { signature, item });
    }
    for (const [identity, event] of ui.events) {
      if (!visibleEvents.has(identity)) { event.item.remove(); ui.events.delete(identity); }
    }
    const resultKey = JSON.stringify([run.summary, run.result, run.error]);
    if (resultKey !== ui.resultKey) {
      ui.resultKey = resultKey;
      ui.result.replaceChildren();
      if (run.error) ui.result.append(element("p", run.error, "agent-error"));
      if (run.summary) ui.result.append(element("h3", "Sonuç"), element("p", run.summary, "agent-task-text"));
      if (run.result !== null && run.result !== undefined) ui.result.append(disclosure("Yapılandırılmış sonuç", jsonBlock(run.result)));
    }
  }
  function updatePending(view, run, ui) {
    const question = run.pending_question, approval = run.pending_approval;
    const key = JSON.stringify([question, approval, view.session.can_approve]);
    if (key === ui.pendingKey) return;
    const draft = question && ui.questionId === question.id ? ui.answerInput?.value || "" : "";
    ui.questionId = question?.id || null; ui.answerInput = null;
    ui.pendingKey = key; ui.pending.replaceChildren();
    if (question) {
      const form = identify(element("form", null, "agent-pending"), "question");
      form.append(element("h3", "Ajanın sorusu"), element("p", question.question, "agent-task-text"));
      const answer = field("Yanıtınız", "", "textarea"); answer.input.required = true; answer.input.maxLength = 20000;
      answer.input.value = draft; ui.answerInput = answer.input;
      for (const [index, choice] of (question.options || []).entries()) {
        const label = typeof choice === "string" ? choice : choice.label || choice.value || `Seçenek ${index + 1}`;
        form.append(action(label, () => { answer.input.value = label; answer.input.focus(); }));
      }
      const send = action("Yanıtla", () => form.requestSubmit(), "primary");
      form.addEventListener("submit", (event) => { event.preventDefault(); view.busy(send, async () => {
        await view.request(`/api/agents/runs/${run.id}/questions/${question.id}/answer`, "POST", { answer: answer.input.value });
        if (view.alive && view.selectedRun === run.id) await openRun(view, run.id);
      }); });
      form.append(answer.wrapper, element("p", `Yanıt süresi: ${timeLabel(question.expires_at)}`, "agent-help"), send);
      ui.pending.append(form);
    } else if (approval) {
      const card = element("section", null, "agent-pending approval");
      card.append(element("h3", "İşlem onayı gerekiyor"), element("p", approval.workflow_name || "Seçilen akış"),
        element("p", approval.reason || "Gerekçe belirtilmedi.", "agent-task-text"), element("h4", "Onaylanacak girdiler"),
        jsonBlock(approval.inputs || {}), element("p", `Onay süresi: ${timeLabel(approval.expires_at)}`, "agent-help"));
      if (view.session.can_approve) {
        const controls = element("div", null, "agent-actions");
        for (const approved of [true, false]) {
          const button = action(approved ? "Onayla" : "Reddet", () => view.busy(button, async () => {
            await view.request(`/api/agents/runs/${run.id}/approvals/${approval.id}/decision`, "POST", { approved });
            if (view.alive && view.selectedRun === run.id) await openRun(view, run.id);
          }), approved ? "primary" : "danger");
          controls.append(button);
        }
        card.append(controls);
      } else card.append(element("p", "Bu işlemi yalnız ürün sahibi onaylayabilir. Onay gelene kadar akış başlamaz.", "agent-notice"));
      ui.pending.append(card);
    }
  }

  function isCloud(provider) { return ["openai", "gemini", "anthropic"].includes(provider); }
  function cloudText() { return "Akış sonuçları bu sağlayıcıya gönderilir; hassas veri için yerel model kullanın."; }
  function providerNotice(provider) {
    if (provider === "shared") return "Görev ve maskelenmiş akış sonuçları kurumunuzun ortak model sunucusuna gönderilir.";
    return isCloud(provider) ? cloudText() : "";
  }
  function renderConnections(view) {
    const toolbar = element("div", null, "agent-toolbar");
    toolbar.append(element("p", "API anahtarları sistem şifre kasasında saklanır ve geri gösterilmez.", "muted"));
    if (view.session.can_manage) toolbar.append(action("Bağlantı ekle", () => editConnection(view), "primary"));
    const cards = element("div", null, "agent-cards");
    for (const connection of view.connections) {
      const card = element("article", null, "agent-card");
      card.append(element("h2", connection.name), element("p", providers[connection.provider] || connection.provider, "agent-eyebrow"),
        element("p", connection.model || "Model adı ajan üzerinde seçilebilir.", "muted"),
        element("p", connection.has_key ? "API anahtarı kayıtlı" : isCloud(connection.provider) ? "API anahtarı gerekli"
          : connection.provider === "shared" ? "Kurum hesabınızla bağlanır" : "Yerel bağlantı", "agent-help"));
      if (providerNotice(connection.provider)) card.append(element("p", providerNotice(connection.provider), "agent-notice"));
      const controls = element("div", null, "agent-actions");
      if (view.session.can_manage) controls.append(action("Düzenle", () => editConnection(view, connection)));
      const test = action("Bağlantıyı test et", () => view.busy(test, async () => {
        if (isCloud(connection.provider) && !await view.confirm("Bağlantı testi", "Kısa bir test isteği sağlayıcı kullanım ücreti oluşturabilir. Akış verisi gönderilmez.", "Test et")) return;
        const result = await view.request(`/api/agents/connections/${connection.id}/test`, "POST", {});
        if (view.alive) view.options.toast(result.message || "Bağlantı doğrulandı.");
      }));
      if (view.session.can_manage) controls.append(test);
      card.append(controls); cards.append(card);
    }
    if (!view.connections.length) cards.append(empty("Model bağlantısı ekleyin", "Başlangıç için bu bilgisayardaki Ollama sunucusunu kullanabilirsiniz."));
    view.pane.replaceChildren(toolbar, cards);
  }
  function editConnection(view, original = null) {
    const connection = original || { name: "", provider: "ollama", model: "", base_url: "http://127.0.0.1:11434" };
    const form = identify(element("form", null, "agent-form"), "connection");
    form.append(element("h2", original ? "Bağlantıyı düzenle" : "Yeni model bağlantısı"));
    const name = field("Bağlantı adı", connection.name); name.input.required = true; name.input.maxLength = 120;
    const provider = select("Sağlayıcı", Object.entries(providers), connection.provider); provider.input.disabled = Boolean(original);
    const model = field("Varsayılan model adı", connection.model, "text", "Ollama veya sağlayıcı hesabınızda bulunan model adını yazın.");
    model.input.maxLength = 200;
    const address = field("Yerel sunucu adresi", connection.base_url || "", "url", "Bu bilgisayardaki loopback adresini kullanın. Ortak sunucu ayrı kurum bağlantısıyla tanımlanır.");
    const key = field("Yeni API anahtarı", "", "password", original?.has_key ? "Anahtar kayıtlı. Değiştirmeyecekseniz boş bırakın." : "Yalnız sistem şifre kasasına yazılır.");
    key.input.autocomplete = "new-password"; key.input.maxLength = 1000;
    const notice = element("p", "", "agent-notice");
    const update = () => {
      const cloud = isCloud(provider.input.value), shared = provider.input.value === "shared";
      address.wrapper.hidden = cloud || shared;
      address.input.disabled = cloud || shared;
      notice.textContent = providerNotice(provider.input.value); notice.hidden = !notice.textContent;
      key.wrapper.hidden = provider.input.value === "ollama" || shared;
      key.input.disabled = key.wrapper.hidden;
      if (!cloud && !shared && !address.input.value) address.input.value = provider.input.value === "ollama" ? "http://127.0.0.1:11434" : "http://127.0.0.1:1234";
    };
    provider.input.addEventListener("change", () => { address.input.value = ""; update(); }); update();
    const controls = element("div", null, "agent-actions");
    const save = action("Bağlantıyı kaydet", () => form.requestSubmit(), "primary");
    controls.append(save, action("Vazgeç", () => renderConnections(view)));
    if (original) {
      const remove = action("Bağlantıyı kaldır", () => view.busy(remove, async () => {
        if (!await view.confirm("Bağlantı kaldırılsın mı?", "Bu bağlantının API anahtarı da sistem şifre kasasından silinir.", "Kaldır", true)) return;
        await view.request(`/api/agents/connections/${original.id}`, "DELETE");
        view.connections = view.connections.filter((item) => item.id !== original.id);
        if (view.alive) renderConnections(view);
      }), "danger"); controls.append(remove);
      if (original.has_key) {
        const removeKey = action("Kayıtlı anahtarı sil", () => view.busy(removeKey, async () => {
          if (!await view.confirm("API anahtarı silinsin mi?", "Bağlantı kaydı korunur; kullanmak için yeniden anahtar girmeniz gerekir.", "Anahtarı sil", true)) return;
          await view.request(`/api/agents/connections/${original.id}/key`, "DELETE");
          original.has_key = false; key.input.value = "";
          if (view.alive) editConnection(view, original);
        }), "danger"); controls.append(removeKey);
      }
    }
    form.addEventListener("submit", (event) => {
      event.preventDefault(); view.busy(save, async () => {
        const body = { name: name.input.value.trim(), provider: provider.input.value, model: model.input.value.trim(),
          base_url: isCloud(provider.input.value) || provider.input.value === "shared" ? null : address.input.value.trim() || null };
        const saved = await view.request(original ? `/api/agents/connections/${original.id}` : "/api/agents/connections", original ? "PUT" : "POST", body);
        original = saved;
        provider.input.disabled = true;
        view.connections = [...view.connections.filter((item) => item.id !== saved.id), saved];
        const secret = key.input.disabled ? "" : key.input.value;
        key.input.value = "";
        if (secret) {
          await view.request(`/api/agents/connections/${saved.id}/key`, "PUT", { key: secret });
          saved.has_key = true;
        }
        view.connections = [...view.connections.filter((item) => item.id !== saved.id), saved];
        if (view.alive) { view.options.toast("Model bağlantısı kaydedildi."); renderConnections(view); }
      });
    });
    form.append(name.wrapper, provider.wrapper, model.wrapper, address.wrapper, key.wrapper, notice, controls);
    view.pane.replaceChildren(form); name.input.focus();
  }

  function schedulePoll(view, delay = 2000) {
    clearTimeout(view.timer);
    // Extensions own their lightweight status polling. Other built-in forms do not use run history.
    if (!view.alive || document.hidden || view.tab !== "runs") return;
    view.timer = setTimeout(() => poll(view), delay);
  }
  async function poll(view) {
    if (!view.alive || document.hidden || view.polling || view.tab !== "runs") return;
    view.polling = true;
    try {
      const runs = await view.request("/api/agents/runs");
      if (!view.alive) return;
      view.pollErrorShown = false;
      view.runs = runs;
      if (view.tab === "runs") {
        updateRunsList(view);
        const selected = runs.find((item) => item.id === view.selectedRun);
        if (selected) updateRun(view, selected);
      }
    } catch (error) {
      if (view.alive && !view.pollErrorShown) { view.pollErrorShown = true; view.error(error); }
    } finally {
      view.polling = false;
      schedulePoll(view);
    }
  }

  window.RpaAgents = Object.freeze({ mount, unmount,
    registerTab(definition) {
      if (!definition || !/^[a-z][a-z0-9_-]*$/.test(definition.id) || typeof definition.mount !== "function"
          || ["agents", "runs", "connections"].includes(definition.id)) throw new Error("Ajan sekmesi geçersiz.");
      extensions.set(definition.id, definition);
    },
    openRun(identity) { if (active) return openRun(active, identity); },
  });
})();
