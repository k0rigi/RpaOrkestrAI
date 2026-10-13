"use strict";

// An intentionally empty office preview. Characters and task animations are a later stage.
let serial = 0;
const states = { idle: "Boşta", queued: "Sırada", running: "Çalışıyor", waiting_user: "Yanıt bekliyor",
  waiting_approval: "Onay bekliyor", succeeded: "Tamamlandı", failed: "Hata", cancelled: "Durduruldu" };

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
    "accent", "accent-tint", "ok", "muted", "mark", "on-solid"].map((key) => [key, style.getPropertyValue(`--${key}`).trim()]));
}
function rooms(data) {
  const departments = data.departments.slice(0, 6);
  if (!departments.length) return [{ name: "Departman alanı", x: -8, z: -4 }, { name: "Departman alanı", x: 8, z: -4 },
    { name: "Departman alanı", x: -8, z: 4 }, { name: "Departman alanı", x: 8, z: 4 }];
  const points = [[-8, -5], [8, -5], [-8, 3], [8, 3], [-8, 10], [8, 10]];
  return departments.map((department, index) => ({ name: department.name, x: points[index][0], z: points[index][1] }));
}
function safeData(value) {
  if (!value || !Array.isArray(value.agents) || !Array.isArray(value.departments)) throw new Error("Ofis durumu okunamadı.");
  return { agents: value.agents.slice(0, 500), departments: value.departments.slice(0, 100), totals: value.totals || {} };
}

