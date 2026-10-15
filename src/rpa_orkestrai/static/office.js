"use strict";

// The scene consumes only status DTOs. Business details are requested after selection.
let serial = 0;
const states = { idle: "Boşta", queued: "Sırada", running: "Çalışıyor", waiting_user: "Yanıt bekliyor",
  waiting_approval: "Onay bekliyor", succeeded: "Tamamlandı", failed: "Hata", cancelled: "Durduruldu", unknown: "Durum paylaşılmıyor" };
const activityNames = { thinking: "Düşünüyor", workflow: "Akış çalıştırıyor", asking_manager: "Yöneticiye soru soruyor",
  reviewing: "Departman sorusunu yanıtlıyor" };
function stateName(person) { return activityNames[person.activity] || states[person.status] || "Bilinmiyor"; }
function symbol(person) { return ({ thinking: "…", workflow: "↻", waiting_approval: "!", waiting_user: "?", asking_manager: "?", reviewing: "✎",
  failed: "!", succeeded: "✓", queued: "◷", running: "…", unknown: "—" })[person.activity || person.status] || "·"; }
function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = String(text);
  if (className) result.className = className;
  return result;
}
function button(text, callback) {
  const result = node("button", text, "button small");
  result.id = `rpa-office-button-${++serial}`; result.type = "button";
  result.addEventListener("click", callback);
  return result;
}
function palette() {
  const style = getComputedStyle(document.documentElement);
  return Object.fromEntries(["bg", "surface", "surface-2", "surface-3", "ink", "ink-2", "line", "line-strong",
    "accent", "accent-tint", "ok", "muted", "mark", "on-solid", "err", "warn"].map((key) => [key, style.getPropertyValue(`--${key}`).trim()]));
}
function population(data) { return [...data.agents, ...(data.people || [])]; }
function rooms(data) {
  const groups = new Map(data.departments.map((department) => [`department:${department.name}`, { name: department.name, members: [] }]));
  for (const person of population(data)) {
    if (person.role === "manager") continue;
    const human = person.kind === "human", name = human ? "Çalışanlar" : person.department || "Departman alanı";
    const key = human ? "people" : `department:${name}`;
    if (!groups.has(key)) groups.set(key, { name, members: [] }); groups.get(key).members.push(person);
  }
  if (!groups.size) ["Departman alanı 1", "Departman alanı 2"].forEach((name) => groups.set(name, { name, members: [] }));
  const result = [];
  let z = -5, rowHeight = 0;
  [...groups.values()].forEach(({ name, members }, index) => {
    if (index && index % 2 === 0) { z += rowHeight + 2; rowHeight = 0; }
    const depth = Math.max(5.4, Math.ceil(members.length / 3) * 3.2 + 2);
    result.push({ name, members, x: index % 2 ? 8 : -8, z: z + depth / 2 - 2.7, depth });
    rowHeight = Math.max(rowHeight, depth);
  });
  return result;
}
function seating(data) {
  const result = [];
  for (const person of population(data)) if (person.role === "manager") result.push({ person, x: 0, z: -.7, large: true });
  for (const room of rooms(data)) room.members.forEach((person, index) => {
    result.push({ person, x: room.x + (index % 3 - 1) * 2.5, z: room.z - room.depth / 2 + 2.7 + Math.floor(index / 3) * 3.2 });
  });
  return result;
}
function safeData(value) {
  if (!value || !Array.isArray(value.agents) || !Array.isArray(value.departments)) throw new Error("Ofis durumu okunamadı.");
  return { agents: value.agents.slice(0, 500), people: [], departments: value.departments.slice(0, 100), totals: value.totals || {} };
}

