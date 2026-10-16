"use strict";

// Otomasyonlar: zamanında, bir akış bitince, klasöre dosya, tabloya kayıt veya posta kutusuna e-posta gelince
// bir ajana görev verir ya da bir akışı doğrudan çalıştırır.
(() => {
  let sequence = 0;
  const days = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
  const statusText = { started: "Başlatıldı", queued: "Sırada", skipped: "Atlandı", missed: "Kaçırıldı", error: "Hata" };
  const triggerInputs = {
    schedule: "tetikleme_zamani",
    workflow: "tetikleyen_akis, akis_durumu, akis_hatasi, akis_calisma_id",
    folder: "dosya_adi, dosya_yolu",
    rows: "kayit (kaydın tüm sütunları: ${kayit.Fatura_No} gibi) ve kayit_anahtari",
    email: "eposta (${eposta.subject}, ${eposta.from}, ${eposta.text}, ${eposta.attachments})",
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
  function checkbox(label, checked) {
    const box = id(el("input"), "check");
    box.type = "checkbox";
    box.checked = Boolean(checked);
    const wrapper = el("label", undefined, "agent-toggle");
    wrapper.htmlFor = box.id;
    wrapper.append(box, el("span", label));
    return { wrapper, box };
  }
  function time(value) {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" });
  }

  function mount(container, options) {
    const view = { alive: true, timer: null, connections: [] };
    const request = (path, method = "GET", body) => options.api(path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const agents = options.agents || [], workflows = options.workflows || [];
    const can = Boolean(options.session?.can_manage);
    const head = el("div", undefined, "agent-toolbar");
    head.append(el("h2", "Otomasyonlar"));
    if (can) {
      const add = button("Otomasyon ekle", () => act(add, async () => { await view.ready; edit(null); }), "primary");
      head.append(add);
    }
    const intro = el("p", "İşlerin kendiliğinden başlamasını sağlayın: belirli zamanlarda, bir akış bittiğinde, klasöre dosya, "
      + "tabloya yeni kayıt veya posta kutusuna e-posta geldiğinde. Karar gerektiren işi bir ajana verin; hep aynı adımlarla "
      + "yapılan işi doğrudan bir akışa verin (yapay zekâ kullanmaz). Gelen işler sıraya girer ve teker teker işlenir. "
      + "Otomasyonlar yalnız Studio açık ve oturumunuz geçerliyken çalışır.", "muted");
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
    const workflowName = (identity) => workflows.find((item) => item.id === identity)?.name || "Silinmiş akış";

    function card(item) {
      const article = el("article", undefined, "agent-card agent-automation-card");
      const agent = agents.find((value) => value.id === item.agent_id);
      article.dataset.enabled = String(item.enabled);
      const who = item.target === "workflow" ? `Akış: ${item.target_name || workflowName(item.target_workflow_id)}`
        : `Ajan: ${agent ? agent.name : "Silinmiş ajan"}`;
      article.append(el("span", who, "agent-eyebrow"), el("h3", item.name), el("p", item.summary, "agent-automation-when"));
      if (item.target === "agent" && item.task) article.append(el("p", item.task, "agent-help agent-instructions"));
      const facts = el("ul", undefined, "agent-automation-facts");
      facts.append(el("li", item.enabled ? "Etkin" : "Kapalı"));
      if (item.trigger.kind === "schedule" && item.enabled) facts.append(el("li", `Sonraki: ${time(item.next_run_at)}`));
      if (item.queue_count) facts.append(el("li", `Sırada: ${item.queue_count} iş`));
      if (item.waiting) facts.append(el("li", "Masaüstünü bekliyor"));
      if (item.last_status) facts.append(el("li", `Son: ${statusText[item.last_status] || item.last_status} · ${time(item.last_run_at)}`));
      article.append(facts);
      if (item.last_message && item.last_status !== "started") article.append(el("p", item.last_message, item.last_status === "error" ? "agent-warning" : "agent-help"));
      const actions = el("div", undefined, "agent-actions");
      const openLast = (identity) => (item.target === "workflow" ? options.openRun?.(identity) : options.openAgentRun?.(identity));
      if (item.last_run_id) actions.append(button(item.target === "workflow" ? "Son çalışmayı aç" : "Son görevi aç", () => openLast(item.last_run_id)));
      if (can) {
        const run = button("Şimdi çalıştır", () => act(run, async () => {
          const changed = await request(`/api/agents/automations/${item.id}/run`, "POST", {});
          options.toast(item.target === "workflow" ? "Akış sıraya alındı." : "Görev başlatıldı.");
          if (item.target === "agent" && changed.last_run_id) options.openAgentRun?.(changed.last_run_id); else await refresh();
        }));
        const toggle = button(item.enabled ? "Kapat" : "Aç", () => act(toggle, async () => {
          await request(`/api/agents/automations/${item.id}`, "PUT", { ...payload(item), enabled: !item.enabled });
          await refresh();
        }));
        const remove = button("Sil", () => act(remove, async () => {
          if (!await confirmed("Otomasyon silinsin mi?", "Bundan sonra bu otomasyon iş başlatmaz. Sıradaki işler de silinir; daha önce başlattıkları kalır.")) return;
          await request(`/api/agents/automations/${item.id}`, "DELETE");
          await refresh();
        }), "danger");
        const change = button("Düzenle", () => act(change, async () => { await view.ready; edit(item); }));
        actions.append(run, change, toggle, remove);
      }
      article.append(actions);
      return article;
    }
    function payload(item) {
      const { name, target, agent_id, target_workflow_id, task, inputs, enabled, trigger } = item;
      return { name, target, agent_id, target_workflow_id, task, inputs, enabled, trigger };
    }
    function connectionChoice(types, value) {
      const options = view.connections.filter((item) => types.includes(item.type)).map((item) => [item.id, item.name]);
      return choice([["", options.length ? "Varsayılan bağlantı" : "Önce Ayarlar → Bağlantılar'dan ekleyin"], ...options], value || "");
    }

    function edit(item) {
      const defaults = { kind: "schedule", schedule_kind: "daily", time: "09:00", days: [0, 1, 2, 3, 4], every_minutes: 60,
        until: null, date: null, workflow_id: null, outcome: "any", folder: "", pattern: "*", source: "sheets",
        connection_id: null, spreadsheet_id: "", worksheet: "", query: "", file_path: "", sheet: "", key_column: "",
        filter_column: "", filter_value: "", process_existing: false, mail_folder: "", from_contains: "",
        subject_contains: "", attachment_folder: "", check_minutes: 5 };
      const current = item || { name: "", target: "agent", agent_id: agents[0]?.id || "", target_workflow_id: "", task: "",
        inputs: {}, enabled: true, trigger: defaults };
      const trigger = { ...defaults, ...current.trigger };
      form.hidden = false;
      form.replaceChildren(el("h3", item ? "Otomasyonu düzenle" : "Yeni otomasyon"));
      const name = input("text", current.name); name.maxLength = 120; name.required = true;
      const target = choice([["agent", "Ajana görev ver (karar gerektiren işler)"], ["workflow", "Akışı doğrudan çalıştır (hep aynı adımlar)"]],
        current.target || "agent");
      const agent = choice(agents.map((value) => [value.id, `${value.name} (${value.role === "manager" ? "Yönetici" : value.department})`]),
        current.agent_id || agents[0]?.id || "");
      const flow = choice([["", "Akış seçin"], ...workflows.map((value) => [value.id, value.name])], current.target_workflow_id || "");
      const task = input("textarea", current.task); task.rows = 4; task.maxLength = 16000;
      const kind = choice([["schedule", "Belirli zamanlarda"], ["rows", "Tabloya yeni kayıt geldiğinde"],
        ["email", "Yeni e-posta geldiğinde"], ["folder", "Klasöre yeni dosya geldiğinde"], ["workflow", "Bir akış bittiğinde"]], trigger.kind);
      // Schedule
      const often = choice([["daily", "Her gün"], ["weekly", "Belirli günler"], ["interval", "Belirli aralıklarla"], ["once", "Bir kez"]], trigger.schedule_kind);
      const date = input("date", trigger.date || ""); const hour = input("time", trigger.time || "09:00");
      const every = input("number", trigger.every_minutes || 60); every.min = "5"; every.max = "1440";
      const until = input("time", trigger.until || "");
      const dayBox = el("div", undefined, "agent-automation-days");
      const dayInputs = days.map((label, index) => {
        const { wrapper, box } = checkbox(label, (trigger.days || []).includes(index));
        dayBox.append(wrapper); return box;
      });
      const scheduleFields = el("div", undefined, "agent-form-grid");
      const dateField = labelled("Tarih", date), hourField = labelled("Saat (aralıkta başlangıç)", hour),
        everyField = labelled("Kaç dakikada bir", every, "En az 5 dakika."), untilField = labelled("Bitiş saati (isteğe bağlı)", until),
        dayField = el("div", undefined, "agent-field");
      dayField.append(el("span", "Günler", "agent-days-caption"), dayBox);
      scheduleFields.append(labelled("Ne sıklıkla?", often), dateField, hourField, everyField, untilField, dayField);
      // Workflow finished
      const watched = choice([["", "Akış seçin"], ...workflows.map((value) => [value.id, value.name])], trigger.workflow_id || "");
      const outcome = choice([["any", "Bittiğinde (her sonuç)"], ["succeeded", "Başarıyla bittiğinde"], ["failed", "Hata verdiğinde"]], trigger.outcome);
      const workflowFields = el("div", undefined, "agent-form-grid");
      workflowFields.append(labelled("İzlenen akış", watched, "Sizin veya zamanlayıcının başlattığı çalışmalar sayılır; ajanların ve otomasyonların çalıştırdığı akışlar tetiklemez."),
        labelled("Ne zaman?", outcome));
      // Folder
      const folder = input("text", trigger.folder || ""); folder.maxLength = 2000; folder.placeholder = "C:\\Gelen faturalar veya /Users/ad/Gelen";
      const pattern = input("text", trigger.pattern || "*"); pattern.maxLength = 100;
      const folderFields = el("div", undefined, "agent-form-grid");
      folderFields.append(labelled("Klasörün tam yolu", folder, "Yalnız bu klasöre doğrudan gelen yeni dosyalar sayılır; kayıt anındaki dosyalar işlenmez."),
        labelled("Dosya deseni", pattern, "Ör. *.pdf veya fatura_*.xlsx. Geçici ve gizli dosyalar sayılmaz."));
      // Rows
      const source = choice([["sheets", "Google Sheets"], ["database", "Veritabanı (SELECT sorgusu)"], ["file", "Excel / CSV dosyası"]], trigger.source);
      const sheetsConnection = connectionChoice(["google_sheets"], trigger.source === "sheets" ? trigger.connection_id : "");
      const databaseConnection = connectionChoice(["database"], trigger.source === "database" ? trigger.connection_id : "");
      const spreadsheet = input("text", trigger.spreadsheet_id || ""); spreadsheet.placeholder = "https://docs.google.com/spreadsheets/d/…";
      const worksheet = input("text", trigger.worksheet || ""); worksheet.placeholder = "Sayfa1";
      const query = input("textarea", trigger.query || ""); query.rows = 3; query.className = "mono";
      query.placeholder = "SELECT ID, MUSTERI, TUTAR FROM SIPARISLER WHERE DURUM = 'Bekliyor'";
      const filePath = input("text", trigger.file_path || ""); filePath.placeholder = "C:\\Paylaşım\\siparisler.xlsx";
      const sheet = input("text", trigger.sheet || ""); sheet.placeholder = "Boş: ilk sayfa";
      const keyColumn = input("text", trigger.key_column || ""); keyColumn.placeholder = "Ör. Fatura No veya ID";
      const filterColumn = input("text", trigger.filter_column || ""); filterColumn.placeholder = "Ör. Durum";
      const filterValue = input("text", trigger.filter_value || ""); filterValue.placeholder = "Ör. Bekliyor";
      const existing = checkbox("Kayıt anında tabloda olan kayıtları da işle", trigger.process_existing);
      const rowFields = el("div", undefined, "agent-form-grid");
      const sheetsBox = el("div", undefined, "agent-form-grid agent-span");
      sheetsBox.append(labelled("Google Sheets bağlantısı", sheetsConnection), labelled("Tablonun adresi", spreadsheet),
        labelled("Sayfa adı", worksheet, "İlk satır sütun başlıklarıdır."));
      const databaseBox = el("div", undefined, "agent-form-grid agent-span");
      databaseBox.append(labelled("Veritabanı bağlantısı", databaseConnection),
        labelled("Kayıtları getiren sorgu", query, "Yalnız SELECT; her kontrolde çalışır. Değişken kullanılamaz."));
      const fileBox = el("div", undefined, "agent-form-grid agent-span");
      fileBox.append(labelled("Dosyanın tam yolu", filePath), labelled("Sayfa (Excel)", sheet));
      rowFields.append(labelled("Kaynak", source), sheetsBox, databaseBox, fileBox,
        labelled("Her kaydı ayıran sütun", keyColumn, "Bu sütunda daha önce görülmemiş bir değer yeni kayıt sayılır (ör. Fatura No). Boş olan satırlar işlenmez."),
        labelled("Yalnız şu sütun… (isteğe bağlı)", filterColumn), labelled("…şu değere eşitse", filterValue), existing.wrapper);
      // Email
      const mailConnection = connectionChoice(["imap"], trigger.kind === "email" ? trigger.connection_id : "");
      const mailFolder = input("text", trigger.mail_folder || ""); mailFolder.placeholder = "Boş: bağlantıdaki klasör (INBOX)";
      const fromContains = input("text", trigger.from_contains || ""); fromContains.placeholder = "Ör. @tedarikci.com";
      const subjectContains = input("text", trigger.subject_contains || ""); subjectContains.placeholder = "Ör. Fatura";
      const attachmentFolder = input("text", trigger.attachment_folder || ""); attachmentFolder.placeholder = "Ör. C:\\Gelen ekler";
      const mailFields = el("div", undefined, "agent-form-grid");
      mailFields.append(labelled("Gelen e-posta (IMAP) bağlantısı", mailConnection), labelled("Klasör", mailFolder),
        labelled("Gönderen içeriyorsa", fromContains), labelled("Konu içeriyorsa", subjectContains),
        labelled("Ekleri bu klasöre kaydet", attachmentFolder, "Boş bırakılırsa ekler kaydedilmez. Kayıt anında posta kutusunda olan iletiler işlenmez."));
      const checkMinutes = input("number", trigger.check_minutes || 5); checkMinutes.min = "1"; checkMinutes.max = "1440";
      const checkField = labelled("Kaç dakikada bir denetlensin?", checkMinutes);
      const given = el("p", "", "agent-notice");
      const editor = (values) => {
        const selected = target.value === "workflow" ? workflows.find((value) => value.id === flow.value) : null;
        const suggestions = selected ? (selected.inputs || []).map((value) => ({ ...value, flows: [selected.name] }))
          : window.RpaAgents.expectedInputs(agents.find((value) => value.id === agent.value) || {});
        return window.RpaAgents.inputsEditor(values, suggestions);
      };
      let inputs = editor(current.inputs);
      const inputsBox = el("div");
      inputsBox.append(inputs.wrapper);
      const refreshInputs = () => {
        let values = {};
        try { values = inputs.read(); } catch { values = {}; }
        inputs = editor(values); inputsBox.replaceChildren(inputs.wrapper);
      };
      agent.addEventListener("change", refreshInputs);
      flow.addEventListener("change", refreshInputs);
      const agentField = labelled("Görevi alacak ajan", agent), flowField = labelled("Çalıştırılacak akış", flow,
        "Gelen iş, akışa girdi değişkeni olarak verilir; akış onay sormadan ve yapay zekâ kullanmadan çalışır.");
      const taskField = labelled("Görev", task, "Ajana her seferinde verilecek iş. Ör. «Gelen faturayı incele, uygunsa iade akışını çalıştır.»");
      const update = () => {
        const selected = kind.value, toAgent = target.value === "agent";
        agentField.hidden = taskField.hidden = !toAgent; flowField.hidden = toAgent;
        scheduleFields.hidden = selected !== "schedule"; workflowFields.hidden = selected !== "workflow";
        folderFields.hidden = selected !== "folder"; rowFields.hidden = selected !== "rows"; mailFields.hidden = selected !== "email";
        checkField.hidden = !["rows", "email"].includes(selected);
        sheetsBox.hidden = source.value !== "sheets"; databaseBox.hidden = source.value !== "database"; fileBox.hidden = source.value !== "file";
        dateField.hidden = often.value !== "once"; everyField.hidden = untilField.hidden = often.value !== "interval";
        dayField.hidden = !["weekly", "interval"].includes(often.value);
        given.textContent = `${toAgent ? "Ajan" : "Akış"}, işle birlikte şu girdileri de alır: ${triggerInputs[selected]}.`
          + (selected === "folder" || selected === "email" ? " Dosyayı okuyup işlemek için ajanın veya akışın bu klasöre erişimi olmalıdır." : "")
          + (selected === "rows" ? " Türkçe harfli veya boşluklu sütun adları değişkende sade yazılır: «Müşteri Adı» → ${kayit.Musteri_Adi}." : "");
      };
      for (const control of [kind, often, target, source]) control.addEventListener("change", update);
      update();
      const save = button("Otomasyonu kaydet", () => act(save, async () => {
        if (!name.value.trim()) throw new Error("Otomasyona bir ad verin.");
        const selectedSource = source.value;
        const body = { name: name.value.trim(), target: target.value, agent_id: target.value === "agent" ? agent.value || null : null,
          target_workflow_id: target.value === "workflow" ? flow.value || null : null, task: task.value.trim(), inputs: inputs.read(),
          enabled: current.enabled, trigger: { kind: kind.value, schedule_kind: often.value, date: date.value || null,
            time: hour.value || "09:00", days: dayInputs.flatMap((box, index) => (box.checked ? [index] : [])),
            every_minutes: Number(every.value) || 60, until: until.value || null, workflow_id: watched.value || null,
            outcome: outcome.value, folder: folder.value.trim() || null, pattern: pattern.value.trim() || "*",
            source: selectedSource, connection_id: (kind.value === "email" ? mailConnection.value
              : selectedSource === "sheets" ? sheetsConnection.value : selectedSource === "database" ? databaseConnection.value : "") || null,
            spreadsheet_id: spreadsheet.value.trim() || null, worksheet: worksheet.value.trim() || null, query: query.value.trim() || null,
            file_path: filePath.value.trim() || null, sheet: sheet.value.trim() || null, key_column: keyColumn.value.trim() || null,
            filter_column: filterColumn.value.trim() || null, filter_value: filterValue.value.trim() || null,
            process_existing: existing.box.checked, mail_folder: mailFolder.value.trim() || null,
            from_contains: fromContains.value.trim() || null, subject_contains: subjectContains.value.trim() || null,
            attachment_folder: attachmentFolder.value.trim() || null, check_minutes: Number(checkMinutes.value) || 5 } };
        await request(item ? `/api/agents/automations/${item.id}` : "/api/agents/automations", item ? "PUT" : "POST", body);
        options.toast("Otomasyon kaydedildi.");
        close(); await refresh();
      }), "primary");
      const controls = el("div", undefined, "agent-actions");
      controls.append(save, button("Vazgeç", close));
      const grid = el("div", undefined, "agent-form-grid");
      grid.append(labelled("Otomasyon adı", name), labelled("Ne yapılsın?", target), agentField, flowField);
      form.append(grid, taskField, labelled("Ne zaman çalışsın?", kind), scheduleFields, workflowFields, folderFields,
        rowFields, mailFields, checkField, given);
      const details = el("details", undefined, "agent-details");
      details.append(id(el("summary", "Girdi değişkenleri (isteğe bağlı)"), "summary"), inputsBox);
      form.append(details, controls);
      name.focus();
    }
    function close() { form.hidden = true; form.replaceChildren(); }

    async function refresh() {
      clearTimeout(view.timer);
      if (!view.alive) return;
      try {
        if (!document.hidden) {
          const items = await request("/api/agents/automations");
          if (!view.alive) return;
          const cards = items.map(card);
          list.replaceChildren(...(cards.length ? cards : [el("p", can
            ? "Henüz otomasyon yok. Otomasyon ekle ile başlayın: ör. Sheets tablosuna yeni sipariş gelince sipariş akışını çalıştırın."
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
    // Connection names fill the source choices; the editor opens only after they are known.
    view.ready = request("/api/connections").then((items) => { if (view.alive) view.connections = Array.isArray(items) ? items : []; })
      .catch(() => {});
    refresh();
    return () => { view.alive = false; clearTimeout(view.timer); document.removeEventListener("visibilitychange", visibility); };
  }

  window.RpaAgents.registerTab({ id: "automations", label: "Otomasyonlar", mount });
})();
