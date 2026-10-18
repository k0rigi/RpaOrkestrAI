"use strict";

(() => {
  let sequence = 0;
  const labels = { queued: "Sırada", running: "Çalışıyor", waiting_user: "Yanıt bekliyor",
    waiting_approval: "Onay bekliyor", succeeded: "Tamamlandı", failed: "Hata", cancelled: "Durduruldu",
    pending: "Onay bekliyor", approved: "Onaylandı", rejected: "Reddedildi", consumed: "Uygulandı" };
  const el = (tag, text, css = "") => {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = String(text);
    if (css) item.className = css;
    return item;
  };
  const id = (item) => { item.id = `agent-team-${++sequence}`; return item; };
  function button(text, work, css = "") {
    const item = id(el("button", text, `button ${css}`));
    item.type = "button";
    item.addEventListener("click", work);
    return item;
  }
  function input(label, value = "", multiline = false) {
    const wrapper = el("div", undefined, "agent-field");
    const field = id(el(multiline ? "textarea" : "input"));
    if (multiline) field.rows = 4;
    else field.type = "text";
    field.value = value;
    const caption = el("label", label);
    caption.htmlFor = field.id;
    wrapper.append(caption, field);
    return { wrapper, field };
  }
  function dropdown(label, options) {
    const item = input(label);
    const select = el("select");
    select.id = item.field.id;
    for (const [value, text] of options) {
      const option = el("option", text);
      option.value = value;
      select.append(option);
    }
    item.field.replaceWith(select);
    item.field = select;
    return item;
  }
  function state(status) { return el("span", labels[status] || "Bilinmiyor", "agent-status"); }
  const finished = new Set(["succeeded", "failed", "cancelled"]);
  async function confirmed(options, title, message, label = "Sil") {
    if (options.confirmDialog) return options.confirmDialog(title, message, label, true);
    return window.confirm(`${title}\n\n${message}`);
  }
  function time(value) { return value ? new Date(value).toLocaleString("tr-TR") : "—"; }
  function setup(container, options) {
    const view = { alive: true, busy: false, timer: null, container, options, current: null };
    view.request = (path, method = "GET", body) => options.api(path, {
      method, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    view.error = (error) => { if (view.alive) options.toast(error?.message || "İşlem tamamlanamadı.", true); };
    view.act = async (work) => {
      if (view.busy || !view.alive) return;
      view.busy = true;
      container.setAttribute("aria-busy", "true");
      try { await work(); } catch (error) { view.error(error); }
      finally { view.busy = false; container.removeAttribute("aria-busy"); }
    };
    view.dispose = () => {
      view.alive = false;
      clearTimeout(view.timer);
      document.removeEventListener("visibilitychange", view.visibility);
    };
    view.visibility = () => { if (!document.hidden) view.refresh?.(); };
    document.addEventListener("visibilitychange", view.visibility);
    return view;
  }
  function polling(view, load) {
    let loading = false;
    view.refresh = async () => {
      clearTimeout(view.timer);
      if (!view.alive || loading) return;
      loading = true;
      try { if (!document.hidden) await load(); }
      catch (error) { view.error(error); }
      finally {
        loading = false;
        if (view.alive) view.timer = setTimeout(view.refresh, 5000);
      }
    };
    view.refresh();
  }

  // Kontroller yalnız kayıtlı tanımlardan üretilir; hiçbir ajanı değiştirmez.
  function organizationChecks(agents, connections, workflows) {
    const manager = agents.find((item) => item.role === "manager");
    const departments = agents.filter((item) => item.role === "department");
    const checks = [];
    if (!agents.length) checks.push(["info", "Henüz ajan yok. Ajanlar sekmesinden bir departman ajanı ekleyerek başlayın."]);
    if (manager && !departments.some((item) => item.manager_id === manager.id)) {
      checks.push(["warn", `${manager.name} yöneticisine bağlı departman yok; yönetici görev dağıtamaz.`]);
    }
    if (!manager && departments.length > 1) {
      checks.push(["info", "Yönetici ajan ekleyerek tek bir görevle birden fazla departmanı çalıştırabilirsiniz."]);
    }
    for (const agent of agents) {
      const connection = connections.find((item) => item.id === agent.provider_connection_id);
      if (!connection) checks.push(["warn", `${agent.name} için geçerli bir model bağlantısı seçilmemiş.`]);
      if (agent.role !== "department") continue;
      if (!(agent.workflows || []).length) checks.push(["warn", `${agent.name} ajanının akış izni yok; görev alsa da iş yapamaz.`]);
      for (const grant of agent.workflows || []) {
        const flow = workflows.find((item) => item.id === grant.workflow_id);
        if (!flow) checks.push(["warn", `${agent.name} ajanının izinli akışlarından biri artık bulunmuyor.`]);
        else if (flow.agent_supported === false) checks.push(["warn", `${agent.name}: «${flow.name}» ajanla çalıştırılamaz.`]);
      }
    }
    if (agents.length && !checks.some(([kind]) => kind === "warn")) checks.unshift(["ok", "Kurulum tutarlı: her ajanın modeli ve görevine uygun izinleri var."]);
    return checks;
  }

  function mountOrganization(container, options) {
    const view = setup(container, options);
    const agents = options.agents || [];
    const manager = agents.find((item) => item.role === "manager");
    const linked = agents.filter((item) => item.role === "department" && manager && item.manager_id === manager.id);
    const independent = agents.filter((item) => item.role === "department" && !linked.includes(item));
    const tree = el("section", undefined, "agent-organization");
    const humans = el("section", undefined, "agent-panel");
    const checks = el("ul", undefined, "agent-org-checks");
    checks.setAttribute("aria-label", "Kurulum kontrolü");
    for (const [kind, text] of organizationChecks(agents, options.connections || [], options.workflows || [])) {
      const item = el("li", text); item.dataset.kind = kind; checks.append(item);
    }
    container.append(el("h2", "Organizasyon"),
      el("p", "Görevler yöneticiden departmanlara iner; sorular ve sonuçlar yöneticiye çıkar. Departmanlar birbiriyle doğrudan konuşmaz; böylece bir departmanın bilgisi veya izni diğerine kendiliğinden geçmez.", "muted"),
      checks, tree, humans);
    const departmentCard = (agent) => {
      const card = el("article", undefined, "agent-card agent-org-card");
      card.append(el("span", agent.department, "agent-eyebrow"), el("h3", agent.name),
        el("p", `${agent.workflows?.length || 0} izinli akış`, "agent-help"));
      return card;
    };
    const managerCard = el("article", undefined, "agent-card agent-manager-card agent-org-card");
    managerCard.append(el("span", "Yönetici ajan", "agent-eyebrow"),
      el("h3", manager?.name || "Yönetici henüz eklenmedi"),
      el("p", manager ? `${linked.length} departmana görev verebilir. Akış çalıştırmaz.` : "İsterseniz Ajanlar sekmesinden Yönetici rolüyle bir ajan ekleyin.", "muted"));
    tree.append(managerCard);
    if (manager) {
      const legend = el("ul", undefined, "agent-org-legend");
      legend.setAttribute("aria-label", "İletişim yönleri");
      for (const text of ["↓ Görev verir", "↑ Soru sorar", "↓ Yanıtlar", "↑ Sonuç teslim eder"]) legend.append(el("li", text));
      const row = el("div", undefined, "agent-cards agent-org-departments");
      row.append(...linked.map(departmentCard));
      if (!linked.length) row.append(el("p", "Bağlı departman yok. Departman ajanını düzenleyip Bağlı yönetici alanında bu yöneticiyi seçin.", "agent-help"));
      tree.append(legend, row);
    }
    if (independent.length) {
      tree.append(el("h3", "Bağımsız ajanlar"),
        el("p", "Bu ajanlara görevi doğrudan siz verirsiniz; takılınca size sorarlar ve diğer ajanlarla iletişim kurmazlar.", "agent-help"));
      const row = el("div", undefined, "agent-cards");
      row.append(...independent.map(departmentCard));
      tree.append(row);
    }
    if (options.session.can_manage && options.openTab) tree.append(button("Ajanları düzenle", () => options.openTab("agents")));
    if (options.session.individual) {
      // A personal account is a team of one: the person approves and there are no colleagues to list.
      humans.append(el("p", "Bireysel hesapta ekip sizsiniz: ajanlarınızın riskli işlemlerini siz onaylarsınız.", "agent-help"));
      return view.dispose;
    }
    const office = options.session.office?.name;
    const people = office ? `${office} çalışanları` : "İnsan çalışanlar";
    humans.append(el("h3", people), el("p", "Kurum hesapları yükleniyor…", "muted"));
    view.request("/api/agents/central/members").then((data) => {
      if (!view.alive) return;
      humans.replaceChildren(el("h3", people));
      const list = el("ul", undefined, "agent-people");
      for (const member of data.uyeler || []) {
        list.append(el("li", `${member.ad_soyad}${member.onayci ? (office ? " · Ofis yetkilisi" : " · Onay yetkilisi") : ""}`));
      }
      humans.append(list, el("p", office
        ? "Bu liste ofisinize bağlı, ajan lisansı bulunan hesaplardan gelir. Diğer departmanların ofisleri burada görünmez. Ofis yetkilisi lisanslı çalışanları Ofisim sekmesinden ofise ekler; lisans atama kurum yönetiminde yapılır. İnsan çalışanlara Görevler sekmesinden iş atanır."
        : "Bu liste ayrı ajan lisansı bulunan kurum hesaplarından gelir. Hesap oluşturma ve lisans atama kurum yönetiminde yapılır. İnsan çalışanlara Görevler sekmesinden iş atanır.", "agent-help"));
    }).catch((error) => {
      if (view.alive) humans.replaceChildren(el("h3", people), el("p", error.message, "agent-warning"));
    });
    return view.dispose;
  }

  function mountTasks(container, options) {
    const view = setup(container, options);
    const header = el("div", undefined, "agent-toolbar");
    header.append(el("h2", "Görevler"));
    const list = el("div", undefined, "agent-cards");
    const detail = el("section", undefined, "agent-panel");
    detail.hidden = true;
    const note = el("p", "İnsan görevlerinin başlığı, açıklaması ve sonucu kurum sunucusunda saklanır. Ajan çalışma ayrıntıları bu bilgisayarda kalır.", "agent-help");
    container.append(header, note, detail, list);
    let humanTasks = [], localTasks = [], members = [];
    function renderList() {
      const cards = [];
      for (const [kind, tasks] of [["human", humanTasks], ["agent", localTasks]]) {
        for (const task of tasks) {
          const card = el("article", undefined, "agent-card");
          const who = kind === "human" ? members.find((m) => m.kullanici_id === task.assignee_user_id)?.ad_soyad
            : options.agents.find((a) => a.id === task.assigned_agent_id)?.name;
          card.append(el("span", who || (kind === "human" ? "İnsan çalışan" : "Ajan"), "agent-eyebrow"),
            el("h3", task.title), state(task.status), el("p", time(task.created_at), "agent-help"));
          const actions = el("div", undefined, "agent-actions");
          if (kind === "human") actions.append(button("Görevi aç", () => view.act(() => showHuman(task.id))));
          else if (task.run_id) actions.append(button("Çalışmayı aç", () => options.openAgentRun(task.run_id)));
          if (options.session.can_manage && finished.has(task.status)) {
            actions.append(button("Sil", () => view.act(() => removeTask(kind, task)), "danger"));
          }
          card.append(actions);
          if (task.parent_task_id) card.append(el("p", "Bir yönetici görevinin alt görevi", "agent-help"));
          cards.push(card);
        }
      }
      list.replaceChildren(...(cards.length ? cards : [el("p", "Henüz görev yok.", "muted")]));
    }
    async function removeTask(kind, task) {
      const message = kind === "human"
        ? "Görev listelerden ve performans hesabından kalkar; kayıt denetim için kurum sunucusunda saklanır."
        : task.parent_task_id ? "Bu ajan görevi ve çalışma kaydı silinir. Çalıştırdığı akışların kaydı Çalışma geçmişinde kalır."
          : "Bu görev, varsa departmanlara verilen alt görevleriyle birlikte silinir. Akış kayıtları Çalışma geçmişinde kalır.";
      if (!await confirmed(options, "Görev silinsin mi?", message)) return;
      if (kind === "human") {
        await view.request(`/api/agents/central/tasks/${encodeURIComponent(task.id)}/delete`, "POST", { expected_version: task.version });
      } else await view.request(`/api/agents/tasks/${encodeURIComponent(task.id)}`, "DELETE");
      if (view.current === task.id) { view.current = null; detail.hidden = true; detail.replaceChildren(); }
      options.toast("Görev silindi.");
      await view.refresh();
    }
    async function showHuman(identity) {
      const data = await view.request(`/api/agents/central/tasks/${encodeURIComponent(identity)}`);
      if (!view.alive) return;
      const task = data.task;
      view.current = identity;
      detail.hidden = false;
      detail.replaceChildren(el("h3", task.title), state(task.status), el("p", task.instructions, "agent-task-copy"));
      if (task.summary) detail.append(el("h4", "Sonuç"), el("p", task.summary, "agent-task-copy"));
      const mayUpdate = options.session.can_manage || task.assignee_user_id === options.session.actor?.user_id;
      const transitions = { queued: [["running", "Göreve başla"], ["cancelled", "İptal et"]],
        running: [["waiting_user", "Yanıt bekle"], ["succeeded", "Tamamlandı"], ["failed", "Hata bildir"], ["cancelled", "İptal et"]],
        waiting_user: [["running", "Devam et"], ["cancelled", "İptal et"]] };
      if (mayUpdate && transitions[task.status]) {
        const summary = input("Durum veya sonuç notu", "", true);
        summary.field.maxLength = 4000;
        detail.append(summary.wrapper);
        const actions = el("div", undefined, "agent-toolbar");
        for (const [status, label] of transitions[task.status]) {
          if (task.assignee_user_id !== options.session.actor?.user_id && status !== "cancelled") continue;
          actions.append(button(label, () => view.act(async () => {
            await view.request(`/api/agents/central/tasks/${identity}/status`, "POST", {
              status, expected_version: task.version, summary: summary.field.value,
            });
            await showHuman(identity);
            await view.refresh();
          })));
        }
        detail.append(actions);
      }
      if (options.session.can_manage && task.status === "queued") {
        const assignee = dropdown("Başka çalışana aktar", members.map((m) => [String(m.kullanici_id), m.ad_soyad]));
        assignee.field.value = String(task.assignee_user_id);
        detail.append(assignee.wrapper, button("Atamayı değiştir", () => view.act(async () => {
          await view.request(`/api/agents/central/tasks/${identity}/assign`, "POST", {
            assignee_user_id: Number(assignee.field.value), expected_version: task.version,
          });
          await showHuman(identity); await view.refresh();
        })));
      }
      if (options.session.can_manage) {
        if (finished.has(task.status)) detail.append(button("Görevi sil", () => view.act(() => removeTask("human", task)), "danger"));
        else detail.append(el("p", "Görevi silmek için önce iptal edin.", "agent-help"));
      }
      detail.append(button("Ayrıntıyı kapat", () => { view.current = null; detail.hidden = true; detail.replaceChildren(); }));
      detail.scrollIntoView({ block: "nearest" });
    }
    function newAgentTask() {
      view.current = "new_agent";
      detail.hidden = false;
      detail.replaceChildren(el("h3", "Ajana görev ver"));
      const availableAgents = options.agents || [];
      if (!availableAgents.length) {
        detail.append(el("p", "Henüz ajan oluşturulmadı. Önce Ajanlar sekmesinden bir ajan ekleyin.", "agent-warning"),
          button("Vazgeç", () => { detail.hidden = true; detail.replaceChildren(); view.current = null; }));
        return;
      }
      const title = input("Görev başlığı"); title.field.required = true; title.field.maxLength = 160;
      const instructions = input("Yapılacak iş / Hedef", "", true); instructions.field.required = true; instructions.field.maxLength = 16000;
      const agentDropdown = dropdown("Ajan seçin", availableAgents.map((a) => [a.id, `${a.name} (${a.department || "Genel"})`]));
      const form = id(el("form"));
      form.append(agentDropdown.wrapper, title.wrapper, instructions.wrapper);
      const submit = id(el("button", "Görevi başlat", "button primary")); submit.type = "submit";
      form.append(submit);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        view.act(async () => {
          const agentId = agentDropdown.field.value;
          const taskText = `${title.field.value.trim()}\n\n${instructions.field.value.trim()}`;
          const run = await view.request(`/api/agents/${encodeURIComponent(agentId)}/runs`, "POST", {
            task: taskText, title: title.field.value.trim(), inputs: {},
          });
          options.toast("Ajan görevi başlatıldı.");
          detail.hidden = true; detail.replaceChildren(); view.current = null;
          if (options.openAgentRun && run?.id) options.openAgentRun(run.id);
          else await view.refresh();
        });
      });
      detail.append(form, button("Vazgeç", () => { detail.hidden = true; detail.replaceChildren(); view.current = null; }));
    }

    function newHumanTask() {
      view.current = "new";
      detail.hidden = false;
      detail.replaceChildren(el("h3", "İnsan çalışana görev ata"));
      if (!members.length) {
        detail.append(el("p", "Görev atanabilecek lisanslı çalışan bulunamadı. Kurum bağlantısını ve çalışan lisanslarını kontrol edin.", "agent-warning"),
          button("Vazgeç", () => { detail.hidden = true; detail.replaceChildren(); view.current = null; }));
        return;
      }
      const title = input("Görev başlığı"); title.field.required = true; title.field.maxLength = 160;
      const instructions = input("Yapılacak iş", "", true); instructions.field.required = true; instructions.field.maxLength = 16000;
      const member = dropdown("Atanan çalışan", members.map((m) => [String(m.kullanici_id), m.ad_soyad]));
      const priority = dropdown("Öncelik", [["normal", "Normal"], ["high", "Yüksek"], ["low", "Düşük"]]);
      const form = id(el("form"));
      form.append(title.wrapper, instructions.wrapper, member.wrapper, priority.wrapper);
      const submit = id(el("button", "Görevi ata", "button primary")); submit.type = "submit";
      form.append(submit);
      const requestId = Array.from(crypto.getRandomValues(new Uint8Array(16)),
        (value) => value.toString(16).padStart(2, "0")).join("");
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        view.act(async () => {
          const data = await view.request("/api/agents/central/tasks", "POST", {
            request_id: requestId, title: title.field.value, instructions: instructions.field.value,
            assignee_user_id: Number(member.field.value), priority: priority.field.value,
          });
          await showHuman(data.task.id); await view.refresh();
        });
      });
      detail.append(form, button("Vazgeç", () => { detail.hidden = true; detail.replaceChildren(); view.current = null; }));
    }

    header.append(button("Ajana görev ver", newAgentTask, "primary"));
    if (options.session.can_manage) header.append(button("İnsan çalışana görev ata", newHumanTask));
    header.append(button("Yenile", () => view.refresh()));
    polling(view, async () => {
      const responses = await Promise.allSettled([
        view.request("/api/agents/tasks"), view.request("/api/agents/central/tasks"), view.request("/api/agents/central/members"),
      ]);
      if (!view.alive) return;
      if (responses[0].status === "fulfilled") localTasks = responses[0].value;
      if (responses[1].status === "fulfilled") humanTasks = responses[1].value.tasks || [];
      if (responses[2].status === "fulfilled") members = responses[2].value.uyeler || [];
      const error = responses.find((response) => response.status === "rejected");
      note.textContent = error ? `Bazı görevler alınamadı: ${error.reason.message}`
        : "İnsan görevleri kurum sunucusunda, ajan çalışma ayrıntıları bu bilgisayarda tutulur.";
      renderList();
    });
    return view.dispose;
  }

  function mountApprovals(container, options) {
    const view = setup(container, options);
    const list = el("div", undefined, "agent-cards");
    const detail = el("section", undefined, "agent-panel"); detail.hidden = true;
    const note = el("p", "Onaylar yükleniyor…", "agent-help");
    container.append(el("h2", "Kurum onayları"), note, detail, list);
    async function show(identity) {
      const data = await view.request(`/api/agents/central/approvals/${encodeURIComponent(identity)}`);
      if (!view.alive) return;
      const item = data.approval;
      detail.hidden = false;
      detail.replaceChildren(el("h3", item.preview?.workflow_name || "Akış onayı"), state(item.status),
        el("h4", "Girdiler"), el("pre", JSON.stringify(item.preview?.inputs || {}, null, 2), "agent-json"),
        el("h4", "Ajanın gerekçesi"), el("p", item.reason, "agent-task-copy"),
        el("p", `Son onay zamanı: ${time(item.expires_at)} · Deneme: ${item.attempt}`, "agent-help"));
      if (item.status === "pending" && options.session.can_approve) {
        const actions = el("div", undefined, "agent-toolbar");
        for (const [approved, label] of [[true, "Onayla"], [false, "Reddet"]]) {
          actions.append(button(label, () => view.act(async () => {
            await view.request(`/api/agents/central/approvals/${identity}/decision`, "POST", { approved });
            await show(identity); await view.refresh();
          }), approved ? "primary" : "danger"));
        }
        detail.append(actions);
      } else if (item.status === "pending") detail.append(el("p", options.session.office ? "Kararı ofisinizin yetkilisi verebilir." : "Kararı firmanın onay yetkilisi verebilir.", "muted"));
      detail.append(button("Ayrıntıyı kapat", () => { detail.hidden = true; detail.replaceChildren(); }));
    }
    let members = null;
    polling(view, async () => {
      try {
        if (members === null) {
          // Names are only a label; a failed member list must not hide approvals.
          members = await view.request("/api/agents/central/members").then((data) => data.uyeler || []).catch(() => []);
        }
        const data = await view.request("/api/agents/central/approvals");
        if (!view.alive) return;
        note.textContent = "Onay akışa, girdilere ve tek denemeye bağlıdır. Süresi dolan onayla işlem başlatılmaz.";
        const cards = (data.approvals || []).map((item) => {
          const card = el("article", undefined, "agent-card");
          const requester = members.find((member) => member.kullanici_id === item.requester_user_id)?.ad_soyad;
          card.append(state(item.status), el("p", `İsteyen: ${requester || `hesap ${item.requester_user_id}`}`, "agent-help"),
            el("p", `Oluşturma: ${time(item.created_at)}`, "agent-help"), button("Onayı incele", () => view.act(() => show(item.id))));
          return card;
        });
        list.replaceChildren(...(cards.length ? cards : [el("p", "Bekleyen onay bulunmuyor.", "muted")]));
      } catch (err) {
        if (!view.alive) return;
        note.textContent = "Kurum onayları alınamadı.";
        list.replaceChildren(el("div", null, "agent-warning"),
          el("p", `Onay hizmetine bağlanılamadı: ${err?.message || "Oturum süresi dolmuş olabilir. Sol alttan çıkış yapıp tekrar giriş yapın."}`));
      }
    });
    return view.dispose;
  }
  // Every office of the account (an authority may run several) and opening another one.
  function officeList(view, options) {
    const section = el("section", undefined, "agent-my-offices");
    const several = (options.session.offices || []).length > 1;
    if (!several && !options.session.can_create_office) return section;
    const list = el("ul", undefined, "agent-office-list");
    section.append(el("h3", several ? "Ofislerim" : "Başka bir ofis"), list);
    if (several) {
      list.append(el("li", "Ofis bilgileri yükleniyor…", "muted"));
      view.request("/api/agents/central/my-offices").then((data) => {
        if (!view.alive) return;
        list.replaceChildren(...(data.offices || []).map((office) => {
          const row = el("li");
          const facts = `${office.agents} ajan · ${office.people} kişi · ${office.open_tasks} açık görev · ${office.pending_approvals} onay bekliyor`;
          const text = el("div");
          text.append(el("strong", office.name), el("span", facts, "agent-help"));
          row.append(text, office.on_screen ? el("span", "Ekranda", "agent-office-current")
            : button("Bu ofise geç", () => view.act(async () => {
              await view.request("/api/agents/central/my-office/select", "POST", { office_id: office.id });
              options.reload?.();
            }), "small"));
          return row;
        }));
      }).catch((error) => { if (view.alive) list.replaceChildren(el("li", error.message, "agent-warning")); });
      section.append(el("p", "Ofis değiştirmek yalnız ekranı değiştirir; diğer ofislerin ajanları, otomasyonları ve onay beklemeleri kendi ofislerinde sürer.", "agent-help"));
    }
    if (options.session.can_create_office) {
      const name = input("Yeni ofisin adı");
      name.field.maxLength = 120;
      name.field.placeholder = "ör. Satın Alma Departmanı";
      section.append(name.wrapper, button("Yeni ofis kur", () => view.act(async () => {
        const value = name.field.value.trim().replace(/\s+/g, " ");
        if (value.length < 2) throw new Error("Yeni ofise en az 2 karakterlik bir ad verin.");
        await view.request("/api/agents/central/my-office", "POST", { name: value });
        options.toast(`${value} ofisi kuruldu; ekranda artık bu ofis var.`);
        options.reload?.();
      }), "primary"), el("p", "Kurduğunuz her ofisin yetkilisi sizsiniz; her ofisin kendi ajanları, çalışanları ve onayları olur.", "agent-help"));
    }
    return section;
  }

  // The office on screen: its authority names it and places licensed colleagues; a member may leave.
  function mountMyOffice(container, options) {
    const view = setup(container, options);
    const draw = (data) => {
      if (!view.alive) return;
      const office = data.office;
      if (!office) {
        container.replaceChildren(el("h2", "Ofisim"), el("p", "Bu hesap bir ofise bağlı değil.", "muted"));
        return;
      }
      const head = el("div", undefined, "agent-toolbar");
      head.append(el("h2", office.name));
      // A personal account is a team of one: there are no colleagues to place in its office.
      const individual = Boolean(options.session.individual);
      const intro = el("p", !office.is_authority ? "Bu ofisin üyesisiniz. Ajanları ve onayları ofisin yetkilisi yönetir."
        : individual ? "Bu ofisin yetkilisisiniz: ajanları kurar ve riskli işlemleri onaylarsınız."
          : "Bu ofisin yetkilisisiniz: ajanları kurar, riskli işlemleri onaylar ve çalışanları ofise yerleştirirsiniz.", "muted");
      const people = el("ul", undefined, "agent-people");
      for (const member of data.members || []) {
        const row = el("li", `${member.name}${member.authority ? " · Ofis yetkilisi" : ""}`);
        if (office.is_authority && !member.authority) {
          row.append(" ", button("Ofisten çıkar", () => view.act(async () => {
            if (!(await confirmed(options, "Ofisten çıkar", `${member.name} bu ofisten çıkarılsın mı? Ofisteki görev geçmişi ofiste kalır.`, "Çıkar"))) return;
            await view.request(`/api/agents/central/my-office/members/${member.user_id}/remove`, "POST", {});
            options.toast(`${member.name} ofisten çıkarıldı.`);
            await load();
          }), "small"));
        }
        people.append(row);
      }
      const parts = [head, intro, el("h3", "Ofisteki çalışanlar"), people];
      if (office.is_authority) {
        const rename = input("Ofis adı", office.name);
        rename.field.maxLength = 120;
        parts.push(rename.wrapper, button("Adı kaydet", () => view.act(async () => {
          await view.request("/api/agents/central/my-office/name", "POST", { name: rename.field.value.trim().replace(/\s+/g, " ") });
          options.toast("Ofis adı kaydedildi. Yeni ad birkaç dakika içinde tüm ekranlarda görünür.");
          await load();
        })));
        if (!individual) {
          parts.push(el("h3", "Ofise çalışan ekle"));
          if ((data.candidates || []).length) {
            const choice = dropdown("Ofisi olmayan lisanslı çalışan", data.candidates.map((item) => [String(item.user_id), item.name]));
            parts.push(choice.wrapper, button("Ofise ekle", () => view.act(async () => {
              const picked = data.candidates.find((item) => String(item.user_id) === choice.field.value);
              await view.request("/api/agents/central/my-office/members", "POST", { user_id: Number(choice.field.value) });
              options.toast(`${picked?.name || "Çalışan"} ofise eklendi.`);
              await load();
            }), "primary"));
          } else {
            parts.push(el("p", "Ofisi olmayan, RPA ve Ajanlar lisanslı çalışan yok. Yeni çalışanlara lisans orkestrai.net yönetiminden verilir; kendi ofisini kuran çalışan buraya gelmez.", "agent-help"));
          }
        }
      } else {
        parts.push(button("Ofisten ayrıl", () => view.act(async () => {
          if (!(await confirmed(options, "Ofisten ayrıl", "Bu ofisten ayrılırsanız ofisin görevlerini ve onaylarını görmezsiniz. İsterseniz sonra kendi ofisinizi kurabilirsiniz.", "Ayrıl"))) return;
          await view.request("/api/agents/central/my-office/leave", "POST", {});
          options.toast("Ofisten ayrıldınız.");
          options.reload?.();
        })));
      }
      // The summary of every office comes first: it is where an authority of several offices starts.
      parts.splice(2, 0, officeList(view, options));
      const page = el("section", undefined, "agent-my-office");
      page.append(...parts);
      container.replaceChildren(page);
    };
    const load = async () => draw(await view.request("/api/agents/central/my-office"));
    container.replaceChildren(el("h2", "Ofisim"), el("p", "Ofis bilgisi yükleniyor…", "muted"));
    load().catch((error) => { if (view.alive) container.replaceChildren(el("h2", "Ofisim"), el("p", error.message, "agent-warning")); });
    return view.dispose;
  }

  window.RpaAgents.registerTab({ id: "my-office", label: "Ofisim", mount: mountMyOffice, hidden: (session) => !session?.office });
  window.RpaAgents.registerTab({ id: "organization", label: "Organizasyon", mount: mountOrganization });
  // Human tasks need colleagues; a person's own account has none.
  window.RpaAgents.registerTab({ id: "tasks", label: "Görevler", mount: mountTasks, hidden: (session) => Boolean(session?.individual) });
  window.RpaAgents.registerTab({ id: "approvals", label: "Onaylar", mount: mountApprovals });
})();