export function mountOffice(container, options) {
  let alive = true, mode = "3d", model = null, timer = null, pending = false, scene = null, generation = 0;
  let shapeKey = "", lastData = null, selected = null, panelVersion = 0;
  const seenEvents = new Set();
  const title = node("div", undefined, "office-title");
  title.append(node("p", "DİJİTAL EKİP", "agent-eyebrow"), node("h2", "Ofis"),
    node("p", "Ajanlarınız ve çalışma arkadaşlarınız aynı ofiste", "muted"));
  const toolbar = node("div", undefined, "office-toolbar");
  const status = node("span", "Yükleniyor…", "office-mode-label"); status.setAttribute("role", "status");
  const controls = node("div", undefined, "agent-actions");
  const buttons = new Map();
  for (const [key, text] of [["3d", "3D görünüm"], ["2d", "2D plan"], ["list", "Liste"]]) {
    const item = button(text, () => switchMode(key)); buttons.set(key, item); controls.append(item);
  }
  const reset = button("Kamerayı sıfırla", () => scene?.reset()); controls.append(reset); toolbar.append(status, controls);
  const frame = node("div", undefined, "office-frame"), view = node("div", undefined, "office-view");
  view.append(node("p", "Ofis hazırlanıyor…", "office-loading"));
  const preview = node("span", "CANLI OFİS", "office-preview");
  const legend = node("p", "Sürükleyin: döndür · Tekerlek: yakınlaştır · Karaktere tıklayın: ayrıntı · Balonlar: Görev, Soru, Yanıt, Sonuç", "office-legend");
  frame.append(view, preview, legend);
  const panel = node("aside", undefined, "office-detail"); panel.hidden = true; panel.setAttribute("aria-label", "Çalışan ayrıntısı");
  const layout = node("div", undefined, "office-layout"); layout.append(frame, panel);
  const note = node("p", "Bu görünüm yalnız bilgi gösterir. Departman ajanları birbirleriyle doğrudan konuşmaz; görev, soru ve sonuçlar yönetici üzerinden akar. Balonlarda yalnız mesajın türü görünür, içeriği ofise taşınmaz; ayrıntı için bir çalışan seçin.", "agent-help");
  const humanWarning = node("p", "", "agent-warning office-human-warning"); humanWarning.hidden = true; humanWarning.setAttribute("role", "status");
  const summary = node("p", "", "office-summary"), list = node("div", undefined, "office-list");
  // The feed repeats only who addressed whom and the message type, exactly as the balloons do.
  const feed = node("section", undefined, "office-feed"), feedList = node("ol", undefined, "office-feed-list");
  feed.setAttribute("aria-label", "Son iletişimler");
  feed.append(node("h3", "Son iletişimler"), feedList);
  const feedSeen = new Set(), feedItems = [];
  container.replaceChildren(title, toolbar, layout, summary, feed, humanWarning, note, list); container.classList.add("office-root");

  function updateList(data) {
    const focused = list.contains(document.activeElement) ? document.activeElement.dataset.person : null;
    const headings = ["Çalışan", "Tür / alan", "Durum", "Görev", "Sırada"];
    const table = node("table", undefined, "office-table"), caption = node("caption", "Ajanların ve insanların anlık durumu");
    const head = node("thead"), row = node("tr");
    headings.forEach((label) => { const cell = node("th", label); cell.scope = "col"; row.append(cell); });
    head.append(row); const body = node("tbody");
    for (const person of population(data)) {
      const item = node("tr"), name = node("td"), link = button(person.name, () => selectPerson(person.id));
      link.dataset.person = person.id; name.append(link);
      item.append(name);
      [person.kind === "human" ? "İnsan · Çalışanlar" : person.role === "manager" ? "Ajan · Yönetim" : `Ajan · ${person.department || "Departman alanı"}`,
        stateName(person), person.task_label || "Görev bekliyor", Number(person.queue_count) || 0].forEach((value) => item.append(node("td", value)));
      body.append(item);
    }
    if (!population(data).length) {
      const item = node("tr"), cell = node("td", "Henüz çalışan yok. Ajanlar ve kurum üyeleri eklendikçe ofisiniz düzenlenir.");
      cell.colSpan = headings.length; item.append(cell); body.append(item);
    }
    table.append(caption, head, body); list.replaceChildren(table);
    if (focused) [...list.querySelectorAll("button[data-person]")].find((item) => item.dataset.person === focused)?.focus({ preventScroll: true });
    summary.textContent = `${data.agents.length} ajan · ${data.people.length} insan · ${data.departments.length} departman · ${Number(data.totals.queued) || 0} ajan görevi sırada`;
  }
  function updateFeed(data) {
    const people = population(data), verbs = { delegated: "görev verdi", question: "soru sordu", answered: "soruyu yanıtladı",
      completed: "sonucu teslim etti" };
    for (const person of people) {
      const event = person.event;
      if (!event?.id || feedSeen.has(event.id) || !verbs[event.kind]) continue;
      if (event.kind === "completed" && person.status !== "succeeded") continue;
      const target = people.find((item) => item.id === event.to_agent_id);
      if (!target) continue;
      feedSeen.add(event.id); if (feedSeen.size > 500) feedSeen.delete(feedSeen.values().next().value);
      feedItems.unshift({ time: new Date(), text: `${person.name} → ${target.name}: ${verbs[event.kind]}`, kind: event.kind });
    }
    feedItems.splice(8);
    feedList.replaceChildren(...(feedItems.length ? feedItems.map((item) => {
      const row = node("li"); row.dataset.kind = item.kind;
      row.append(node("time", item.time.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })), node("span", item.text));
      return row;
    }) : [node("li", "Henüz iletişim yok. Yönetici görev verdiğinde, bir departman soru sorduğunda veya sonuç teslim ettiğinde burada görünür.", "agent-help")]));
  }
  function closePanel() { selected = null; panelVersion++; panel.hidden = true; panel.replaceChildren(); layout.classList.remove("office-with-panel"); }
  async function selectPerson(identity) {
    const person = lastData && population(lastData).find((item) => item.id === identity);
    if (!alive || !person) return;
    selected = identity; const version = ++panelVersion;
    panel.hidden = false; layout.classList.add("office-with-panel");
    const top = node("div", undefined, "office-detail-heading");
    top.append(node("h3", person.name), button("Kapat", closePanel));
    const live = node("p", `${stateName(person)} · ${person.task_label || "Görev bekliyor"}`, "office-detail-live");
    panel.replaceChildren(top, node("p", person.kind === "human" ? "İnsan çalışan" : person.role === "manager" ? "Yönetici ajan" : `Departman ajanı · ${person.department}`, "agent-eyebrow"), live);
    if (person.kind === "human" && !person.can_view_tasks) { panel.append(node("p", "Bu çalışanın görev ayrıntılarını görüntüleme yetkiniz yok.", "agent-help")); return; }
    if (person.kind === "human") panel.append(button("Görevler ekranına git", () => options.openTab?.("tasks")));
    else if (person.run_id) panel.append(button(person.status === "waiting_approval" ? "Onay kartına git" : "Çalışma kaydına git", () => options.openAgentRun?.(person.run_id)));
    const details = node("div", "Ayrıntılar yükleniyor…", "office-detail-body"); panel.append(details);
    const end = new Date(), start = new Date(end); start.setHours(0, 0, 0, 0); start.setDate(1);
    const range = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
    const human = person.kind === "human";
    const responses = await Promise.allSettled([
      options.api(human ? "/api/agents/central/tasks" : `/api/agents/tasks?agent_id=${encodeURIComponent(identity)}`),
      options.api(`/api/agents/${human ? "central/" : ""}metrics?${range}`),
    ]);
    if (!alive || selected !== identity || panelVersion !== version) return;
    details.replaceChildren();
    const tasks = responses[0].status === "fulfilled" ? (human ? responses[0].value.tasks : responses[0].value) : null;
    if (Array.isArray(tasks)) {
      const own = tasks.filter((item) => human ? item.assignee_user_id === person.user_id : item.assigned_agent_id === identity || item.assignee_id === identity);
      const current = own.find((item) => item.id === person.task_id);
      if (current) { details.append(node("h4", "Anlık görev"), node("p", current.title, "office-task-title")); }
      details.append(node("h4", "Son görevler"));
      const recent = node("ul", undefined, "office-recent");
      own.slice(0, 5).forEach((task) => recent.append(node("li", `${task.title} · ${states[task.status] || "Bilinmiyor"}`)));
      details.append(own.length ? recent : node("p", "Henüz görev kaydı yok.", "agent-help"));
    } else details.append(node("p", "Görev ayrıntıları alınamadı.", "agent-warning"));
    const metrics = responses[1].status === "fulfilled" ? responses[1].value : null;
    const values = human ? metrics?.metrics?.users : metrics?.agents;
    const entry = Array.isArray(values) ? values.find((item) => human ? item.user_id === person.user_id : item.id === identity) : null;
    details.append(node("h4", "Bu ayın performansı"));
    if (entry) {
      details.append(node("p", `${Number(entry.succeeded) || 0} tamamlandı · ${Number(entry.failed) || 0} başarısız · ${Number(entry.cancelled) || 0} iptal`),
        node("p", `Ortalama süre: ${Math.round(Number(entry.average_seconds) || 0)} sn · Toplam süre: ${Math.round(Number(entry.total_seconds) || 0)} sn`, "agent-help"));
    } else details.append(node("p", metrics ? "Bu ay için görev kaydı yok." : "Performans bilgisi alınamadı.", "agent-help"));
  }
  function fallback(message) {
    if (!alive) return;
    mode = "2d"; scene?.dispose(); scene = null; generation++;
    renderPlan(view, lastData || { agents: [], people: [], departments: [] }, selectPerson);
    status.textContent = message; updateMode();
  }
  function updateMode() {
    for (const [key, item] of buttons) item.setAttribute("aria-pressed", String(key === mode));
    frame.hidden = mode === "list"; reset.hidden = mode !== "3d"; legend.hidden = mode !== "3d";
    list.classList.toggle("office-list-primary", mode === "list");
  }
  async function switchMode(next) {
    if (!alive || !lastData) return;
    mode = next; scene?.dispose(); scene = null;
    const version = ++generation; updateMode();
    if (mode === "list") { view.replaceChildren(); status.textContent = "Erişilebilir liste görünümü"; return; }
    if (mode === "2d") { renderPlan(view, lastData, selectPerson); status.textContent = "2D ofis planı"; return; }
    view.replaceChildren(node("p", "3D ofis hazırlanıyor…", "office-loading"));
    try {
      model ||= Promise.all([import("three"), import("three/addons/controls/OrbitControls.js")]);
      const [THREE, { OrbitControls }] = await model;
      if (!alive || generation !== version || mode !== "3d") return;
      scene = createScene(THREE, OrbitControls, view, lastData, fallback, selectPerson, seenEvents);
      status.textContent = "3D ofis · yerel görünüm"; scene.pause(document.hidden);
    } catch { if (alive && generation === version) fallback("3D bu cihazda açılamadı; 2D plan gösteriliyor."); }
  }
  async function refresh() {
    if (!alive || document.hidden || pending) return;
    pending = true;
    try {
      const [local, central] = await Promise.allSettled([options.api("/api/agents/office"), options.api("/api/agents/central/office")]);
      if (!alive) return;
      if (local.status === "rejected") throw local.reason;
      const data = safeData(local.value);
      const humans = central.status === "fulfilled" && Array.isArray(central.value?.people) ? central.value.people.slice(0, 500) : null;
      data.people = humans || [];
      humanWarning.hidden = humans !== null; humanWarning.textContent = humans === null ? "İnsan çalışanların durumu alınamadı. Kurum bağlantısı yenilendiğinde tekrar gösterilecek." : "";
      lastData = data; updateList(data); updateFeed(data);
      if (selected) {
        const person = population(data).find((item) => item.id === selected);
        if (!person) closePanel();
        else if (person.kind === "human" && !person.can_view_tasks && panel.querySelector(".office-detail-body")) selectPerson(person.id);
        else if (panel.querySelector(".office-detail-live")) panel.querySelector(".office-detail-live").textContent = `${stateName(person)} · ${person.task_label || "Görev bekliyor"}`;
      }
      const key = JSON.stringify([data.departments, population(data).map((p) => [p.id, p.kind, p.role, p.department])]);
      if (shapeKey !== key) { shapeKey = key; await switchMode(mode); }
      else if (mode === "2d") renderPlan(view, data, selectPerson);
      else scene?.update(data);
    } catch (error) { if (alive) { closePanel(); status.textContent = error?.message || "Ofis bilgisi güncellenemedi."; } }
    finally { pending = false; if (alive && !document.hidden) timer = setTimeout(refresh, 3000); }
  }
  function visibility() { clearTimeout(timer); scene?.pause(document.hidden); if (!document.hidden) refresh(); }
  document.addEventListener("visibilitychange", visibility); refresh();
  return () => {
    alive = false; panelVersion++; generation++; clearTimeout(timer); scene?.dispose(); scene = null;
    document.removeEventListener("visibilitychange", visibility); container.classList.remove("office-root");
  };
}