export function mountOffice(container, options) {
  let alive = true, mode = "3d", model = null, timer = null, pending = false, scene = null, generation = 0;
  let shapeKey = "", lastData = null;
  const title = node("div", undefined, "office-title");
  title.append(node("p", "DİJİTAL EKİP", "agent-eyebrow"), node("h2", "Ofis"),
    node("p", "Birlikte çalışacağınız alanın ilk görünümü", "muted"));
  const toolbar = node("div", undefined, "office-toolbar");
  const status = node("span", "Yükleniyor…", "office-mode-label"); status.setAttribute("role", "status");
  const controls = node("div", undefined, "agent-actions");
  const buttons = new Map();
  for (const [key, text] of [["3d", "3D görünüm"], ["2d", "2D plan"], ["list", "Liste"]]) {
    const item = button(text, () => switchMode(key)); buttons.set(key, item); controls.append(item);
  }
  const reset = button("Kamerayı sıfırla", () => scene?.reset()); controls.append(reset);
  toolbar.append(status, controls);
  const frame = node("div", undefined, "office-frame");
  const view = node("div", undefined, "office-view");
  const loading = node("p", "Ofis hazırlanıyor…", "office-loading"); view.append(loading);
  const preview = node("span", "BOŞ OFİS ÖNİZLEMESİ", "office-preview");
  const legend = node("p", "Sürükleyin: döndür · Tekerlek: yakınlaştır", "office-legend");
  frame.append(view, preview, legend);
  const note = node("p", "Bu önizlemede yalnız ofis planı gösterilir. Ajan karakterleri ve hareketleri sonraki aşamada eklenecek.", "agent-help");
  const summary = node("p", "", "office-summary");
  const list = node("div", undefined, "office-list");
  container.replaceChildren(title, toolbar, frame, summary, note, list);
  container.classList.add("office-root");

  function updateList(data) {
    const headings = ["Ajan", "Departman", "Durum", "Görev", "Sırada"];
    const table = node("table", undefined, "office-table");
    const caption = node("caption", "Ajanların anlık durumu");
    const head = node("thead"), row = node("tr");
    headings.forEach((label) => { const cell = node("th", label); cell.scope = "col"; row.append(cell); });
    head.append(row); const body = node("tbody");
    for (const agent of data.agents) {
      const item = node("tr");
      const values = [agent.name, agent.role === "manager" ? "Yönetim" : agent.department,
        states[agent.status] || "Bilinmiyor", agent.task_label || "Görev bekliyor", Number(agent.queue_count) || 0];
      values.forEach((value) => item.append(node("td", value))); body.append(item);
    }
    if (!data.agents.length) {
      const item = node("tr"), cell = node("td", "Henüz ajan eklenmedi. Ofis, departmanlarınız tanımlandıkça düzenlenir.");
      cell.colSpan = headings.length; item.append(cell); body.append(item);
    }
    table.append(caption, head, body); list.replaceChildren(table);
    summary.textContent = `${data.agents.length} ajan · ${data.departments.length} departman · ${Number(data.totals.queued) || 0} görev sırada`;
  }
  function fallback(message) {
    if (!alive) return;
    mode = "2d"; scene?.dispose(); scene = null; generation++;
    renderPlan(view, lastData || { departments: [] });
    status.textContent = message; updateMode();
  }
  function updateMode() {
    for (const [key, item] of buttons) item.setAttribute("aria-pressed", String(key === mode));
    frame.hidden = mode === "list"; reset.hidden = mode !== "3d";
    legend.hidden = mode !== "3d";
    list.classList.toggle("office-list-primary", mode === "list");
  }
  async function switchMode(next) {
    if (!alive || !lastData) return;
    mode = next; scene?.dispose(); scene = null;
    const version = ++generation; updateMode();
    if (mode === "list") { view.replaceChildren(); status.textContent = "Erişilebilir liste görünümü"; return; }
    if (mode === "2d") { renderPlan(view, lastData); status.textContent = "2D ofis planı"; return; }
    view.replaceChildren(node("p", "3D ofis hazırlanıyor…", "office-loading"));
    try {
      model ||= Promise.all([import("three"), import("three/addons/controls/OrbitControls.js")]);
      const [THREE, { OrbitControls }] = await model;
      if (!alive || generation !== version || mode !== "3d") return;
      scene = createScene(THREE, OrbitControls, view, lastData, fallback);
      status.textContent = "3D ofis · yerel görünüm";
      scene.pause(document.hidden);
    } catch {
      if (alive && generation === version) fallback("3D bu cihazda açılamadı; 2D plan gösteriliyor.");
    }
  }
  async function refresh() {
    if (!alive || document.hidden || pending) return;
    pending = true;
    try {
      const data = safeData(await options.api("/api/agents/office"));
      if (!alive) return;
      lastData = data; updateList(data);
      const key = JSON.stringify(data.departments);
      if (shapeKey !== key) { shapeKey = key; await switchMode(mode); }
    } catch (error) {
      if (alive) status.textContent = error?.message || "Ofis bilgisi güncellenemedi.";
    } finally {
      pending = false;
      if (alive && !document.hidden) timer = setTimeout(refresh, 3000);
    }
  }
  function visibility() {
    clearTimeout(timer); scene?.pause(document.hidden);
    if (!document.hidden) refresh();
  }
  document.addEventListener("visibilitychange", visibility);
  refresh();
  return () => {
    alive = false; generation++; clearTimeout(timer); scene?.dispose(); scene = null;
    document.removeEventListener("visibilitychange", visibility);
    container.classList.remove("office-root");
  };
}

function renderPlan(host, data) {
  const create = (tag, attributes, text) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes || {})) element.setAttribute(key, String(value));
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const floor = create("svg", { viewBox: "0 0 1000 650", role: "img", "aria-label": "Boş ofis planı: ortada yönetici odası, çevresinde departman alanları", class: "office-plan" });
  floor.append(create("rect", { x: 20, y: 20, width: 960, height: 610, rx: 24, class: "office-plan-floor" }));
  for (const room of rooms(data)) {
    const x = room.x < 0 ? 50 : 675, y = 70 + (room.z + 5) * 26;
    floor.append(create("rect", { x, y, width: 275, height: 150, rx: 12, class: "office-plan-room" }),
      create("text", { x: x + 18, y: y + 30 }, room.name.slice(0, 30)));
    for (let index = 0; index < 3; index++) {
      floor.append(create("rect", { x: x + 22 + index * 82, y: y + 65, width: 64, height: 33, rx: 4, class: "office-plan-desk" }),
        create("rect", { x: x + 40 + index * 82, y: y + 110, width: 27, height: 21, rx: 5, class: "office-plan-chair" }));
    }
  }
  floor.append(create("rect", { x: 365, y: 205, width: 270, height: 240, rx: 10, class: "office-plan-manager" }),
    create("text", { x: 500, y: 240, "text-anchor": "middle" }, "Yönetici odası"),
    create("rect", { x: 420, y: 305, width: 160, height: 65, rx: 6, class: "office-plan-desk" }),
    create("rect", { x: 474, y: 380, width: 52, height: 35, rx: 8, class: "office-plan-chair" }));
  host.replaceChildren(floor); host.dataset.mode = "2d";
}

