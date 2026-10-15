"use strict";

(() => {
  const statuses = { queued: "Sırada", running: "Çalışıyor", waiting_user: "Yanıt bekliyor",
    waiting_approval: "Onay bekliyor", succeeded: "Tamamlandı", failed: "Hata", cancelled: "Durduruldu" };
  const terminal = new Set(["succeeded", "failed", "cancelled"]);
  const providers = { shared: "Kurum sunucusu", ollama: "Ollama · bu bilgisayar", local_openai: "Yerel OpenAI uyumlu sunucu",
    openai: "OpenAI", gemini: "Google Gemini", anthropic: "Anthropic Claude" };
  // Yalnız öneridir; model adı serbesttir ve sağlayıcıda gerçekten bulunan, araç çağırabilen model seçilmelidir.
  const suggestedModels = {
    gemini: [
      ["gemini-3.8-flash", "gemini-3.8-flash · Önerilen"],
      ["gemini-flash-latest", "gemini-flash-latest · Her zaman en güncel Flash"],
      ["gemini-pro-latest", "gemini-pro-latest · Daha güçlü akıl yürütme"],
      ["gemini-3.5-flash-lite", "gemini-3.5-flash-lite · Hafif ve ekonomik"],
    ],
    ollama: [
      ["qwen3:8b", "qwen3:8b · Önerilen yerel model"],
      ["llama3.1", "llama3.1 · 8B yerel model"],
      ["llama3.2", "llama3.2 · 3B hızlı yerel model"],
      ["qwen2.5:7b", "qwen2.5:7b · Çok dilli model"],
    ],
    openai: [
      ["gpt-5.6-sol", "gpt-5.6-sol · Önerilen"],
      ["gpt-5.6-terra", "gpt-5.6-terra"],
      ["gpt-5.6-luna", "gpt-5.6-luna"],
    ],
    anthropic: [
      ["claude-sonnet-5-5", "claude-sonnet-5-5 · Önerilen"],
      ["claude-haiku-4-5", "claude-haiku-4-5 · Hızlı ve ekonomik"],
      ["claude-opus-5-5", "claude-opus-5-5 · En güçlü"],
    ],
    local_openai: [
      ["default", "default · Yerel varsayılan"],
      ["local-model", "local-model"],
    ],
    // Kurum sunucusundaki model adı kuruluma göre değişir; tahmini ad önerilmez.
    shared: [],
  };
  const defaultLimits = { max_turns: 20, max_workflow_runs: 10, max_seconds: 1800, max_tokens: 50000,
    max_retries: 1, max_tasks: 20, busy_wait_seconds: 60, approval_timeout_seconds: 900, question_timeout_seconds: 900 };
  const limitLabels = { max_turns: "Karar adımı", max_workflow_runs: "Akış çalıştırma",
    max_seconds: "Görevin en uzun süresi (dakika)", max_tokens: "Token bütçesi", max_retries: "Hatalı akışı yeniden deneme",
    max_tasks: "Alt görev (yönetici ekibi)", busy_wait_seconds: "Masaüstü boşalana kadar bekleme (dakika)",
    approval_timeout_seconds: "Onay için bekleme (dakika)", question_timeout_seconds: "Yanıt için bekleme (dakika)" };
  const limitHelp = {
    max_turns: "Ajanın modele danışıp karar verdiği adım sayısı. Dolunca görev durur.",
    max_workflow_runs: "Bir görevde başlatabileceği akış sayısı.",
    max_seconds: "Görev bu süreyi aşarsa durdurulur.",
    max_tokens: "Model kullanımının üst sınırı; bulut sağlayıcıda maliyeti sınırlar.",
    max_retries: "Hata veren akışın aynı görevde tekrar denenme sayısı. Hedef bulunamazsa körlemesine tekrar edilmez.",
    max_tasks: "Yöneticinin bir görevde dağıtabileceği alt görev sayısı.",
    busy_wait_seconds: "Bilgisayarda başka bir akış çalışıyorsa bu kadar bekler.",
    approval_timeout_seconds: "Onay bu sürede gelmezse işlem başlatılmaz.",
    question_timeout_seconds: "Soru bu sürede yanıtlanmazsa ajan tahminle devam etmez.",
  };
  const minuteLimits = new Set(["max_seconds", "busy_wait_seconds", "approval_timeout_seconds", "question_timeout_seconds"]);
  const limitMax = { max_turns: 1000, max_workflow_runs: 1000, max_seconds: 86400, max_tokens: 10000000,
    max_retries: 10, max_tasks: 1000, busy_wait_seconds: 3600, approval_timeout_seconds: 86400, question_timeout_seconds: 86400 };
  const limitPresets = {
    careful: ["Temkinli", "Kısa ve sınırlı işler: az akış, kısa süre, düşük maliyet.", { max_turns: 10, max_workflow_runs: 3,
      max_seconds: 600, max_tokens: 20000, max_retries: 0, max_tasks: 5, busy_wait_seconds: 60, approval_timeout_seconds: 900, question_timeout_seconds: 900 }],
    balanced: ["Dengeli", "Çoğu günlük iş için önerilen varsayılan.", defaultLimits],
    wide: ["Geniş", "Uzun, çok adımlı işler. Bulut modelde maliyeti izleyin.", { max_turns: 60, max_workflow_runs: 30,
      max_seconds: 7200, max_tokens: 200000, max_retries: 2, max_tasks: 50, busy_wait_seconds: 300, approval_timeout_seconds: 3600, question_timeout_seconds: 3600 }],
  };
  const toolTitles = { run_workflow: "Akış çalıştırma isteği", describe_workflow: "Akış inceleniyor", list_workflows: "İzinli akışlar okunuyor",
    get_run: "Akış sonucu okunuyor", list_recent_runs: "Geçmiş çalışmalar okunuyor", read_artifact: "Çıktı dosyası okunuyor",
    ask_user: "Size soru", ask_manager: "Yöneticiye soru", finish: "Görevi bitiriyor", list_team: "Ekip okunuyor",
    delegate_task: "Görev devri", get_task: "Alt görev durumu okunuyor", list_tasks: "Alt görevler okunuyor",
    wait_tasks: "Alt görevler bekleniyor", answer_department: "Departmana yanıt", suggest_note: "Not önerisi" };
  const eventTitles = { created: "Görev alındı", queue: "Masaüstü sırası bekleniyor", workflow_started: "Akış başladı",
    question: "Size soru soruldu", user_answer: "Yanıtınız iletildi", approval_requested: "Onay istendi",
    approval_decision: "Onay kararı verildi", approval_submitted: "Onay kararı gönderildi", approval_consumed: "Onay kullanıldı",
    approval_expired: "Onay süresi doldu", task_delegated: "Görev devredildi", manager_question: "Yöneticiye soru soruldu",
    manager_answer: "Yöneticiden yanıt geldi", manager_question_expired: "Yönetici süre içinde yanıt vermedi",
    department_question: "Departmandan soru geldi", department_answered: "Departmana yanıt verildi",
    context_compacted: "Konuşma kısaltıldı", output_limited: "Yanıt bütçesi daraltıldı", interrupted: "Çalışma yarıda kaldı",
    assistant: "Ajanın notu", tool_result: "Araç sonucu", provider_request: "Modele gönderilen istek",
    note_suggested: "Ajan kalıcı not önerdi" };
  const technicalEvents = new Set(["provider_request", "tool_result", "context_compacted", "output_limited"]);
  const quietTools = new Set(["list_workflows", "describe_workflow", "get_run", "list_recent_runs", "list_team", "get_task",
    "list_tasks", "wait_tasks", "read_artifact", "suggest_note"]);
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

  function noteText(value) { return String(value || "").split(/\s+/).filter(Boolean).join(" "); }
  async function reloadNotes(view) {
    const notes = await view.request("/api/agents/notes");
    if (view.alive) view.notes = notes;
  }
  async function saveNote(view, agentId, text, sourceRun = null) {
    await view.request(`/api/agents/${agentId}/notes`, "POST", { text: noteText(text).slice(0, 500), source_run_id: sourceRun });
    await reloadNotes(view);
    if (view.alive) view.options.toast("Not kaydedildi. Ajan bunu sonraki görevlerde kullanır.");
  }
  // Notes are approved knowledge. They never widen what the agent may run; the editor only shows them.
  function notesSection(view, agent) {
    const notes = view.notes?.[agent.id] || [];
    const body = element("div", null, "agent-notes");
    body.append(element("p", "Ajan bu bilgileri sonraki görevlerde kullanır. Notlar izin vermez; izinleri yalnız ajan formu belirler.", "agent-help"));
    const list = element("ul", null, "agent-note-list");
    for (const note of notes) {
      const item = element("li");
      item.append(element("span", note.text), element("small", `${note.user_name || "Yetkili"} · ${timeLabel(note.updated_at)}`, "muted"));
      if (view.session.can_manage) {
        const controls = element("div", null, "agent-actions");
        const remove = action("Sil", () => view.busy(remove, async () => {
          if (!await view.confirm("Not silinsin mi?", "Ajan bu bilgiyi sonraki görevlerde kullanmaz.", "Sil", true)) return;
          await view.request(`/api/agents/${agent.id}/notes/${note.id}`, "DELETE");
          await reloadNotes(view); view.openNotes = agent.id; if (view.alive && view.tab === "agents") renderAgents(view);
        }), "danger");
        controls.append(action("Düzenle", () => noteForm(view, agent, note, item)), remove);
        item.append(controls);
      }
      list.append(item);
    }
    if (!notes.length) list.append(element("li", "Henüz not yok. Bir soruyu yanıtlarken veya ajanın önerisinden not kaydedebilirsiniz.", "agent-help"));
    body.append(list);
    if (view.session.can_manage) {
      const add = action("Not ekle", () => noteForm(view, agent, null, add));
      body.append(add);
    }
    const details = disclosure(`Bildikleri (${notes.length} not)`, body);
    details.open = view.openNotes === agent.id;
    return details;
  }
  function noteForm(view, agent, note, anchor) {
    const form = identify(element("form", null, "agent-note-form"), "note");
    const textInput = field(note ? "Notu düzenle" : "Yeni not", note?.text || "", "textarea",
      "Kalıcı bilgiyi yazın (en fazla 500 karakter). Tarih, tutar gibi tek seferlik değerleri ve şifreleri yazmayın.");
    textInput.input.maxLength = 500; textInput.input.required = true; textInput.input.rows = 3;
    const save = action("Notu kaydet", () => form.requestSubmit(), "primary");
    const controls = element("div", null, "agent-actions");
    controls.append(save, action("Vazgeç", () => { form.remove(); anchor.hidden = false; }));
    form.append(textInput.wrapper, controls);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      view.busy(save, async () => {
        if (note) await view.request(`/api/agents/${agent.id}/notes/${note.id}`, "PUT", { text: noteText(textInput.input.value) });
        else await view.request(`/api/agents/${agent.id}/notes`, "POST", { text: noteText(textInput.input.value) });
        await reloadNotes(view); view.openNotes = agent.id;
        if (view.alive) { view.options.toast("Not kaydedildi."); if (view.tab === "agents") renderAgents(view); }
      });
    });
    anchor.hidden = true; anchor.after(form); textInput.input.focus();
  }
  function agentName(view, identity) {
    return view.agents.find((item) => item.id === identity)?.name || "Ajan";
  }
  function workflowName(view, identity) {
    return view.workflows.find((item) => item.id === identity)?.name || "İzinli akış";
  }
  function text(value) {
    if (value === null || value === undefined) return "";
    return typeof value === "string" ? value : JSON.stringify(value);
  }

  function unmount() {
    if (!active) return;
    active.alive = false;
    clearTimeout(active.timer);
    clearTimeout(active.attentionTimer);
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
      clearTimeout(view.attentionTimer);
      if (!document.hidden && view.alive) { schedulePoll(view, 0); pollAttention(view); }
    };
    document.addEventListener("visibilitychange", view.visibility);
    try {
      const values = await Promise.all([
        request("/api/agents/session"), request("/api/agents"), request("/api/agents/connections"),
        request("/api/agents/workflows"), request("/api/agents/notes").catch(() => ({})),
      ]);
      if (!view.alive) return;
      [view.session, view.agents, view.connections, view.workflows, view.notes] = values;
      shell(view);
      showTab(view, view.tabButtons.has(options.initialTab) ? options.initialTab : "agents");
      pollAttention(view);
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
    view.attention = element("section", null, "agent-attention");
    view.attention.hidden = true; view.attention.setAttribute("aria-label", "Sizi bekleyen işler");
    view.container.replaceChildren(header, tabs, view.attention, view.pane);
  }

  // A light status read keeps questions and approvals visible from every tab; it never loads run history.
  async function pollAttention(view) {
    clearTimeout(view.attentionTimer);
    // The banner exists only after the page shell loaded; a failed first load has nothing to update.
    if (!view.alive || !view.attention || document.hidden || view.attentionLoading) return;
    view.attentionLoading = true;
    try {
      const data = await view.request("/api/agents/office");
      if (view.alive) renderAttention(view, Array.isArray(data?.agents) ? data.agents : []);
    } catch {
      if (view.alive) renderAttention(view, []);
    } finally {
      view.attentionLoading = false;
      if (view.alive && !document.hidden) view.attentionTimer = setTimeout(() => pollAttention(view), 5000);
    }
  }
  function renderAttention(view, agents) {
    const waiting = agents.filter((item) => ["waiting_user", "waiting_approval"].includes(item.status)
      && typeof item.run_id === "string" && /^[a-f0-9]{32}$/.test(item.run_id)).slice(0, 6);
    const key = JSON.stringify(waiting.map((item) => [item.run_id, item.status, item.name]));
    if (key === view.attentionKey) return;
    view.attentionKey = key;
    view.attention.hidden = !waiting.length;
    if (!waiting.length) { view.attention.replaceChildren(); return; }
    const list = element("div", null, "agent-actions");
    for (const item of waiting) {
      list.append(action(`${item.name}: ${item.status === "waiting_user" ? "yanıtınızı bekliyor" : "onay bekliyor"}`,
        () => openRun(view, item.run_id)));
    }
    view.attention.replaceChildren(element("strong", waiting.length === 1 ? "Sizi bekleyen bir iş var" : `Sizi bekleyen ${waiting.length} iş var`),
      element("p", "Yanıt veya onay gelene kadar ajan bekler; süre dolarsa tahminle devam etmez.", "agent-help"), list);
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
        agents: view.agents, connections: view.connections, workflows: view.workflows,
        openAgentRun: (identity) => openRun(view, identity),
        openTab: (name) => { if (view.tabButtons.has(name)) showTab(view, name); } });
      if (typeof result === "function") view.extensionCleanup = result;
      else if (result?.then) result.then((cleanup) => {
        if (!view.alive || view.tab !== tab) cleanup?.();
        else view.extensionCleanup = cleanup;
      }).catch(view.error);
    }
    schedulePoll(view, 0);
  }

  function duration(seconds) {
    const value = Math.max(0, Math.round(Number(seconds) || 0));
    if (value < 60) return `${value} sn`;
    const hours = Math.floor(value / 3600), minutes = Math.round((value % 3600) / 60);
    return hours ? `${hours} sa${minutes ? ` ${minutes} dk` : ""}` : `${minutes} dk`;
  }
  function count(value) { return Number(value || 0).toLocaleString("tr-TR"); }
  function limitSummary(agent) {
    const limits = { ...defaultLimits, ...(agent.limits || {}) };
    const scope = agent.role === "manager"
      ? `Ekip bütçesi (departmanlar dahil): en fazla ${count(limits.max_tasks)} alt görev, `
      : "Her görevde en fazla ";
    return `${scope}${count(limits.max_workflow_runs)} akış çalıştırma, ${count(limits.max_turns)} karar adımı, `
      + `${duration(limits.max_seconds)} ve ${count(limits.max_tokens)} token. Yanıt için ${duration(limits.question_timeout_seconds)}, `
      + `onay için ${duration(limits.approval_timeout_seconds)} bekler; süre dolunca tahminle devam etmez.`;
  }
  // Kart, ajanın kayıtlı izinlerinden üretilir; elle yazılmış bir vaat göstermez.
  function permissionSummary(view, agent) {
    const can = [], approval = [], cannot = [];
    const rules = [
      "Serbest web araması yapamaz; web ve veritabanına yalnız izinli akışlarla erişir.",
      "Bilgisayarda komut çalıştıramaz; fare ve klavyeyi akış dışında kullanamaz.",
      "Kayıtlı şifreleri ve API anahtarlarını göremez.",
      "Hedef bulunamazsa tahminle tıklamaz veya yazmaz; durur.",
      "Bilmediği bilgiyi uydurmaz; sorar ya da durur.",
    ];
    const noteCount = (view.notes?.[agent.id] || []).length;
    if (noteCount) can.push(`Onaylanmış ${noteCount} kalıcı notu bilir ve kullanır; notlar izin vermez.`);
    if (agent.role === "manager") {
      const team = view.agents.filter((item) => item.manager_id && item.manager_id === agent.id);
      if (team.length) can.push(`Bağlı ${team.length} departman ajanına görev verebilir: ${team.map((item) => `${item.name} (${item.department})`).join(", ")}.`);
      else cannot.push("Henüz bağlı departman ajanı yok; görev dağıtamaz. Departman ajanını düzenleyip bu yöneticiyi seçin.");
      can.push("Bir departmanın sonucunu başka bir departmana girdi olarak aktarabilir.",
        "Departman ajanlarının sorularını yanıtlar; bilmediği konuyu size sorar.",
        "Departman sonuçlarını birleştirip size tek bir özet sunar.");
      approval.push("Kendisi onay veremez; departmanların riskli akışları kurum onaycısına gider.");
      cannot.push("Akış çalıştıramaz; işi yalnız departman ajanları yapar.",
        "Departman ajanlarının akış izinlerini genişletemez.",
        "Kendisine bağlı olmayan ajanlara görev veremez.");
      return { can, approval, cannot, rules };
    }
    for (const grant of agent.workflows || []) {
      const identity = typeof grant === "string" ? grant : grant.workflow_id;
      const flow = view.workflows.find((item) => item.id === identity);
      const name = `«${flow?.name || "Bulunamayan akış"}»`;
      if (!flow) cannot.push(`${name} artık bulunamıyor; ajan bu izni kullanamaz.`);
      else if (flow.agent_supported === false) cannot.push(`${name} ajanla çalıştırılamaz: ${flow.blocked_reason || "desteklenmeyen adım içeriyor."}`);
      else if (flow.risk === "geri_alinamaz" && !grant.allow_without_approval) approval.push(`${name} akışını çalıştırmadan önce onay ister.`);
      else if (flow.risk === "geri_alinamaz") can.push(`${name} akışını onaysız çalıştırabilir (onay yetkilisi izin verdi).`);
      else can.push(`${name} akışını çalıştırabilir (okuma / analiz).`);
      const roots = grant.allowed_roots || [];
      if (flow && roots.length) can.push(`${name} dosyalara yalnız şu klasörlerde erişir: ${roots.join(", ")}.`);
    }
    if (!(agent.workflows || []).length) cannot.push("Henüz akış izni yok; görev verilse bile iş yapamaz.");
    else can.push("İzinli akışların ürettiği CSV, JSON ve metin çıktılarını okuyup yorumlayabilir.");
    const manager = view.agents.find((item) => item.id === agent.manager_id);
    can.push(manager ? `Takıldığında önce yöneticisi ${manager.name} ajanına, gerekirse size sorar.` : "Takıldığında size sorar.");
    cannot.push("İzin verilmeyen akışları çalıştıramaz.",
      manager ? "Diğer departman ajanlarıyla doğrudan konuşamaz; yalnız yöneticisi üzerinden iletişim kurar."
        : "Bir yöneticiye bağlı değil; diğer ajanlarla iletişim kurmaz.");
    return { can, approval, cannot, rules };
  }
  function permissionCard(summary) {
    const section = element("section", null, "agent-permissions");
    section.setAttribute("aria-label", "Yetki özeti");
    for (const [kind, title, items, none] of [
      ["can", "Yapabilir", summary.can, "Şu an yapabileceği bir iş yok."],
      ["approval", "Onay ister", summary.approval, "Onay gerektiren izni yok."],
      ["cannot", "Yapamaz", summary.cannot, ""],
    ]) {
      const column = element("div", null, "agent-permission-column");
      column.dataset.kind = kind;
      const list = element("ul");
      for (const text of items) list.append(element("li", text));
      column.append(element("h4", title), items.length ? list : element("p", none, "agent-help"));
      if (kind === "cannot" && summary.rules?.length) {
        const rules = element("ul");
        for (const text of summary.rules) rules.append(element("li", text));
        column.append(disclosure(`Her ajan için geçerli ${summary.rules.length} güvenlik kuralı`, rules));
      }
      section.append(column);
    }
    return section;
  }

  function renderAgents(view) {
    const toolbar = element("div", null, "agent-toolbar");
    toolbar.append(element("p", `${view.agents.length} ajan`, "muted"));
    if (view.session.can_manage) toolbar.append(action("Ajan ekle", () => editAgent(view), "primary"));
    const cards = element("div", null, "agent-cards");
    for (const agent of view.agents) {
      const card = element("article", null, "agent-card");
      card.append(
        element("span", agent.role === "manager" ? "Yönetici ajan" : agent.department, "agent-eyebrow"),
        element("h2", agent.name),
        element("p", agent.description || "Henüz açıklama eklenmedi.", "muted")
      );
      card.append(permissionCard(permissionSummary(view, agent)), element("p", limitSummary(agent), "agent-help agent-limit-line"));
      card.append(notesSection(view, agent));
      if (agent.instructions) card.append(disclosure("Talimatlar", element("p", agent.instructions, "agent-help agent-instructions")));

      const buttons = element("div", null, "agent-actions");
      buttons.append(action("Görev ver", () => runForm(view, agent), "primary"));
      if (view.session.can_manage) buttons.append(action("Düzenle", () => editAgent(view, agent)));
      buttons.append(action("Çalışmaları gör", () => { view.filterAgent = agent.id; showTab(view, "runs"); }));
      card.append(buttons);
      cards.append(card);
    }
    if (!view.agents.length) cards.append(empty("İlk ajanınızı oluşturun", "Önce bir model bağlantısı ekleyin, sonra ajanın kullanabileceği akışları seçin."));
    view.pane.replaceChildren(toolbar, ...gettingStarted(view), cards);
  }
  function gettingStarted(view) {
    const departments = view.agents.filter((item) => item.role === "department");
    const manager = view.agents.find((item) => item.role === "manager");
    const steps = [
      ["Model bağlantısı ekleyin", "Yerel (Ollama) veya bulut sağlayıcı seçin.", view.connections.length > 0,
        view.session.can_manage ? ["Bağlantılar", () => showTab(view, "connections")] : null],
      ["Departman ajanı oluşturun ve akış izni verin", "Ajan yalnız seçtiğiniz akışları çalıştırır.",
        departments.some((item) => (item.workflows || []).length), view.session.can_manage ? ["Ajan ekle", () => editAgent(view)] : null],
      ["İsterseniz yönetici ajan ekleyin", "Yönetici tek görevi departmanlara dağıtır, sorularını yanıtlar ve sonuçları birleştirir.",
        Boolean(manager) && departments.some((item) => item.manager_id === manager.id), null],
    ];
    const result = [];
    if (steps.slice(0, 2).some(([, , done]) => !done)) {
      const card = element("section", null, "agent-start");
      card.setAttribute("aria-label", "Başlarken");
      const list = element("ol", null, "agent-start-steps");
      for (const [title, help, done, button] of steps) {
        const item = element("li", null, done ? "done" : "");
        item.append(element("strong", `${done ? "✓ " : ""}${title}`), element("p", help, "agent-help"));
        if (!done && button) item.append(action(button[0], button[1]));
        list.append(item);
      }
      card.append(element("h2", "Başlarken"), list,
        element("p", "Hazır olduğunuzda ajan kartındaki Görev ver ile başlayın. Riskli işlemler her zaman onay ister.", "agent-help"));
      result.push(card);
    }
    const flow = element("ol", null, "agent-flow");
    for (const [title, help] of [
      ["Görev verirsiniz", "Hedefi düz bir cümleyle yazın."],
      ["Ajan izinli akışları çalıştırır", "Yalnız sizin seçtiğiniz akışlar; başka araç yoktur."],
      ["Riskli işte onay ister", "Geri alınamaz işlem onaysız başlamaz."],
      ["Takılınca sorar", "Önce yöneticisine, gerekirse size. Tahmin yürütmez."],
      ["Sonucu teslim eder", "Özet ve yapılandırılmış sonuç Çalışmalar sekmesinde."],
    ]) {
      const item = element("li"); item.append(element("strong", title), element("span", help, "agent-help")); flow.append(item);
    }
    result.push(disclosure("Ajanlar nasıl çalışır?", flow));
    return result;
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
    const model = field("Model adı", agent.model, "text", "Aşağıdaki güncel modellerden seçebilir veya kendi model adınızı yazabilirsiniz.");
    model.input.required = true; model.input.maxLength = 200;
    const modelList = identify(element("datalist"), "agent-models");
    model.input.setAttribute("list", modelList.id);
    const modelChips = element("div", null, "agent-chips");
    model.wrapper.append(modelList, modelChips);
    function updateAgentModelSuggestions() {
      const selectedConn = view.connections.find((item) => item.id === connection.input.value);
      const providerKey = selectedConn?.provider || "";
      const suggestions = suggestedModels[providerKey] || [];
      modelList.replaceChildren();
      modelChips.replaceChildren();
      const allChoices = [];
      if (selectedConn?.model && !suggestions.some(([val]) => val === selectedConn.model)) {
        allChoices.push([selectedConn.model, `${selectedConn.model} (Bağlantı varsayılanı)`]);
      }
      allChoices.push(...suggestions);
      for (const [val, label] of allChoices) {
        const opt = element("option"); opt.value = val; opt.textContent = label;
        modelList.append(opt);
        const chip = identify(element("button", val, "agent-chip"), "model-chip");
        chip.type = "button"; chip.title = label;
        chip.addEventListener("click", () => {
          model.input.value = val;
          model.input.focus();
        });
        modelChips.append(chip);
      }
    }
    updateAgentModelSuggestions();
    connection.input.addEventListener("change", () => {
      const selected = view.connections.find((item) => item.id === connection.input.value);
      updateAgentModelSuggestions();
      if (selected?.model) model.input.value = selected.model;
      else if (!model.input.value.trim() && suggestedModels[selected?.provider]?.length) {
        model.input.value = suggestedModels[selected.provider][0][0];
      }
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
    const limits = element("div", null, "agent-limits");
    const limitGrid = element("div", null, "agent-form-grid");
    const limitFields = {};
    const preset = select("Sınır profili", [...Object.entries(limitPresets).map(([key, [label]]) => [key, label]), ["custom", "Özel"]], "custom");
    const presetHelp = element("p", "", "agent-help");
    for (const [key, initial] of Object.entries(defaultLimits)) {
      const stored = agent.limits?.[key] ?? initial;
      const minutes = minuteLimits.has(key);
      const item = field(limitLabels[key], minutes ? Math.round(stored / 60 * 100) / 100 : stored, "number", limitHelp[key]);
      item.input.min = ["max_retries", "max_workflow_runs", "busy_wait_seconds"].includes(key) ? "0" : minutes ? "0.1" : "1";
      item.input.max = String(minutes ? limitMax[key] / 60 : limitMax[key]); item.input.step = minutes ? "any" : "1";
      item.input.required = true;
      limitGrid.append(item.wrapper); limitFields[key] = item.input;
    }
    const readLimits = () => Object.fromEntries(Object.entries(limitFields).map(([key, input]) =>
      [key, minuteLimits.has(key) ? Math.round(Number(input.value) * 60) : Number(input.value)]));
    const matchPreset = () => {
      const current = readLimits();
      const found = Object.entries(limitPresets).find(([, [, , values]]) => Object.keys(defaultLimits).every((key) => values[key] === current[key]));
      preset.input.value = found ? found[0] : "custom";
      presetHelp.textContent = found ? found[1][1] : "Değerleri kendiniz belirlediniz.";
    };
    preset.input.addEventListener("change", () => {
      const values = limitPresets[preset.input.value]?.[2];
      if (values) for (const [key, input] of Object.entries(limitFields)) input.value = minuteLimits.has(key) ? values[key] / 60 : values[key];
      matchPreset();
    });
    limitGrid.addEventListener("input", matchPreset);
    preset.wrapper.append(presetHelp);
    limits.append(preset.wrapper, limitGrid);
    matchPreset();
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
    const preview = element("section", null, "agent-preview");
    const previewBody = element("div");
    preview.append(element("h3", "Bu ajan ne yapabilir?"),
      element("p", "Özet, formdaki seçimlerinize göre anında güncellenir. Kaydetmeden önce kontrol edin.", "agent-help"), previewBody);
    const draft = () => ({ ...agent, name: name.input.value.trim() || "Bu ajan", role: role.input.value,
      department: department.input.value.trim(), manager_id: role.input.value === "manager" ? null : manager.input.value || null,
      workflows: role.input.value === "manager" ? [] : grantRows.filter((item) => item.allowed.input.checked).map((item) => ({
        workflow_id: item.workflow.id, allow_without_approval: item.automatic.input.checked,
        allowed_roots: item.roots.input.value.split("\n").map((line) => line.trim()).filter(Boolean),
        allowed_hosts: item.grant?.allowed_hosts || [],
      })), limits: readLimits() });
    const refreshPreview = () => {
      const current = draft();
      previewBody.replaceChildren(permissionCard(permissionSummary(view, current)), element("p", limitSummary(current), "agent-help agent-limit-line"));
    };
    form.addEventListener("input", refreshPreview);
    form.addEventListener("change", refreshPreview);
    refreshPreview();
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      view.busy(save, async () => {
        const { workflows, limits: chosenLimits } = draft();
        const body = { name: name.input.value.trim(), description: description.input.value, instructions: instructions.input.value,
          department: department.input.value.trim(), role: role.input.value,
          manager_id: role.input.value === "manager" ? null : manager.input.value || null,
          provider_connection_id: connection.input.value || null, model: model.input.value.trim(),
          workflows, limits: chosenLimits };
        const saved = await view.request(original ? `/api/agents/${original.id}` : "/api/agents", original ? "PUT" : "POST", body);
        view.agents = [...view.agents.filter((item) => item.id !== saved.id), saved];
        if (view.alive) { view.options.toast("Ajan kaydedildi."); renderAgents(view); }
      });
    });
    form.append(heading, grid, cloudWarning, description.wrapper, instructions.wrapper, grants,
      disclosure("Çalışma sınırları", limits), preview, buttons);
    view.pane.replaceChildren(form);
    name.input.focus();
  }

  function runForm(view, agent) {
    const form = identify(element("form", null, "agent-form"), "task");
    form.append(element("h2", `${agent.name} için görev`));
    const task = field("Hedefiniz", "", "textarea", "Beklediğiniz sonucu yazın. Ajan yalnız izin verdiğiniz akışları kullanır.");
    task.input.required = true; task.input.maxLength = 16000; task.input.rows = 6;
    const inputs = field("Başlangıç girdileri (JSON)", "{}", "textarea", "Gerekmiyorsa boş bırakın. Örnek: {\"donem\": \"2026-09\", \"dosya\": \"rapor.csv\"}");
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
    const scope = disclosure("Bu ajan neler yapabilir?", permissionCard(permissionSummary(view, agent)));
    scope.open = true;
    const hint = element("p", agent.role === "manager"
      ? "Yönetici işi bağlı departmanlara dağıtır. Hedefi bütün olarak yazın; hangi departmanın ne yapacağını o belirler."
      : "Hedefi, ajanın izinli akışlarıyla yapılabilecek biçimde yazın. İzni olmayan işi yapmaz, size bildirir.", "agent-help");
    form.append(hint, task.wrapper, disclosure("Girdi değişkenleri (isteğe bağlı)", inputs.wrapper), scope, buttons);
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
      button.append(element("small", `${run.parent_run_id ? "↳ Alt görev · " : ""}${agentName(view, run.agent_id)}`, "agent-eyebrow"),
        element("strong", run.title || run.task?.slice(0, 100) || "Ajan görevi"), status(run.status),
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
      const owner = element("p", "", "agent-eyebrow");
      const task = element("p", run.task, "agent-task-text");
      const stats = element("p", "", "agent-help");
      const usage = element("section", null, "agent-usage"); usage.setAttribute("aria-label", "Sınırların kullanımı");
      const team = element("section", null, "agent-team-links");
      const waiting = element("p", "", "agent-notice"); waiting.hidden = true;
      const pending = element("div");
      const technical = toggle("Teknik kayıtları göster", Boolean(view.showTechnical));
      const timeline = element("ol", null, "agent-timeline"); timeline.setAttribute("aria-label", "Çalışma zaman çizelgesi");
      timeline.classList.toggle("show-technical", Boolean(view.showTechnical));
      technical.input.addEventListener("change", () => {
        view.showTechnical = technical.input.checked; timeline.classList.toggle("show-technical", view.showTechnical);
      });
      const timelineHead = element("div", null, "agent-toolbar");
      timelineHead.append(element("h3", "Zaman çizelgesi"), technical.wrapper);
      const result = element("section", null, "agent-run-result");
      view.runPane.replaceChildren(header, owner, task, stats, usage, team, waiting, pending, result, timelineHead, timeline);
      view.runView = { id: run.id, title, owner, task, stop, statusBox, stats, usage, team, teamKey: null, waiting, pending, pendingKey: null,
        questionId: null, answerInput: null, timeline, events: new Map(), result, resultKey: null };
    }
    const ui = view.runView;
    ui.title.textContent = run.title || "Ajan çalışması";
    ui.task.textContent = run.task || "";
    ui.statusBox.replaceChildren(status(run.status));
    ui.stop.hidden = terminal.has(run.status);
    const runner = view.agents.find((item) => item.id === run.agent_id);
    ui.owner.textContent = runner ? `${runner.name} · ${runner.role === "manager" ? "Yönetici ajan" : runner.department}` : "Kaldırılmış ajan";
    ui.stats.textContent = `Başlangıç: ${timeLabel(run.started_at)}${run.finished_at ? ` · Bitiş: ${timeLabel(run.finished_at)}` : ""}`;
    updateUsage(ui.usage, run, runner);
    updateTeam(view, run, ui);
    const asked = [...(run.events || [])].reverse().find((event) => ["manager_question", "manager_answer", "manager_question_expired"].includes(event.kind));
    ui.waiting.hidden = terminal.has(run.status) || asked?.kind !== "manager_question";
    ui.waiting.textContent = ui.waiting.hidden ? "" : "Ajan yöneticisine soru sordu ve yanıtını bekliyor. Yönetici bilmiyorsa soruyu size iletir.";
    updatePending(view, run, ui);
    const visibleEvents = new Set();
    for (const event of run.events || []) {
      visibleEvents.add(event.id);
      const signature = JSON.stringify([event.kind, event.message, event.timestamp, event.data]);
      const previous = ui.events.get(event.id);
      if (previous?.signature === signature) continue;
      const item = element("li", null, `agent-event${isTechnical(event) ? " technical" : ""}`);
      item.dataset.kind = event.kind;
      const detail = eventDetail(view, event);
      item.append(element("small", timeLabel(event.timestamp), "muted"), element("strong", eventTitle(event)));
      // The server sentence only repeats the title when a readable detail exists; the model's own note is always shown.
      if (!detail || event.kind === "assistant") item.append(element("p", event.message || event.kind));
      if (detail) item.append(element("p", detail, "agent-task-text agent-event-detail"));
      if (event.kind === "note_suggested" && view.session.can_manage && typeof event.data?.text === "string") {
        const known = (view.notes?.[run.agent_id] || []).some((item) => item.text === noteText(event.data.text));
        if (known) item.append(element("p", "Bu bilgi ajanın notlarında kayıtlı.", "agent-help"));
        else {
          const keep = action("Not olarak sakla", () => view.busy(keep, async () => {
            await saveNote(view, run.agent_id, event.data.text, run.id);
            if (view.alive) keep.replaceWith(element("p", "Bu bilgi ajanın notlarında kayıtlı.", "agent-help"));
          }), "primary");
          item.append(keep);
        }
      }
      const runId = event.kind === "workflow_started" ? event.data?.run_id : null;
      if (typeof runId === "string" && /^[a-f0-9]{32}$/.test(runId)) {
        item.append(action("Akış çalışma kaydını aç", () => Promise.resolve(view.options.openRun(runId)).catch(view.error)));
      }
      if (event.data && Object.keys(event.data).length) item.append(disclosure("Teknik ayrıntı", jsonBlock(event.data)));
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
  function isTechnical(event) {
    return technicalEvents.has(event.kind) || (event.kind === "tool_call" && quietTools.has(event.data?.name))
      || (event.kind === "assistant" && !String(event.message || "").trim());
  }
  function eventTitle(event) {
    if (event.kind === "tool_call") return toolTitles[event.data?.name] || "Araç kullanıldı";
    if (event.kind === "approval_decision") return event.data?.approved ? "İşlem onaylandı" : "İşlem reddedildi";
    return eventTitles[event.kind] || "Kayıt";
  }
  // Event data are untrusted model or user text; they are only ever rendered with textContent.
  function eventDetail(view, event) {
    const data = event.data || {}, args = data.arguments || {};
    if (event.kind === "tool_call") {
      if (data.name === "run_workflow") return `«${workflowName(view, args.workflow_id)}»${args.reason ? ` · Gerekçe: ${text(args.reason)}` : ""}`;
      if (data.name === "delegate_task") return `${agentName(view, args.agent_id)}: ${text(args.title)}`;
      if (["ask_user", "ask_manager"].includes(data.name)) return text(args.question);
      if (data.name === "answer_department") return text(args.answer);
      if (data.name === "finish") return text(args.summary);
      return "";
    }
    if (["question", "manager_question"].includes(event.kind)) return text(data.question);
    if (["user_answer", "manager_answer", "department_answered"].includes(event.kind)) return text(data.answer);
    if (event.kind === "department_question") return `${agentName(view, data.agent_id)}: ${text(data.question)}`;
    if (event.kind === "task_delegated") return agentName(view, data.agent_id);
    if (event.kind === "workflow_started") return `«${workflowName(view, data.workflow_id)}»`;
    if (event.kind === "note_suggested") return text(data.text);
    return "";
  }
  function updateUsage(box, run, agent) {
    const limits = { ...defaultLimits, ...(agent?.limits || {}) };
    const team = agent?.role === "manager" && !run.parent_run_id ? run.team_usage || {} : null;
    const last = Date.parse(run.events?.at(-1)?.timestamp || "");
    const started = Date.parse(run.started_at || "");
    const ended = Date.parse(run.finished_at || "") || (terminal.has(run.status) && Number.isFinite(last) ? last : Date.now());
    const elapsed = Number.isFinite(started) ? Math.max(0, (ended - started) / 1000) : 0;
    const rows = [
      ["Karar adımı", team ? team.turns : run.turns, limits.max_turns, count],
      ["Akış çalıştırma", team ? team.workflow_count : run.workflow_count, limits.max_workflow_runs, count],
      ...(team ? [["Alt görev", team.task_count, limits.max_tasks, count]] : []),
      ["Süre", elapsed, limits.max_seconds, duration],
      ["Token", team ? team.total_tokens : run.total_tokens, limits.max_tokens, count],
    ];
    const items = rows.map(([label, used, limit, format]) => {
      const value = Number(used) || 0, ratio = limit > 0 ? Math.min(1, value / limit) : 0;
      const item = element("div", null, `agent-usage-item${ratio >= .8 ? " near" : ""}`);
      const bar = element("div", null, "agent-usage-bar");
      bar.setAttribute("role", "progressbar"); bar.setAttribute("aria-label", label);
      bar.setAttribute("aria-valuemin", "0"); bar.setAttribute("aria-valuemax", String(limit)); bar.setAttribute("aria-valuenow", String(Math.round(value)));
      const fill = element("span"); fill.style.width = `${Math.round(ratio * 100)}%`; bar.append(fill);
      item.append(element("span", `${label} · ${format(value)} / ${format(limit)}`), bar);
      return item;
    });
    box.replaceChildren(element("h3", team ? "Ekip bütçesi (departmanlar dahil)" : "Sınırların kullanımı"), ...items);
  }
  function updateTeam(view, run, ui) {
    const children = view.runs.filter((item) => item.parent_run_id === run.id);
    const key = JSON.stringify([run.parent_run_id, children.map((item) => [item.id, item.status, item.agent_id])]);
    if (key === ui.teamKey) return;
    ui.teamKey = key; ui.team.replaceChildren(); ui.team.hidden = !run.parent_run_id && !children.length;
    if (run.parent_run_id) ui.team.append(element("p", "Bu görevi yönetici ajan verdi.", "agent-help"),
      action("Yönetici görevini aç", () => openRun(view, run.parent_run_id)));
    if (children.length) {
      const list = element("ul", null, "agent-team-children");
      for (const child of children) {
        const item = element("li");
        item.append(action(`${agentName(view, child.agent_id)}: ${child.title || "Alt görev"}`, () => openRun(view, child.id)), status(child.status));
        list.append(item);
      }
      ui.team.append(element("h3", "Departmanlara verilen görevler"), list);
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
      const remember = toggle("Bu bilgiyi ajanın kalıcı notu olarak da sakla", false);
      const note = field("Not metni", "", "textarea", "Ajan bunu sonraki görevlerde de kullanır. Tarih, tutar gibi tek seferlik değerleri saklamayın.");
      note.input.maxLength = 500; note.input.rows = 2; note.wrapper.hidden = true;
      remember.input.addEventListener("change", () => {
        note.wrapper.hidden = !remember.input.checked; note.input.required = remember.input.checked;
        if (remember.input.checked && !note.input.value) note.input.value = noteText(`${question.question} → ${answer.input.value}`).slice(0, 500);
      });
      form.addEventListener("submit", (event) => { event.preventDefault(); view.busy(send, async () => {
        await view.request(`/api/agents/runs/${run.id}/questions/${question.id}/answer`, "POST", { answer: answer.input.value });
        if (remember.input.checked && note.input.value.trim()) await saveNote(view, run.agent_id, note.input.value, run.id);
        if (view.alive && view.selectedRun === run.id) await openRun(view, run.id);
      }); });
      form.append(answer.wrapper);
      if (view.session.can_manage) form.append(remember.wrapper, note.wrapper);
      form.append(element("p", `Yanıt süresi: ${timeLabel(question.expires_at)}`, "agent-help"), send);
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
      } else card.append(element("p", "Bu işlemi yalnız firmanın onay yetkilisi onaylayabilir. Onay gelene kadar akış başlamaz.", "agent-notice"));
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
    const model = field("Varsayılan model adı", connection.model, "text", "Aşağıdaki güncel modellerden seçebilir veya kendi model adınızı yazabilirsiniz.");
    model.input.maxLength = 200;
    const modelList = identify(element("datalist"), "conn-models");
    model.input.setAttribute("list", modelList.id);
    const modelChips = element("div", null, "agent-chips");
    model.wrapper.append(modelList, modelChips);
    function updateConnModelSuggestions() {
      const providerKey = provider.input.value || "ollama";
      const suggestions = suggestedModels[providerKey] || [];
      modelList.replaceChildren();
      modelChips.replaceChildren();
      for (const [val, label] of suggestions) {
        const opt = element("option"); opt.value = val; opt.textContent = label;
        modelList.append(opt);
        const chip = identify(element("button", val, "agent-chip"), "model-chip");
        chip.type = "button"; chip.title = label;
        chip.addEventListener("click", () => {
          model.input.value = val;
          model.input.focus();
        });
        modelChips.append(chip);
      }
    }
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
      updateConnModelSuggestions();
    };
    provider.input.addEventListener("change", () => {
      address.input.value = "";
      update();
      if (!model.input.value.trim() && suggestedModels[provider.input.value]?.length) {
        model.input.value = suggestedModels[provider.input.value][0][0];
      }
    }); update();
    if (!connection.model && !original && suggestedModels[connection.provider]?.length) {
      model.input.value = suggestedModels[connection.provider][0][0];
    }
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