function renderPlan(host, data, selectPerson) {
  const focused = host.contains(document.activeElement) ? document.activeElement.dataset.person : null;
  const create = (tag, attributes, text) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes || {})) element.setAttribute(key, String(value));
    if (text !== undefined) element.textContent = text; return element;
  };
  const areas = rooms(data), seats = seating(data), length = Math.max(18, ...areas.map((r) => r.z + r.depth / 2 + 9));
  const px = (x) => 500 + x * 32, py = (z) => 40 + (z + 8.5) * 24;
  const floor = create("svg", { viewBox: `0 0 1000 ${length * 24 + 80}`, role: "group", "aria-label": "Ofis planı ve çalışan durumları", class: "office-plan" });
  floor.append(create("rect", { x: 20, y: 20, width: 960, height: length * 24 + 40, rx: 24, class: "office-plan-floor" }));
  for (const room of areas) {
    const x = px(room.x) - 125, y = py(room.z - room.depth / 2);
    floor.append(create("rect", { x, y, width: 250, height: room.depth * 24, rx: 12, class: "office-plan-room" }),
      create("text", { x: x + 12, y: y + 24 }, room.name.slice(0, 28)));
  }
  floor.append(create("rect", { x: 398, y: py(-3.8), width: 204, height: 6.2 * 24, rx: 10, class: "office-plan-manager" }),
    create("text", { x: 500, y: py(-2.7), "text-anchor": "middle" }, "Yönetici"));
  const head = seats.find((seat) => seat.person.role === "manager");
  for (const seat of seats) {
    if (!head || seat === head || seat.person.activity !== "asking_manager") continue;
    floor.append(create("line", { x1: px(seat.x), y1: py(seat.z) + 28, x2: px(head.x), y2: py(head.z) + 28, class: "office-plan-link" }),
      create("text", { x: (px(seat.x) + px(head.x)) / 2, y: (py(seat.z) + py(head.z)) / 2 + 22, "text-anchor": "middle", class: "office-plan-link-label" }, "Soru"));
  }
  for (const seat of seats) {
    const person = seat.person, x = px(seat.x), y = py(seat.z);
    floor.append(create("rect", { x: x - 28, y: y - 5, width: 56, height: 22, rx: 4, class: "office-plan-desk" }));
    const mark = create("g", { role: "button", tabindex: "0", id: `rpa-office-plan-person-${++serial}`,
      "aria-label": `${person.name} · ${stateName(person)}`, class: "office-plan-person", "data-status": person.status, "data-activity": person.activity || person.status, "data-person": person.id });
    mark.append(create("circle", { cx: x, cy: y + 28, r: 12 }), create("text", { x, y: y + 34, "text-anchor": "middle", class: "office-plan-symbol" }, symbol(person)),
      create("text", { x, y: y + 59, "text-anchor": "middle", class: "office-plan-name" }, String(person.name).slice(0, 12)));
    mark.addEventListener("click", () => selectPerson(person.id));
    mark.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectPerson(person.id); } });
    floor.append(mark);
  }
  host.replaceChildren(floor); host.dataset.mode = "2d";
  if (focused) [...host.querySelectorAll("[data-person]")].find((item) => item.dataset.person === focused)?.focus({ preventScroll: true });
}