function createScene(THREE, OrbitControls, host, data, fallback) {
  let disposed = false, paused = document.hidden, raf = null, slow = 0, frames = 0;
  const paint = [], labels = [], materials = new Set(), geometries = new Set();
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(37, 1, .1, 150);
  const canvas = renderer.domElement; canvas.id = `rpa-office-canvas-${++serial}`;
  canvas.tabIndex = 0; canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", "Boş 3D ofis. Sürükleyerek döndürün, tekerlekle yakınlaştırın. Aynı bilgi alttaki tabloda bulunur.");
  const overlay = node("div", undefined, "office-labels");
  host.replaceChildren(canvas, overlay); host.dataset.mode = "3d";
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = false; controls.enablePan = false; controls.autoRotate = false;
  controls.minDistance = 24; controls.maxDistance = 58; controls.minPolarAngle = .35; controls.maxPolarAngle = 1.2;
  controls.minAzimuthAngle = -.15; controls.maxAzimuthAngle = Math.PI * .72;
  controls.target.set(0, 0, 1);
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  function motion() { controls.rotateSpeed = reduced.matches ? .3 : .65; controls.zoomSpeed = reduced.matches ? .4 : .8; }
  motion(); reduced.addEventListener("change", motion);
  const colors = palette();
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
  const floorMat = material("surface-2"), edgeMat = material("line-strong"), wallMat = material("surface"),
    deskMat = material("surface"), chairMat = material("accent"), metalMat = material("ink-2"),
    glassMat = material("accent-tint", { transparent: true, opacity: .28, depthWrite: false, roughness: .2 }),
    screenMat = material("ink"), plantMat = material("ok"), zoneMat = material("surface-3"), trimMat = material("accent");
  function mesh(geometry, mat, x, y, z) {
    geometries.add(geometry); const object = new THREE.Mesh(geometry, mat); object.position.set(x, y, z);
    object.castShadow = !mat.transparent; object.receiveShadow = !mat.transparent; scene.add(object); return object;
  }
  function box(w, h, d, mat, x, y, z) { return mesh(new THREE.BoxGeometry(w, h, d), mat, x, y, z); }
  function label(text, x, y, z, main = false) {
    const value = node("span", text, `office-room-label${main ? " main" : ""}`); overlay.append(value);
    labels.push({ node: value, point: new THREE.Vector3(x, y, z) });
  }
  function desk(x, z, large = false) {
    const width = large ? 3.7 : 2.0;
    box(width, .15, 1.15, deskMat, x, 1.3, z);
    for (const side of [-1, 1]) box(.1, 1.2, .75, metalMat, x + side * (width / 2 - .16), .65, z);
    box(.8, .52, .09, screenMat, x, 1.7, z - .26); box(.1, .16, .1, metalMat, x, 1.41, z - .26);
    box(.55, .035, .22, metalMat, x, 1.39, z + .25);
    box(.65, .15, .65, chairMat, x, .78, z + 1.05); box(.65, .55, .14, chairMat, x, 1.1, z + 1.34);
    box(.1, .65, .1, metalMat, x, .36, z + 1.05); box(.65, .08, .65, metalMat, x, .13, z + 1.05);
  }
  function plant(x, z) {
    mesh(new THREE.CylinderGeometry(.32, .24, .55, 6), wallMat, x, .42, z);
    mesh(new THREE.ConeGeometry(.53, 1.15, 5), plantMat, x, 1.2, z);
  }
  const length = data.departments.length > 4 ? 24 : 18, centerZ = length > 18 ? 3 : 0;
  box(28.5, .46, length + .6, edgeMat, 0, -.3, centerZ);
  box(28, .16, length, floorMat, 0, .015, centerZ);
  box(28, 2.9, .24, wallMat, 0, 1.45, -8.8);
  box(.24, 2.9, length, wallMat, -13.9, 1.45, centerZ);
  for (let x = -12; x <= 12; x += 2) box(.012, .014, length, edgeMat, x, .103, centerZ);
  for (let z = -8; z <= length - 9; z += 2) box(28, .014, .012, edgeMat, 0, .103, z);
  for (const room of rooms(data)) {
    box(7.8, .035, 5.4, zoneMat, room.x, .13, room.z);
    box(7.8, .045, .075, trimMat, room.x, .16, room.z - 2.7);
    [-2.5, 0, 2.5].forEach((offset) => desk(room.x + offset, room.z));
    label(room.name, room.x, .35, room.z - 2.45);
    plant(room.x - 3.45, room.z + 2.05);
  }
  box(6.2, .055, 6.2, wallMat, 0, .14, -.7);
  for (const x of [-3.1, 3.1]) {
    box(.08, 3.2, 6.2, glassMat, x, 1.72, -.7);
    for (const z of [-3.8, 2.4]) box(.075, 3.35, .075, metalMat, x, 1.78, z);
    box(.09, .075, 6.2, metalMat, x, 3.42, -.7);
  }
  box(6.2, 3.2, .06, glassMat, 0, 1.72, -3.8); box(6.2, .075, .09, metalMat, 0, 3.42, -3.8);
  desk(0, -.7, true); plant(-2.15, -2.65); plant(2.15, -2.65);
  label("Yönetici odası", 0, 3.9, -1.8, true);
  plant(12.8, -7.65); plant(-12.8, 7.8);
  // A meeting bench anchors the entrance; no characters or movement are included.
  box(3.7, .48, 1.1, chairMat, 0, .53, 6.8); box(3.7, .58, .18, chairMat, 0, 1.04, 7.27);
  box(2.3, .12, .8, deskMat, 0, .7, 5.4); box(.12, .6, .12, metalMat, -.8, .35, 5.4); box(.12, .6, .12, metalMat, .8, .35, 5.4);
  function theme() {
    const next = palette(); scene.background = new THREE.Color(next.bg);
    paint.forEach(({ value, token }) => value.color.set(next[token]));
    ambient.color.copy(lampColor(next)); ambient.groundColor.set(next["surface-3"]); light.color.copy(lampColor(next));
    request();
  }
  function render() {
    raf = null; if (disposed || paused || document.hidden) return;
    const start = performance.now(); renderer.render(scene, camera);
    const width = host.clientWidth, height = host.clientHeight;
    for (const item of labels) {
      const p = item.point.clone().project(camera);
      item.node.style.transform = `translate(-50%, -50%) translate(${(p.x + 1) * width / 2}px, ${(-p.y + 1) * height / 2}px)`;
      item.node.hidden = p.z < -1 || p.z > 1;
    }
    frames++; slow = frames > 3 && performance.now() - start > 100 ? slow + 1 : 0;
    if (slow >= 6) fallback("Bu cihazda daha akıcı görüntü için 2D plana geçildi.");
  }
  function request() { if (!disposed && !paused && !document.hidden && raf === null) raf = requestAnimationFrame(render); }
  function resize() {
    if (disposed) return;
    const width = Math.max(1, host.clientWidth), height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix(); request();
  }
  function reset() { camera.position.set(23, 24, 29); controls.target.set(0, 0, centerZ); controls.update(); request(); }
  function lost(event) { event.preventDefault(); fallback("3D görüntü kesildi; 2D plan gösteriliyor."); }
  canvas.addEventListener("webglcontextlost", lost);
  controls.addEventListener("change", request);
  const observer = new ResizeObserver(resize); observer.observe(host);
  const themes = new MutationObserver(theme); themes.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  reset(); resize(); theme();
  return { reset, pause(value) { paused = value; if (paused) { cancelAnimationFrame(raf); raf = null; } else request(); },
    dispose() {
      if (disposed) return; disposed = true; cancelAnimationFrame(raf);
      observer.disconnect(); themes.disconnect(); reduced.removeEventListener("change", motion);
      controls.removeEventListener("change", request); controls.dispose(); canvas.removeEventListener("webglcontextlost", lost);
      geometries.forEach((item) => item.dispose()); materials.forEach((item) => item.dispose());
      light.shadow.dispose();
      renderer.dispose(); renderer.forceContextLoss(); canvas.remove(); overlay.remove();
    } };
}

window.RpaAgents.registerTab({ id: "office", label: "Ofis", mount: mountOffice });
