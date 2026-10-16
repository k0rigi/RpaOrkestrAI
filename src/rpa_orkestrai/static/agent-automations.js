"use strict";

// Ajan otomasyonları: zamanında, bir akış bitince veya klasöre dosya gelince ajana görev verir.
(() => {
  let sequence = 0;
  const days = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
  const statusText = { started: "Görev başlatıldı", skipped: "Atlandı", missed: "Kaçırıldı", error: "Hata" };
  const triggerInputs = {
    schedule: ["tetikleme_zamani"],
    workflow: ["tetikleyen_akis", "akis_durumu", "akis_hatasi", "akis_calisma_id"],
    folder: ["dosya_adi", "dosya_yolu"],
  };
  const el = (tag, text, css = "") => {
    const item = document.createElement(tag);
    if (text !== undefined && text !== null) item.textContent = String(text);
    if (css) item.className = css;
    return item;
  };
  const id = (item, hint = "item") => { item.id = `agent-automation-${hint}-${++sequence}`; return item; };
  function button(text, work, css = "") {
    const item = id(el("button", text, `button ${css}`), "button");
    item.type = "button";
    item.addEventListener("click", work);
    return item;
  }
  function labelled(label, control, help = "") {
    const wrapper = el("div", undefined, "agent-field");
    id(control, "field");
    const caption = el("label", label);
    caption.htmlFor = control.id;
    wrapper.append(caption, control);
    if (help) wrapper.append(el("p", help, "agent-help"));
    return wrapper;
  }
  function input(type = "text", value = "") {
    const item = el(type === "textarea" ? "textarea" : "input");
    if (type !== "textarea") item.type = type;
    item.value = value ?? "";
    return item;
  }
  function choice(options, value) {
    const item = el("select");
    for (const [key, text] of options) { const option = el("option", text); option.value = key; item.append(option); }
    item.value = value;
    return item;
  }
  function time(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
  }

  function mount(container, options) {
    const view = { alive: true, timer: null, editing: false };
    const request = (path, method = "GET", body) => options.api(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const agents = options.agents || [], workflows = options.workflows || [];
    const can = Boolean(options.session?.can_manage);
    const head = el("div", undefined, "agent-toolbar");
    head.append(el("h2", "Otomasyonlar"));
    if (can) head.append(button("Otomasyon ekle", () => edit(null), "primary"));
    const intro = el("p", "Ajana belirli zamanlarda, bir akış bittiğinde veya bir klasöre yeni dosya geldiğinde kendiliğinden görev "
      + "verin. Görev, elle verdiğiniz görevle aynı izin, onay ve sınırlarla çalışır; ajan takılırsa size sorar. Otomasyonlar "
      + "yalnız Studio açık ve oturumunuz geçerliyken çalışır.", "muted");
    const form = el("section", undefined, "agent-form agent-automation-form"); form.hidden = true;
    const list = el("div", undefined, "agent-cards");
    container.append(head, intro, form, list);

    async function act(control, work) {
      if (control.disabled) return;
      control.disabled = true;
      try { await work(); } catch (error) { if (view.alive) options.toast(error?.message || "İşlem tamamlanamadı.", true); }
      finally { control.disabled = false; }
    }
    async function confirmed(title, message) {
      if (options.confirmDialog) return options.confirmDialog(title, message, "Sil", true);
      return window.confirm(`${title}\n\n${message}`);
    }

    function card(item) {
      const article = el("article", undefined, "agent-card agent-automation-card");
      const agent = agents.find((value) => value.id === item.agent_id);
      article.dataset.enabled = String(item.enabled);
      article.append(el("span", agent ? agent.name : "Silinmiş ajan", "agent-eyebrow"), el("h3", item.name),
        el("p", item.summary, "agent-automation-when"), el("p", item.task, "agent-help agent-instructions"));
      const facts = el("ul", undefined, "agent-automation-facts");
      facts.append(el("li", item.enabled ? "Etkin" : "Kapalı"));
      if (item.trigger.kind === "schedule" && item.enabled) facts.append(el("li", `Sonraki: ${time(item.next_run_at)}`));
      if (item.last_status) facts.append(el("li", `Son: ${statusText[item.last_status] || item.last_status} · ${time(item.last_run_at)}`));
      article.append(facts);
      if (item.last_message && item.last_status !== "started") article.append(el("p", item.last_message, item.last_status === "error" ? "agent-warning" : "agent-help"));
      const actions = el("div", undefined, "agent-actions");
      if (item.last_run_id) actions.append(button("Son görevi aç", () => options.openAgentRun?.(item.last_run_id)));
      if (can) {
        const run = button("Şimdi çalıştır", () => act(run, async () => {
          const changed = await request(`/api/agents/automations/${item.id}/run`, "POST", {});
          options.toast("Görev başlatıldı.");
          if (changed.last_run_id) options.openAgentRun?.(changed.last_run_id); else await refresh();
        }));
        const toggle = button(item.enabled ? "Kapat" : "Aç", () => act(toggle, async () => {
          await request(`/api/agents/automations/${item.id}`, "PUT", { ...payload(item), enabled: !item.enabled });
          await refresh();
        }));
        const remove = button("Sil", () => act(remove, async () => {
          if (!await confirmed("Otomasyon silinsin mi?", "Bundan sonra bu otomasyon görev başlatmaz. Daha önce başlattığı görevler kalır.")) return;
          await request(`/api/agents/automations/${item.id}`, "DELETE");
          await refresh();
        }), "danger");
        actions.append(run, button("Düzenle", () => edit(item)), toggle, remove);
      }
      article.append(actions);
      return article;
    }
    function payload(item) {
      const { name, agent_id, task, inputs, enabled, trigger } = item;
      return { name, agent_id, task, inputs, enabled, trigger };
    }

    function edit(item) {
      view.editing = true;
      const current = item || { name: "", agent_id: agents[0]?.id || "", task: "", inputs: {}, enabled: true,
        trigger: { kind: "schedule", schedule_kind: "daily", time: "09:00", days: [0, 1, 2, 3, 4], every_minutes: 60,
          until: null, date: null, workflow_id: null, outcome: "any", folder: "", pattern: "*" } };
      const trigger = { kind: "schedule", schedule_kind: "daily", time: "09:00", days: [0, 1, 2, 3, 4], every_minutes: 60,
        outcome: "any", pattern: "*", ...current.trigger };
      form.hidden = false;
      form.replaceChildren(el("h3", item ? "Otomasyonu düzenle" : "Yeni otomasyon"));
      if (!agents.length) {
        form.append(el("p", "Önce Ajanlar sekmesinden bir ajan oluşturun.", "agent-warning"), button("Vazgeç", close));
        return;
      }
      const name = input("text", current.name); name.maxLength = 120; name.required = true;
      const agent = choice(agents.map((value) => [value.id, `${value.name} (${value.role === "manager" ? "Yönetici" : value.department})`]), current.agent_id);
      const task = input("textarea", current.task); task.rows = 4; task.maxLength = 16000; task.required = true;
      const kind = choice([["schedule", "Belirli zamanlarda"], ["workflow", "Bir akış bittiğinde"], ["folder", "Klasöre yeni dosya geldiğinde"]], trigger.kind);
      // Schedule
      const often = choice([["daily", "Her gün"], ["weekly", "Belirli günler"], ["interval", "Belirli aralıklarla"], ["once", "Bir kez"]], trigger.schedule_kind);
      const date = input("date", trigger.date || ""); const hour = input("time", trigger.time || "09:00");
      const every = input("number", trigger.every_minutes || 60); every.min = "5"; every.max = "1440";
      const until = input("time", trigger.until || "");
      const dayBox = el("div", undefined, "agent-automation-days");
      const dayInputs = days.map((label, index) => {
        const box = id(el("input"), "day"); box.type = "checkbox"; box.checked = (trigger.days || []).includes(index);
        const wrapper = el("label", undefined, "agent-toggle"); wrapper.htmlFor = box.id; wrapper.append(box, el("span", label));
        dayBox.append(wrapper); return box;
      });
      const scheduleFields = el("div", undefined, "agent-form-grid");
      const dateField = labelled("Tarih", date), hourField = labelled("Saat (aralıkta başlangıç)", hour),
        everyField = labelled("Kaç dakikada bir", every, "En az 5 dakika."), untilField = labelled("Bitiş saati (isteğe bağlı)", until),
        dayField = el("div", undefined, "agent-field");
      dayField.append(el("span", "Günler", "agent-days-caption"), dayBox);
      scheduleFields.append(labelled("Ne sıklıkla?", often), dateField, hourField, everyField, untilField, dayField);
      // Workflow
      const flow = choice([["", "Akış seçin"], ...workflows.map((value) => [value.id, value.name])], trigger.workflow_id || "");
      const outcome = choice([["any", "Bittiğinde (her sonuç)"], ["succeeded", "Başarıyla bittiğinde"], ["failed", "Hata verdiğinde"]], trigger.outcome);
      const workflowFields = el("div", undefined, "agent-form-grid");
      workflowFields.append(labelled("Akış", flow, "Sizin veya zamanlayıcının başlattığı çalışmalar sayılır; ajanların çalıştırdığı akışlar tetiklemez."),
        labelled("Ne zaman?", outcome));
      // Folder
      const folder = input("text", trigger.folder || ""); folder.maxLength = 2000; folder.placeholder = "/Users/ad/Belgeler/Gelen faturalar";
      const pattern = input("text", trigger.pattern || "*"); pattern.maxLength = 100;
      const folderFields = el("div", undefined, "agent-form-grid");
      folderFields.append(labelled("Klasörün tam yolu", folder, "Yalnız bu klasöre doğrudan gelen yeni dosyalar sayılır; kayıt anındaki dosyalar işlenmez."),
        labelled("Dosya deseni", pattern, "Ör. *.pdf veya fatura_*.xlsx. Geçici ve gizli dosyalar sayılmaz."));
      const given = el("p", "", "agent-notice");
      const editor = (values) => window.RpaAgents.inputsEditor(values, window.RpaAgents.expectedInputs(agents.find((value) => value.id === agent.value) || {}));
      let inputs = editor(current.inputs);
      const inputsBox = el("div");
      inputsBox.append(inputs.wrapper);
      agent.addEventListener("change", () => {
        let values = {};
        try { values = inputs.read(); } catch { values = {}; }
        inputs = editor(values); inputsBox.replaceChildren(inputs.wrapper);
      });
      const update = () => {
        const selected = kind.value;
        scheduleFields.hidden = selected !== "schedule"; workflowFields.hidden = selected !== "workflow"; folderFields.hidden = selected !== "folder";
        dateField.hidden = often.value !== "once"; everyField.hidden = untilField.hidden = often.value !== "interval";
        dayField.hidden = !["weekly", "interval"].includes(often.value);
        given.textContent = `Ajan, görevle birlikte şu girdileri de alır: ${triggerInputs[selected].join(", ")}.`
          + (selected === "folder" ? " Dosyayı okuyup işlemesi için ajanın bu klasöre izinli bir akışı olmalıdır." : "");
      };
      kind.addEventListener("change", update); often.addEventListener("change", update); update();
      const save = button("Otomasyonu kaydet", () => act(save, async () => {
        if (!name.value.trim() || !task.value.trim()) throw new Error("Ad ve görev alanlarını doldurun.");
        const body = { name: name.value.trim(), agent_id: agent.value, task: task.value.trim(), inputs: inputs.read(),
          enabled: current.enabled, trigger: { kind: kind.value, schedule_kind: often.value, date: date.value || null,
            time: hour.value || "09:00", days: dayInputs.flatMap((box, index) => (box.checked ? [index] : [])),
            every_minutes: Number(every.value) || 60, until: until.value || null, workflow_id: flow.value || null,
            outcome: outcome.value, folder: folder.value.trim() || null, pattern: pattern.value.trim() || "*" } };
        await request(item ? `/api/agents/automations/${item.id}` : "/api/agents/automations", item ? "PUT" : "POST", body);
        options.toast("Otomasyon kaydedildi.");
        close(); await refresh();
      }), "primary");
      const controls = el("div", undefined, "agent-actions");
      controls.append(save, button("Vazgeç", close));
      const grid = el("div", undefined, "agent-form-grid");
      grid.append(labelled("Otomasyon adı", name), labelled("Görevi alacak ajan", agent));
      form.append(grid, labelled("Görev", task, "Ajana her seferinde verilecek iş. Ör. «Gelen faturayı incele, uygunsa iade akışını çalıştır.»"),
        labelled("Ne zaman çalışsın?", kind), scheduleFields, workflowFields, folderFields, given);
      const details = el("details", undefined, "agent-details");
      details.append(id(el("summary", "Girdi değişkenleri (isteğe bağlı)"), "summary"), inputsBox);
      form.append(details, controls);
      name.focus();
    }
    function close() { view.editing = false; form.hidden = true; form.replaceChildren(); }

    async function refresh() {
      clearTimeout(view.timer);
      if (!view.alive) return;
      try {
        if (!document.hidden) {
          const items = await request("/api/agents/automations");
          if (!view.alive) return;
          const cards = items.map(card);
          list.replaceChildren(...(cards.length ? cards : [el("p", can
            ? "Henüz otomasyon yok. Otomasyon ekle ile başlayın: ör. her sabah 09:00'da yöneticiye günün özetini hazırlatın."
            : "Henüz otomasyon yok. Otomasyonları ajanları yönetme yetkisi olan kişi tanımlar.", "muted")]));
        }
      } catch (error) {
        if (view.alive) list.replaceChildren(el("p", error?.message || "Otomasyonlar alınamadı.", "agent-warning"));
      } finally {
        if (view.alive) view.timer = setTimeout(refresh, 10000);
      }
    }
    const visibility = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", visibility);
    refresh();
    return () => { view.alive = false; clearTimeout(view.timer); document.removeEventListener("visibilitychange", visibility); };
  }

  window.RpaAgents.registerTab({ id: "automations", label: "Otomasyonlar", mount });
})();