function createScene(THREE, OrbitControls, host, data, fallback, selectPerson, seenEvents) {
  let disposed = false, paused = document.hidden, raf = null, animationTimer = null, slow = 0, frames = 0;
  const paint = [], labels = [], materials = new Set(), geometries = new Set(), characters = new Map(), flights = [];
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5)); renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1;
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene(), camera = new THREE.PerspectiveCamera(37, 1, .1, 3000);
  const canvas = renderer.domElement; canvas.id = `rpa-office-canvas-${++serial}`;
  canvas.tabIndex = 0; canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "3D ofis. Sürükleyerek döndürün, tekerlekle yakınlaştırın. Çalışan adından ayrıntıları açın. Aynı bilgi alttaki tabloda bulunur.");
  const overlay = node("div", undefined, "office-labels"); host.replaceChildren(canvas, overlay); host.dataset.mode = "3d";
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false; controls.enablePan = false; controls.autoRotate = false;
  controls.minDistance = 24; controls.maxDistance = 58; controls.minPolarAngle = .35; controls.maxPolarAngle = 1.2;
  controls.minAzimuthAngle = -.15; controls.maxAzimuthAngle = Math.PI * .72; controls.target.set(0, 0, 1);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)"), colors = palette();
  function motion() {
    controls.rotateSpeed = reduced.matches ? .3 : .65; controls.zoomSpeed = reduced.matches ? .4 : .8;
    if (reduced.matches) { flights.forEach((f) => f.mesh.visible = false); characters.forEach((c) => { c.delivery = null; }); }
    request();
  }
  reduced.addEventListener("change", motion);
  function lampColor(values) {
    const first = new THREE.Color(values["on-solid"]), second = new THREE.Color(values.ink);
    return first.getHSL({}).l > second.getHSL({}).l ? first : second;
  }
  const ambient = new THREE.HemisphereLight(lampColor(colors), colors["surface-3"], 1.8); scene.add(ambient);
  const light = new THREE.DirectionalLight(lampColor(colors), 2.1); light.position.set(8, 16, 10);
  light.castShadow = true; light.shadow.mapSize.set(1024, 1024);
  Object.assign(light.shadow.camera, { left: -22, right: 22, top: 22, bottom: -22, near: 1, far: 65 });
  light.shadow.normalBias = .035; scene.add(light);
  function material(token, options = {}) {
    const value = new THREE.MeshStandardMaterial({ color: colors[token], roughness: .78, ...options });
    materials.add(value); paint.push({ value, token }); return value;
  }
  function recolor(mat, token) { const entry = paint.find((p) => p.value === mat); if (entry) entry.token = token; mat.color.set(palette()[token]); }
  const floorMat = material("surface-2"), edgeMat = material("line-strong"), wallMat = material("surface"),
    deskMat = material("surface"), chairMat = material("accent"), metalMat = material("ink-2"),
    glassMat = material("accent-tint", { transparent: true, opacity: .22, depthWrite: false, roughness: .2 }),
    screenMat = material("ink"), plantMat = material("ok"), zoneMat = material("surface-3"), trimMat = material("accent"),
    humanMat = material("mark"), headMat = material("surface"), bootMat = material("ink"), paperMat = material("on-solid");
  function mesh(geometry, mat, x, y, z, parent = scene) {
    geometries.add(geometry); const object = new THREE.Mesh(geometry, mat); object.position.set(x, y, z);
    object.castShadow = !mat.transparent; object.receiveShadow = !mat.transparent; parent.add(object); return object;
  }
  function box(w, h, d, mat, x, y, z, parent = scene) { return mesh(new THREE.BoxGeometry(w, h, d), mat, x, y, z, parent); }
  function label(text, x, y, z, main = false) {
    const value = node("span", text, `office-room-label${main ? " main" : ""}`); overlay.append(value);
    labels.push({ node: value, point: new THREE.Vector3(x, y, z) });
  }
  function desk(x, z, large = false, ownScreen = screenMat) {
    const width = large ? 3.7 : 2;
    box(width, .15, 1.15, deskMat, x, 1.3, z);
    for (const side of [-1, 1]) box(.1, 1.2, .75, metalMat, x + side * (width / 2 - .16), .65, z);
    box(.8, .52, .09, ownScreen, x, 1.7, z - .26); box(.1, .16, .1, metalMat, x, 1.41, z - .26);
    box(.55, .035, .22, metalMat, x, 1.39, z + .25);
    box(.65, .15, .65, chairMat, x, .78, z + 1.05); box(.65, .55, .14, chairMat, x, 1.1, z + 1.34);
    box(.1, .65, .1, metalMat, x, .36, z + 1.05); box(.65, .08, .65, metalMat, x, .13, z + 1.05);
  }
  function plant(x, z) {
    mesh(new THREE.CylinderGeometry(.32, .24, .55, 6), wallMat, x, .42, z);
    mesh(new THREE.ConeGeometry(.53, 1.15, 5), plantMat, x, 1.2, z);
  }
  const areas = rooms(data), length = Math.max(18, ...areas.map((r) => r.z + r.depth / 2 + 9)), centerZ = length / 2 - 9;
  controls.maxDistance = Math.max(58, length * 2.8);
  box(28.5, .46, length + .6, edgeMat, 0, -.3, centerZ); box(28, .16, length, floorMat, 0, .015, centerZ);
  box(28, 2.9, .24, wallMat, 0, 1.45, -8.8); box(.24, 2.9, length, wallMat, -13.9, 1.45, centerZ);
  for (let x = -12; x <= 12; x += 2) box(.012, .014, length, edgeMat, x, .103, centerZ);
  for (let z = -8; z <= length - 9; z += 2) box(28, .014, .012, edgeMat, 0, .103, z);
  for (const room of areas) {
    box(7.8, .035, room.depth, zoneMat, room.x, .13, room.z);
    box(7.8, .045, .075, trimMat, room.x, .16, room.z - room.depth / 2);
    if (!room.members.length) [-2.5, 0, 2.5].forEach((offset) => desk(room.x + offset, room.z));
    label(room.name, room.x, .35, room.z - room.depth / 2 + .3);
    plant(room.x - 3.45, room.z + room.depth / 2 - .5);
  }
  box(6.2, .055, 6.2, wallMat, 0, .14, -.7);
  for (const x of [-3.1, 3.1]) {
    box(.08, 3.2, 6.2, glassMat, x, 1.72, -.7);
    for (const z of [-3.8, 2.4]) box(.075, 3.35, .075, metalMat, x, 1.78, z);
    box(.09, .075, 6.2, metalMat, x, 3.42, -.7);
  }
  box(6.2, 3.2, .06, glassMat, 0, 1.72, -3.8); box(6.2, .075, .09, metalMat, 0, 3.42, -3.8);
  if (!data.agents.some((a) => a.role === "manager")) desk(0, -.7, true);
  plant(-2.15, -2.65); plant(2.15, -2.65); label("Yönetici odası", 0, 3.9, -1.8, true);
  plant(12.8, -7.65); plant(-12.8, length - 9.8);
  box(3.7, .48, 1.1, chairMat, 0, .53, 6.8); box(3.7, .58, .18, chairMat, 0, 1.04, 7.27);
  box(2.3, .12, .8, deskMat, 0, .7, 5.4); box(.12, .6, .12, metalMat, -.8, .35, 5.4); box(.12, .6, .12, metalMat, .8, .35, 5.4);

  function character(seat) {
    const { person, x, z } = seat, root = new THREE.Group(); scene.add(root); root.position.set(x, .05, z + .95);
    const shirt = person.kind === "human" ? humanMat : chairMat, screen = material("ink"), statusMat = material("accent");
    desk(x, z, seat.large, screen);
    const body = new THREE.Group(); root.add(body);
    mesh(new THREE.CylinderGeometry(.27, .34, .65, 5), shirt, 0, 1.13, 0, body);
    const head = mesh(new THREE.IcosahedronGeometry(.29, 1), headMat, 0, 1.67, 0, body);
    // Small eyes and a badge distinguish the generated office figures without external textures.
    for (const side of [-1, 1]) box(.055, .045, .035, bootMat, side * .10, 1.7, -.27, body);
    box(.10, .15, .025, person.kind === "human" ? chairMat : humanMat, .14, 1.25, -.26, body);
    const arms = [], legs = [];
    for (const side of [-1, 1]) {
      const arm = new THREE.Group(); arm.position.set(side * .34, 1.33, 0); body.add(arm);
      box(.17, .46, .18, shirt, 0, -.18, 0, arm); mesh(new THREE.IcosahedronGeometry(.12, 0), headMat, 0, -.44, 0, arm); arms.push(arm);
      const leg = box(.17, .48, .22, bootMat, side * .17, .53, -.16, root); legs.push(leg);
      box(.19, .14, .32, bootMat, side * .17, .26, -.23, root);
    }
    const ring = mesh(new THREE.TorusGeometry(.52, .035, 5, 20, Math.PI * 1.5), statusMat, x, .25, z + .95);
    ring.rotation.x = Math.PI / 2; ring.visible = false;
    const folder = box(.35, .42, .065, humanMat, -.42, 1.05, -.18, body); folder.visible = false;
    const name = button("", () => selectPerson(person.id)); name.className = "office-person-label";
    name.dataset.person = person.id; overlay.append(name);
    const bubble = node("span", "", "office-person-bubble"), caption = node("span", "", "office-person-name");
    const speech = node("span", "", "office-person-speech"); speech.hidden = true; speech.setAttribute("aria-hidden", "true");
    name.append(speech, bubble, caption);
    const labelItem = { node: name, point: new THREE.Vector3(x, 2.9, z + .95), character: root }; labels.push(labelItem);
    root.traverse((child) => { if (child.isMesh) child.userData.personId = person.id; });
    characters.set(person.id, { root, body, head, arms, legs, folder, ring, screen, statusMat, name, bubble, caption, labelItem,
      speech, said: null, origin: root.position.clone(), person, delivery: null, trip: null });
  }
  seating(data).forEach(character);
  // Balloons show only the message type; the office never receives question or answer texts.
  function say(item, text, duration, stamp) { item.said = { text, until: stamp + duration }; }
  function eventFor(person, stamp) {
    const event = person.event;
    if (!event?.id || seenEvents.has(event.id)) return;
    seenEvents.add(event.id); if (seenEvents.size > 1000) seenEvents.delete(seenEvents.values().next().value);
    const source = characters.get(person.id), destination = characters.get(event.to_agent_id);
    if (!source || !destination) return;
    if (event.kind === "answered") say(source, "Yanıt", 4500, stamp);
    else if (event.kind === "delegated") say(source, "Görev", 3000, stamp);
    else if (event.kind === "completed" && person.status === "succeeded") say(source, "Sonuç", 4500, stamp);
    if (reduced.matches) return;
    if (event.kind === "completed" && person.status === "succeeded") source.delivery = { stamp, target: destination.origin.clone() };
    else if (event.kind === "delegated") {
      const card = box(.65, .45, .06, paperMat, source.origin.x, 2.7, source.origin.z);
      flights.push({ mesh: card, stamp, from: source.origin.clone(), to: destination.origin.clone() });
    }
  }
  function update(next) {
    const stamp = performance.now();
    population(next).forEach((person) => {
      const item = characters.get(person.id); if (!item) return;
      item.person = person; item.caption.textContent = person.name; item.bubble.textContent = symbol(person);
      item.name.dataset.status = person.status; item.name.dataset.activity = person.activity || person.status;
      item.name.setAttribute("aria-label", `${person.name} · ${stateName(person)}`);
      item.name.title = `${person.name} · ${stateName(person)}`;
      const state = person.activity || person.status;
      const token = state === "failed" ? "err" : state === "waiting_approval" ? "warn" : state === "succeeded" ? "ok" : "accent";
      recolor(item.statusMat, token); recolor(item.screen, state === "workflow" ? "ok" : state === "thinking" || state === "running" ? "accent" : "ink");
      item.screen.emissive.set(palette()[state === "workflow" ? "ok" : "ink"]); item.screen.emissiveIntensity = state === "workflow" ? .25 : 0;
      eventFor(person, stamp);
    });
    request();
  }
  const TRIP = 3500;
  function route(item, endX) {
    const side = item.origin.x < 0 ? -4 : 4;
    return [item.origin, new THREE.Vector3(side, .05, item.origin.z), new THREE.Vector3(side, .05, 3.3),
      new THREE.Vector3(endX, .05, 3.3), new THREE.Vector3(endX, .05, 1.9)];
  }
  function askingSlot(item) {
    // Several departments can wait in front of the manager at once; give each a fixed place.
    const waiting = [...characters.values()].filter((other) => (other.person.activity || other.person.status) === "asking_manager");
    const index = Math.max(0, waiting.indexOf(item));
    return (index % 2 ? 1 : -1) * (1.2 + Math.floor(index / 2) * 1.2);
  }
  function walk(item, path, phase, back, stamp, stepping) {
    const piece = Math.min(3, Math.floor(phase * 4)), fraction = phase * 4 - piece;
    item.root.position.lerpVectors(path[piece], path[piece + 1], fraction);
    const direction = path[piece + 1].clone().sub(path[piece]);
    item.root.rotation.y = Math.atan2(-direction.x, -direction.z) + (back ? Math.PI : 0);
    if (stepping) item.legs.forEach((leg, index) => { leg.rotation.x = Math.sin(stamp / 130 + index * Math.PI) * .35; });
  }
  function animate(stamp) {
    let active = false;
    for (const item of characters.values()) {
      const state = item.person.activity || item.person.status, moving = !reduced.matches;
      item.root.position.copy(item.origin); item.root.rotation.y = 0; item.body.position.y = 0; item.head.rotation.z = 0;
      item.arms[0].rotation.set(0, 0, 0); item.arms[1].rotation.set(0, 0, 0); item.legs.forEach((leg) => { leg.rotation.x = 0; });
      item.ring.visible = state === "workflow"; item.ring.rotation.z = moving ? stamp / 1300 : 0;
      item.folder.visible = Boolean(item.delivery) && moving;
      if (state === "waiting_approval") {
        item.body.position.y = moving ? Math.sin(stamp / 600) * .025 : 0;
        item.arms[1].rotation.z = -2.35; item.head.rotation.z = moving ? Math.sin(stamp / 650) * .04 : 0; active ||= moving;
      } else if (["thinking", "running", "workflow"].includes(state)) {
        item.arms.forEach((arm, index) => { arm.rotation.x = -.55 + (moving && state === "workflow" ? Math.sin(stamp / 180 + index) * .08 : 0); });
        item.body.position.y = moving ? Math.sin(stamp / 850) * .025 : 0; active ||= moving;
      }
      const asking = state === "asking_manager";
      const speech = asking ? "Soru" : item.said && item.said.until > stamp ? item.said.text : "";
      if (item.said && item.said.until <= stamp) item.said = null;
      item.speech.textContent = speech; item.speech.hidden = !speech; active ||= Boolean(item.said);
      if (asking && moving && !item.trip) {
        item.trip = { out: true, stamp, route: route(item, askingSlot(item)) }; item.delivery = null;
      } else if (item.trip?.out && (!asking || !moving)) {
        const reached = Math.min(1, (stamp - item.trip.stamp) / TRIP);
        item.trip = { ...item.trip, out: false, stamp: stamp - (1 - reached) * TRIP };
      }
      if (item.trip) {
        const elapsed = (stamp - item.trip.stamp) / TRIP, phase = item.trip.out ? Math.min(1, elapsed) : 1 - elapsed;
        if ((!item.trip.out && phase <= 0) || !moving) item.trip = null;
        else {
          walk(item, item.trip.route, phase, !item.trip.out, stamp, phase < 1);
          if (phase >= 1) item.root.rotation.y = 0;
          active ||= phase < 1;
        }
      }
      if (item.delivery && moving && !item.trip) {
        const progress = (stamp - item.delivery.stamp) / 8000;
        if (progress >= 1) { item.delivery = null; item.folder.visible = false; }
        else {
          // Walk to the open front of the manager room, then return to the same desk.
          const phase = progress < .5 ? progress * 2 : (1 - progress) * 2;
          walk(item, route(item, 0), phase, progress >= .5, stamp, true); active = true;
        }
      }
      item.labelItem.point.copy(item.root.position).add(new THREE.Vector3(0, 2.85, 0));
    }
    for (let index = flights.length - 1; index >= 0; index--) {
      const flight = flights[index], progress = (stamp - flight.stamp) / 2400;
      if (progress >= 1 || reduced.matches) {
        scene.remove(flight.mesh); flight.mesh.geometry.dispose(); geometries.delete(flight.mesh.geometry); flights.splice(index, 1);
      } else {
        flight.mesh.position.lerpVectors(flight.from, flight.to, progress); flight.mesh.position.y = 2.8 + Math.sin(progress * Math.PI) * 2;
        flight.mesh.rotation.y = progress * Math.PI * 2; active = true;
      }
    }
    return active;
  }
  function theme() {
    const next = palette(); scene.background = new THREE.Color(next.bg); paint.forEach(({ value, token }) => value.color.set(next[token]));
    characters.forEach((item) => item.screen.emissive.set(next[item.person.activity === "workflow" ? "ok" : "ink"]));
    ambient.color.copy(lampColor(next)); ambient.groundColor.set(next["surface-3"]); light.color.copy(lampColor(next)); request();
  }
  function render(stamp) {
    raf = null; if (disposed || paused || document.hidden) return;
    const start = performance.now(), active = animate(stamp); renderer.render(scene, camera);
    const width = host.clientWidth, height = host.clientHeight;
    for (const item of labels) {
      const p = item.point.clone().project(camera);
      item.node.style.transform = `translate(-50%, -50%) translate(${(p.x + 1) * width / 2}px, ${(-p.y + 1) * height / 2}px)`;
      item.node.hidden = p.z < -1 || p.z > 1;
    }
    frames++; slow = frames > 3 && performance.now() - start > 100 ? slow + 1 : 0;
    if (slow >= 6) { fallback("Bu cihazda daha akıcı görüntü için 2D plana geçildi."); return; }
    if (active) animationTimer = setTimeout(() => { animationTimer = null; request(); }, 42);
  }
  function request() {
    clearTimeout(animationTimer); animationTimer = null;
    if (!disposed && !paused && !document.hidden && raf === null) raf = requestAnimationFrame(render);
  }
  function resize() {
    if (disposed) return;
    const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix(); request();
  }
  function reset() {
    const scale = Math.max(1, length / 22); camera.position.set(23 * scale, 24 * scale, centerZ + 29 * scale);
    controls.target.set(0, 0, centerZ); controls.update(); request();
  }
  function lost(event) { event.preventDefault(); fallback("3D görüntü kesildi; 2D plan gösteriliyor."); }
  let pointerStart = null;
  const raycaster = new THREE.Raycaster();
  function pointerDown(event) { pointerStart = { x: event.clientX, y: event.clientY }; }
  function pointerUp(event) {
    if (!pointerStart || Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 6) return;
    pointerStart = null; const rect = canvas.getBoundingClientRect();
    raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, 1 - (event.clientY - rect.top) / rect.height * 2), camera);
    const hits = raycaster.intersectObjects([...characters.values()].map((item) => item.root), true);
    if (hits[0]?.object.userData.personId) selectPerson(hits[0].object.userData.personId);
  }
  canvas.addEventListener("webglcontextlost", lost); canvas.addEventListener("pointerdown", pointerDown); canvas.addEventListener("pointerup", pointerUp);
  controls.addEventListener("change", request);
  const observer = new ResizeObserver(resize); observer.observe(host);
  const themes = new MutationObserver(theme); themes.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  motion(); reset(); resize(); theme(); update(data);
  return { reset, update, pause(value) {
    paused = value; if (paused) { cancelAnimationFrame(raf); raf = null; clearTimeout(animationTimer); animationTimer = null; } else request();
  }, dispose() {
    if (disposed) return; disposed = true; cancelAnimationFrame(raf); clearTimeout(animationTimer);
    observer.disconnect(); themes.disconnect(); reduced.removeEventListener("change", motion);
    controls.removeEventListener("change", request); controls.dispose();
    canvas.removeEventListener("webglcontextlost", lost); canvas.removeEventListener("pointerdown", pointerDown); canvas.removeEventListener("pointerup", pointerUp);
    geometries.forEach((item) => item.dispose()); materials.forEach((item) => item.dispose()); light.shadow.dispose();
    renderer.dispose(); renderer.forceContextLoss(); canvas.remove(); overlay.remove();
  } };
}

window.RpaAgents.registerTab({ id: "office", label: "Ofis", mount: mountOffice });
