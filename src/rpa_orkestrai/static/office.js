"use strict";

// The scene consumes only status DTOs. Business details are requested after selection.
let serial = 0;
const states = { idle: "Boşta", queued: "Sırada", running: "Çalışıyor", waiting_user: "Yanıt bekliyor",
  waiting_approval: "Onay bekliyor", succeeded: "Tamamlandı", failed: "Hata", cancelled: "Durduruldu", unknown: "Durum paylaşılmıyor" };
const activityNames = { thinking: "Düşünüyor", workflow: "Akış çalıştırıyor", asking_manager: "Yöneticiye soru soruyor",
  reviewing: "Departman sorusunu yanıtlıyor", researching: "İnternette araştırıyor" };
function stateName(person) { return activityNames[person.activity] || states[person.status] || "Bilinmiyor"; }
function symbol(person) { return ({ thinking: "…", workflow: "↻", waiting_approval: "!", waiting_user: "?", asking_manager: "?", reviewing: "✎", researching: "⌕",
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
  const office = typeof value.office_name === "string" ? value.office_name.slice(0, 120) : "";
  return { agents: value.agents.slice(0, 500), people: [], departments: value.departments.slice(0, 100), totals: value.totals || {}, office };
}

// The person's own office model: a GLB that follows the RPA layout contract, kept on this computer only.
const MODEL_LIMIT = 100_000_000;
const PLACEMENT = { cut_height: 0 };
const CUT_RANGE = [0, 100];
// The generated figures face -Z; a layout point's local +Z is the direction the person faces, so they turn by π.
const CHARACTER_FORWARD = Math.PI;
// The figure's soles lie this far above its origin; a layout point marks the sole level.
const SOLE = .19;
// Seated pose: the thighs' lower side above the origin, the shin length and how far the pelvis sits forward.
const THIGH_UNDERSIDE = .66, SHIN = .24, SEAT_FORWARD = .12;
const WALK_SPEED = 1.4, MAX_TRIP = 6000;
const PLACE_NAMES = { work: "Çalışma noktası", wait: "Bekleme noktası", manager: "Yönetici noktası" };
// Older exporters (e.g. SimLab) write the retired specular-glossiness materials; they are shown as matte standard ones.
function specularGlossiness(THREE) {
  return (parser) => ({ name: "KHR_materials_pbrSpecularGlossiness", extendMaterialParams(index, params) {
    const value = parser.json.materials?.[index]?.extensions?.KHR_materials_pbrSpecularGlossiness;
    if (!value) return Promise.resolve();
    const diffuse = Array.isArray(value.diffuseFactor) ? value.diffuseFactor : [1, 1, 1, 1];
    params.color.setRGB(diffuse[0] ?? 1, diffuse[1] ?? 1, diffuse[2] ?? 1, THREE.LinearSRGBColorSpace);
    params.opacity = diffuse[3] ?? 1; params.metalness = 0;
    params.roughness = Math.min(1, Math.max(.35, 1 - (typeof value.glossinessFactor === "number" ? value.glossinessFactor : 1)));
    return value.diffuseTexture ? parser.assignTexture(params, "map", value.diffuseTexture, THREE.SRGBColorSpace) : Promise.resolve();
  } });
}
// Thousands of exported parts become one mesh per material, so turning the office stays smooth.
function bake(THREE, mergeGeometries, root) {
  const getters = ["getX", "getY", "getZ", "getW"], names = ["position", "normal", "uv", "uv1", "color"];
  const groups = new Map(), matrix = new THREE.Matrix4(), group = new THREE.Group(), materials = new Set();
  function copy(source, transform) {
    const geometry = new THREE.BufferGeometry();
    for (const name of names) {
      const attribute = source.getAttribute(name);
      if (!attribute) continue;
      const size = attribute.itemSize, values = new Float32Array(attribute.count * size);
      for (let i = 0; i < attribute.count; i++) for (let c = 0; c < size; c++) values[i * size + c] = attribute[getters[c]](i);
      geometry.setAttribute(name, new THREE.BufferAttribute(values, size));
    }
    const index = new Uint32Array(source.index ? source.index.count : geometry.getAttribute("position").count);
    for (let i = 0; i < index.length; i++) index[i] = source.index ? source.index.getX(i) : i;
    // A mirrored part turns inside out once its mirror is baked into the vertices; keep the triangles facing out.
    if (transform.determinant() < 0) for (let i = 0; i + 2 < index.length; i += 3) [index[i + 1], index[i + 2]] = [index[i + 2], index[i + 1]];
    geometry.setIndex(new THREE.BufferAttribute(index, 1));
    if (!geometry.getAttribute("normal")) geometry.computeVertexNormals();
    return geometry.applyMatrix4(transform);
  }
  root.updateMatrixWorld(true);
  root.traverseVisible((object) => {
    if (!object.isMesh || Array.isArray(object.material) || !object.geometry?.getAttribute("position")) return;
    const copies = object.isInstancedMesh ? Math.min(object.count, 10000) : 1;
    for (let i = 0; i < copies; i++) {
      if (object.isInstancedMesh) { object.getMatrixAt(i, matrix); matrix.premultiply(object.matrixWorld); } else matrix.copy(object.matrixWorld);
      const geometry = copy(object.geometry, matrix);
      const key = `${object.material.uuid}|${Object.entries(geometry.attributes).map(([name, value]) => name + value.itemSize).sort().join(",")}`;
      if (!groups.has(key)) groups.set(key, { material: object.material, parts: [] });
      groups.get(key).parts.push(geometry);
    }
  });
  root.traverse((object) => object.geometry?.dispose());
  const plane = new THREE.Plane(new THREE.Vector3(0, -1, 0), 1e6);
  for (const { material, parts } of groups.values()) {
    material.clippingPlanes = [plane]; material.clipShadows = true; materials.add(material);
    const merged = parts.length > 1 ? mergeGeometries(parts, false) : parts[0];
    for (const geometry of merged ? [merged] : parts) {
      const mesh = new THREE.Mesh(geometry, material); mesh.receiveShadow = true; group.add(mesh);
    }
    if (merged && parts.length > 1) parts.forEach((part) => part.dispose());
  }
  const box = new THREE.Box3().setFromObject(group);
  if (box.isEmpty()) throw new Error("Modelde görüntülenecek bir şekil bulunamadı.");
  return { group, box, plane, dispose() {
    group.children.forEach((mesh) => mesh.geometry.dispose());
    for (const material of materials) {
      Object.values(material).forEach((value) => { if (value?.isTexture) value.dispose(); });
      material.dispose();
    }
  } };
}
// Exported for the browser tests that open sample models; the page itself only uses mountOffice.
export async function openModel(THREE, buffer) {
  const [{ GLTFLoader }, { mergeGeometries }] = await Promise.all([import("three/addons/loaders/GLTFLoader.js"),
    import("three/addons/utils/BufferGeometryUtils.js")]);
  const loader = new GLTFLoader(); loader.register(specularGlossiness(THREE));
  return bake(THREE, mergeGeometries, (await loader.parseAsync(buffer, "")).scene);
}
// The shortest walk on the model's path network; only the links the model declares are walkable.
export function shortestPath(layout, from, to) {
  if (!layout.points[from] || !layout.points[to]) return null;
  if (from === to) return [from];
  const neighbours = new Map();
  for (const [first, second] of layout.edges) {
    if (!neighbours.has(first)) neighbours.set(first, []);
    if (!neighbours.has(second)) neighbours.set(second, []);
    neighbours.get(first).push(second); neighbours.get(second).push(first);
  }
  const at = (name) => layout.points[name].position;
  const distance = (a, b) => Math.hypot(at(a)[0] - at(b)[0], at(a)[1] - at(b)[1], at(a)[2] - at(b)[2]);
  const best = new Map([[from, 0]]), previous = new Map(), open = new Set([from]);
  while (open.size) {
    let current = null;
    for (const name of open) if (current === null || best.get(name) < best.get(current)) current = name;
    open.delete(current);
    if (current === to) break;
    for (const next of neighbours.get(current) || []) {
      const cost = best.get(current) + distance(current, next);
      if (!best.has(next) || cost < best.get(next)) { best.set(next, cost); previous.set(next, current); open.add(next); }
    }
  }
  if (!best.has(to)) return null;
  const result = [to];
  while (result[0] !== from) result.unshift(previous.get(result[0]));
  return result;
}
function occupants(data) {
  return population(data).map((person) => ({ id: person.id, role: person.kind === "human" ? "human" : person.role === "manager" ? "manager" : "department",
    department: String(person.department || "").slice(0, 120) }));
}
function requestId() {
  const bytes = new Uint8Array(16); crypto.getRandomValues(bytes);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
}
function field(label, control) {
  control.id = `rpa-office-field-${++serial}`;
  const wrapper = node("div", undefined, "agent-field"), caption = node("label", label); caption.htmlFor = control.id;
  wrapper.append(caption, control); return wrapper;
}

export function mountOffice(container, options) {
  let alive = true, mode = "3d", model = null, timer = null, pending = false, scene = null, generation = 0;
  let shapeKey = "", lastData = null, selected = null, panelVersion = 0, humansLoaded = false;
  let modelInfo = null, modelState = { id: null, promise: null, value: null }, modelNotice = "", placeTimer = null;
  // The layout and everybody's place are read again only when the people or the model change, never for a view switch.
  let placement = { ...PLACEMENT }, layoutState = null, layoutStale = true, layoutReading = null, layoutSerial = 0;
  let demo = null;
  const session = options.session || null;
  const seenEvents = new Set();
  const title = node("div", undefined, "office-title");
  // A firm split into departments shows the account's own office; other departments' offices stay private.
  const heading = node("h2", "Ofis");
  title.append(node("p", "DİJİTAL EKİP", "agent-eyebrow"), heading,
    node("p", "Ajanlarınız ve çalışma arkadaşlarınız aynı ofiste", "muted"));
  const toolbar = node("div", undefined, "office-toolbar");
  const status = node("span", "Yükleniyor…", "office-mode-label"); status.setAttribute("role", "status");
  const controls = node("div", undefined, "agent-actions");
  const buttons = new Map();
  for (const [key, text] of [["3d", "3D görünüm"], ["2d", "2D plan"], ["list", "Liste"]]) {
    const item = button(text, () => switchMode(key)); buttons.set(key, item); controls.append(item);
  }
  const reset = button("Kamerayı sıfırla", () => scene?.reset());
  // The head of the office is one click away: the manager agent's panel opens on its question form.
  const managerButton = button("Yöneticiye yaz", () => {
    const manager = lastData?.agents.find((item) => item.role === "manager");
    if (manager) selectPerson(manager.id, "chat");
  });
  managerButton.hidden = true;
  // A short show on screen only: the office's own manager and departments act out the whole chain of work.
  const demoButton = button("Gösterimi oynat", () => (demo ? stopDemo() : startDemo()));
  demoButton.title = "Ajanların görev, soru, araştırma ve sonuç teslimini 3D'de canlandırır; gerçek iş yapılmaz.";
  const modelButton = button("Ofis modeli", () => toggleModel(modelPanel.hidden));
  const modelPanel = node("section", undefined, "office-model"); modelPanel.id = `rpa-office-model-${++serial}`; modelPanel.hidden = true;
  modelPanel.setAttribute("aria-label", "Kendi ofis modeliniz");
  modelButton.setAttribute("aria-expanded", "false"); modelButton.setAttribute("aria-controls", modelPanel.id);
  controls.append(reset, managerButton, demoButton, modelButton); toolbar.append(status, controls);
  const frame = node("div", undefined, "office-frame"), view = node("div", undefined, "office-view");
  view.append(node("p", "Ofis hazırlanıyor…", "office-loading"));
  const preview = node("span", "CANLI OFİS", "office-preview");
  const legend = node("p", "Sürükleyin: döndür · Tekerlek: yakınlaştır · Karaktere tıklayın: ayrıntı ve işlemler · Balonlar: Görev, Soru, Yanıt, Sonuç, Araştırıyor", "office-legend");
  const capacity = node("p", "", "office-capacity"); capacity.hidden = true; capacity.setAttribute("role", "status");
  frame.append(view, preview, capacity, legend);
  const panel = node("aside", undefined, "office-detail"); panel.hidden = true; panel.setAttribute("aria-label", "Çalışan ayrıntısı");
  const layout = node("div", undefined, "office-layout"); layout.append(frame, panel);
  const note = node("p", session ? "Bir çalışana tıklayıp görev verebilir, ajana soru sorabilir, bekleyen soruyu yanıtlayabilir ve onay yetkiniz varsa onay verebilirsiniz. Departman ajanları birbirleriyle doğrudan konuşmaz; görev, soru ve sonuçlar yönetici üzerinden akar. Balonlarda yalnız mesajın türü görünür."
    : "Departman ajanları birbirleriyle doğrudan konuşmaz; görev, soru ve sonuçlar yönetici üzerinden akar. Balonlarda yalnız mesajın türü görünür, içeriği ofise taşınmaz; ayrıntı için bir çalışan seçin.", "agent-help");
  const humanWarning = node("p", "", "agent-warning office-human-warning"); humanWarning.hidden = true; humanWarning.setAttribute("role", "status");
  const summary = node("p", "", "office-summary"), list = node("div", undefined, "office-list");
  // The feed repeats only who addressed whom and the message type, exactly as the balloons do.
  const feed = node("section", undefined, "office-feed"), feedList = node("ol", undefined, "office-feed-list");
  feed.setAttribute("aria-label", "Son iletişimler");
  feed.append(node("h3", "Son iletişimler"), feedList);
  const feedSeen = new Set(), feedItems = [];
  container.replaceChildren(title, toolbar, modelPanel, layout, summary, feed, humanWarning, note, list); container.classList.add("office-root");

  // ----- the office model ----------------------------------------------------------------------
  function modelMessage(text, error = false) {
    const line = modelPanel.querySelector(".office-model-status");
    if (line) { line.textContent = text; line.classList.toggle("agent-warning", error); }
  }
  function toggleModel(open) {
    modelPanel.hidden = !open; modelButton.setAttribute("aria-expanded", String(open));
    if (!open) return;
    drawModel();
    options.api("/api/agents/office/model").then((info) => {
      if (!alive) return;
      const changed = modelInfo?.present !== info.present || modelInfo?.id !== info.id || Boolean(modelInfo?.rejected) !== Boolean(info.rejected);
      modelInfo = info;
      if (changed) { placement = { ...PLACEMENT, ...info.placement }; drawModel(); }
    }).catch((error) => { if (alive) modelMessage(error.message, true); });
  }
  function drawModel() {
    if (modelPanel.hidden) return;
    const info = modelInfo, line = node("p", "", "agent-help office-model-status"); line.setAttribute("role", "status");
    const actions = node("div", undefined, "agent-actions");
    const pick = button(info?.present || info?.rejected ? "Yeni model seç (.glb)" : "Model seç (.glb)", choose);
    const sample = button("Örnek ofisi kullan", useSample);
    const parts = [node("h3", "Kendi ofis modeliniz"), node("p", "Bilgisayarınızdaki .glb dosyası (en fazla 100 MB) RPA ofis yerleşim sözleşmesine uymalıdır: ajanlar modelin tanımladığı çalışma ve bekleme noktalarına yerleşir, yalnız modelin yol ağında yürür. Model yalnız bu bilgisayarda ve bu ofis için saklanır, sunucuya gönderilmez. Kurallar ve model hazırlama yönergesi: belgelerdeki «Ofis modeli» sayfası.", "agent-help")];
    if (!info) { modelPanel.replaceChildren(...parts, node("p", "Model bilgisi yükleniyor…", "muted"), line); return; }
    if (info.rejected) {
      const reasons = node("ul", undefined, "office-model-errors");
      (info.rejected.errors || []).forEach((item) => reasons.append(node("li", item)));
      actions.append(pick, sample, button("Eski modeli sil", removeModel));
      modelPanel.replaceChildren(...parts, node("p", `İçe aktarılmış model (${info.rejected.name}) yerleşim sözleşmesine uymadığı için kullanılmıyor:`, "agent-warning"),
        reasons, actions, line);
      return;
    }
    if (!info.present) { actions.append(pick, sample); modelPanel.replaceChildren(...parts, actions, line); return; }
    const value = { ...PLACEMENT, ...placement };
    const cut = node("input"); cut.type = "number"; cut.min = String(CUT_RANGE[0]); cut.max = String(CUT_RANGE[1]); cut.step = ".1";
    cut.value = String(value.cut_height);
    cut.addEventListener("input", () => {
      const next = { cut_height: Number(cut.value) };
      if (cut.value.trim() === "" || !Number.isFinite(next.cut_height) || next.cut_height < CUT_RANGE[0] || next.cut_height > CUT_RANGE[1]) {
        modelMessage("Tavan kesitini 0–100 m arasında girin.", true); return;
      }
      placement = next; scene?.place(next); modelMessage("");
      clearTimeout(placeTimer); placeTimer = setTimeout(() => savePlacement(next), 600);
    });
    actions.append(pick, sample, button("Varsayılan ofise dön", removeModel));
    const size = info.size < 1_000_000 ? `${Math.max(1, Math.round(info.size / 1000))} KB`
      : `${(info.size / 1_000_000).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} MB`;
    const room = info.layout?.capacity || {}, seats = Object.keys(info.layout?.seats || {}).length;
    const facts = node("p", `${room.work || 0} çalışma noktası · ${room.wait || 0} bekleme noktası · ${seats} oturma yeri · ${Object.keys(info.layout?.points || {}).length} yerleşim düğümü`, "agent-help");
    const notes = node("ul", undefined, "office-model-errors");
    (info.layout?.warnings || []).forEach((item) => notes.append(node("li", item)));
    modelPanel.replaceChildren(...parts, node("p", `${info.name} · ${size} · Yerleşim sözleşmesi ${info.layout?.version || 1}`, "office-model-name"),
      facts, ...(notes.children.length ? [notes] : []), node("div", undefined, "office-model-grid"), actions, line);
    modelPanel.querySelector(".office-model-grid").append(field("Tavan kesiti (m, 0 = kapalı)", cut));
  }
  async function savePlacement(next) {
    try {
      const saved = await options.api("/api/agents/office/model/placement", { method: "PUT", body: JSON.stringify(next) });
      if (alive && modelInfo?.id === saved.id) { modelInfo = saved; modelMessage("Görünüm bu bilgisayara kaydedildi."); }
    } catch (error) { if (alive) modelMessage(error.message, true); }
  }
  async function imported(load, message) {
    modelPanel.querySelectorAll("button, input, select").forEach((item) => { item.disabled = true; });
    modelMessage(message);
    try {
      const info = await load();
      if (!alive) return;
      clearTimeout(placeTimer); modelInfo = info; placement = { ...PLACEMENT, ...info.placement }; drawModel();
      modelMessage("Model içe aktarıldı; 3D ofis hazırlanıyor…");
      layoutStale = true; await switchMode("3d");
      if (alive && !modelNotice) modelMessage(layoutState?.places?.full ? "Model yerleştirildi; ofis kapasitesi dolu, yerleşemeyenler listede."
        : "Model yerleştirildi; ajanlar çalışma noktalarında.");
    } catch (error) {
      if (alive) { drawModel(); modelMessage(error.message, true); }
    }
  }
  function choose() {
    const input = node("input"); input.type = "file"; input.accept = ".glb,model/gltf-binary";
    input.addEventListener("change", () => {
      const file = input.files?.[0];
      if (!file || !alive) return;
      if (!/\.glb$/i.test(file.name)) { modelMessage("Yalnız .glb dosyası içe aktarılabilir. Modeli dokularıyla birlikte tek bir .glb olarak dışa aktarın.", true); return; }
      if (file.size > MODEL_LIMIT) { modelMessage("Model en fazla 100 MB olabilir. Dokuları küçültüp veya ayrıntıyı azaltıp yeniden dışa aktarın.", true); return; }
      imported(() => options.api("/api/agents/office/model", { method: "PUT", body: file,
        headers: { "Content-Type": "model/gltf-binary", "X-Model-Name": encodeURIComponent(file.name) } }), "Model içe aktarılıyor ve yerleşim sözleşmesi denetleniyor…");
    });
    input.click();
  }
  function useSample() {
    imported(() => options.api("/api/agents/office/model/sample", { method: "POST", body: "{}" }), "Örnek ofis hazırlanıyor…");
  }
  async function removeModel() {
    const question = "İçe aktarılan model bu bilgisayardan silinsin mi? 3D ofis hazır görünümle açılır.";
    const confirmed = options.confirmDialog ? await options.confirmDialog("Varsayılan ofise dön", question, "Modeli sil", true)
      : window.confirm(question);
    if (!confirmed || !alive) return;
    try {
      clearTimeout(placeTimer);
      await options.api("/api/agents/office/model", { method: "DELETE" });
      if (!alive) return;
      modelInfo = { present: false, placement: { ...PLACEMENT } }; placement = { ...PLACEMENT }; drawModel();
      layoutStale = true; await switchMode(mode);
      modelMessage("Varsayılan ofise dönüldü.");
    } catch (error) { if (alive) modelMessage(error.message, true); }
  }
  // The layout of the imported model and everybody's persistent point on it.
  async function officeLayout() {
    const serial = ++layoutSerial;
    const info = await options.api("/api/agents/office/model");
    if (!alive || serial !== layoutSerial) return layoutState;
    const changed = modelInfo?.present !== info.present || modelInfo?.id !== info.id || Boolean(modelInfo?.rejected) !== Boolean(info.rejected);
    modelInfo = info;
    if (changed) { placement = { ...PLACEMENT, ...info.placement }; drawModel(); }
    if (!info.present || !info.layout) { releaseModel(); layoutState = null; return null; }
    const places = await options.api("/api/agents/office/model/assignments", { method: "POST",
      body: JSON.stringify({ occupants: occupants(lastData), humans_complete: humansLoaded }) });
    if (!alive || serial !== layoutSerial) return layoutState;
    layoutState = { id: info.id, layout: info.layout, places };
    return layoutState;
  }
  // Starts a read when the people or the model changed; a view switch meanwhile waits for the same read.
  function readLayout() {
    if (!layoutStale) return layoutReading;
    layoutStale = false; modelNotice = "";
    const reading = layoutReading = officeLayout().catch((error) => {
      layoutState = null; modelNotice = `Ofis modeli açılamadı (${error?.message || "bilinmeyen hata"}); hazır ofis gösteriliyor.`;
    }).then(() => { if (layoutReading === reading) layoutReading = null; });
    return reading;
  }
  // The model is read once and reused while agents come and go; only a new import reads the file again.
  function officeModel(THREE) {
    if (modelState.id !== modelInfo.id) {
      releaseModel();
      const id = modelInfo.id, promise = fetch("/api/agents/office/model/file", { cache: "no-store" }).then((response) => {
        if (!response.ok) throw new Error("Ofis modeli okunamadı.");
        return response.arrayBuffer();
      }).then((buffer) => openModel(THREE, buffer));
      modelState = { id, promise, value: null };
      promise.then((value) => { if (alive && modelState.id === id) modelState.value = value; else value.dispose(); },
        () => { if (modelState.id === id) modelState = { id: null, promise: null, value: null }; });
    }
    return modelState.promise;
  }
  function releaseModel() {
    const old = modelState; modelState = { id: null, promise: null, value: null }; old.value?.dispose();
  }
  function showCapacity() {
    const overflow = layoutState?.places?.overflow?.length || 0;
    capacity.hidden = !overflow;
    capacity.textContent = overflow ? `Ofis kapasitesi dolu: ${overflow} çalışan yerleşemedi; listede görünür.` : "";
  }

  // ----- list, feed and the detail panel ---------------------------------------------------------
  function placeOf(person) {
    const point = layoutState?.places?.places?.[person.id];
    if (!layoutState) return "";
    if (!point) return layoutStale || layoutReading ? "" : " · Yer yok (ofis kapasitesi dolu)";
    const kind = layoutState.layout.points[point]?.kind;
    return ` · ${PLACE_NAMES[kind] || "Nokta"} ${point.replace(/^RPA_[A-Z]+_/, "")}`;
  }
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
      [(person.kind === "human" ? "İnsan · Çalışanlar" : person.role === "manager" ? "Ajan · Yönetim" : `Ajan · ${person.department || "Departman alanı"}`) + placeOf(person),
        stateName(person), person.task_label || "Görev bekliyor", Number(person.queue_count) || 0].forEach((value) => item.append(node("td", value)));
      body.append(item);
    }
    if (!population(data).length) {
      const item = node("tr"), cell = node("td", "Henüz çalışan yok. Ajanlar ve kurum üyeleri eklendikçe ofisiniz düzenlenir.");
      cell.colSpan = headings.length; item.append(cell); body.append(item);
    }
    table.append(caption, head, body); list.replaceChildren(table);
    if (focused) [...list.querySelectorAll("button[data-person]")].find((item) => item.dataset.person === focused)?.focus({ preventScroll: true });
    const overflow = layoutState?.places?.overflow?.length || 0;
    summary.textContent = `${data.agents.length} ajan · ${data.people.length} insan · ${data.departments.length} departman · ${Number(data.totals.queued) || 0} ajan görevi sırada`
      + (overflow ? ` · ${overflow} çalışan yerleşemedi (ofis kapasitesi dolu)` : "");
    managerButton.hidden = !session || !data.agents.some((item) => item.role === "manager");
  }
  function updateFeed(data) {
    const people = population(data), verbs = { delegated: "görev verdi", question: "soru sordu", answered: "soruyu yanıtladı",
      completed: "sonucu teslim etti", office_request: "diğer ofise iş gönderdi", office_received: "diğer ofisten iş aldı",
      office_answered: "diğer ofisin işini teslim etti" };
    for (const person of people) {
      const event = person.event;
      if (!event?.id || feedSeen.has(event.id) || !verbs[event.kind]) continue;
      if (event.kind === "completed" && person.status !== "succeeded") continue;
      const target = people.find((item) => item.id === event.to_agent_id);
      const destination = target ? target.name : event.to_office ? `${event.to_office} ofisi` : "";
      if (!destination) continue;
      feedSeen.add(event.id); if (feedSeen.size > 500) feedSeen.delete(feedSeen.values().next().value);
      feedItems.unshift({ time: new Date(), text: `${person.name} → ${destination}: ${verbs[event.kind]}`, kind: event.kind });
    }
    feedItems.splice(8);
    feedList.replaceChildren(...(feedItems.length ? feedItems.map((item) => {
      const row = node("li"); row.dataset.kind = item.kind;
      row.append(node("time", item.time.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })), node("span", item.text));
      return row;
    }) : [node("li", "Henüz iletişim yok. Yönetici görev verdiğinde, bir departman soru sorduğunda veya sonuç teslim ettiğinde burada görünür.", "agent-help")]));
  }
  function closePanel() { selected = null; panelVersion++; panel.hidden = true; panel.replaceChildren(); layout.classList.remove("office-with-panel"); }
  function toast(message, error = false) { options.toast?.(message, error); }
  // The forms act exactly like the other Studio screens and with the same rights; nothing happens without a click.
  function taskForm(person, work) {
    const text = node("textarea"); text.rows = 4; text.maxLength = 16000;
    const start = button("Görevi başlat", async () => {
      const task = text.value.trim();
      if (!task) { toast("Görevi yazın.", true); return; }
      start.disabled = true;
      try {
        await options.api(`/api/agents/${encodeURIComponent(person.id)}/runs`, { method: "POST", body: JSON.stringify({ task }) });
        if (!alive) return;
        toast(`${person.name} görevi aldı.`); text.value = ""; refresh(true);
      } catch (error) { toast(error.message, true); } finally { start.disabled = false; }
    });
    start.classList.add("primary");
    work.replaceChildren(node("h4", person.role === "manager" ? "Yöneticiye görev ver" : "Görev ver"),
      field(person.role === "manager" ? "Yönetici ne yapsın? Gerekirse departmanlarına dağıtır." : "Ajan ne yapsın?", text), start);
    text.focus();
  }
  async function chatForm(person, work, version) {
    const thread = node("ol", undefined, "office-chat"), text = node("textarea"); text.rows = 3; text.maxLength = 4000;
    const show = (messages) => thread.replaceChildren(...(messages || []).slice(-6).map((item) => {
      const row = node("li", undefined, item.role === "user" ? "mine" : "theirs");
      row.append(node("strong", `${item.role === "user" ? (item.user || "Siz") : person.name}${item.via === "telegram" ? " · Telegram'dan" : ""}`), node("span", item.text));
      return row;
    }));
    const send = button("Sor", async () => {
      const question = text.value.trim();
      if (!question) { toast("Sorunuzu yazın.", true); return; }
      send.disabled = true; text.disabled = true;
      try {
        const answer = await options.api(`/api/agents/${encodeURIComponent(person.id)}/chat`, { method: "POST", body: JSON.stringify({ text: question }) });
        if (!alive || panelVersion !== version) return;
        show(answer?.messages); text.value = "";
      } catch (error) { toast(error.message, true); } finally { send.disabled = false; text.disabled = false; }
    });
    send.classList.add("primary");
    work.replaceChildren(node("h4", person.role === "manager" ? "Yöneticiye soru sor" : "Ajana soru sor"), thread,
      field("Sorunuz (ajan iş başlatmaz, bildiklerinden yanıtlar)", text), send);
    text.focus();
    try {
      const history = await options.api(`/api/agents/${encodeURIComponent(person.id)}/chat`);
      if (alive && panelVersion === version && Array.isArray(history)) show(history);
    } catch { /* The form still works without the earlier messages. */ }
  }
  function humanTaskForm(person, work) {
    const heading = node("input"); heading.type = "text"; heading.maxLength = 160;
    const text = node("textarea"); text.rows = 4; text.maxLength = 16000;
    const priority = node("select");
    for (const [value, label] of [["normal", "Normal"], ["high", "Yüksek"], ["low", "Düşük"]]) {
      const option = node("option", label); option.value = value; priority.append(option);
    }
    const assign = button("Görevi ata", async () => {
      const titleText = heading.value.trim(), instructions = text.value.trim();
      if (!titleText || !instructions) { toast("Görev başlığını ve yapılacak işi yazın.", true); return; }
      assign.disabled = true;
      try {
        await options.api("/api/agents/central/tasks", { method: "POST", body: JSON.stringify({ request_id: requestId(), title: titleText,
          instructions, assignee_user_id: person.user_id, priority: priority.value }) });
        if (!alive) return;
        toast(`${person.name} için görev oluşturuldu.`); heading.value = ""; text.value = ""; refresh(true);
      } catch (error) { toast(error.message, true); } finally { assign.disabled = false; }
    });
    assign.classList.add("primary");
    work.replaceChildren(node("h4", "Görev ata"), field("Görev başlığı", heading), field("Yapılacak iş", text), field("Öncelik", priority), assign);
    heading.focus();
  }
  // A question the agent waits for and, for the approver, the approval card, straight from the run.
  async function pendingWork(person, box, version) {
    let run;
    try { run = await options.api(`/api/agents/runs/${encodeURIComponent(person.run_id)}`); } catch { return; }
    if (!alive || panelVersion !== version || !run || typeof run !== "object" || Array.isArray(run)) return;
    const question = run.pending_question, approval = run.pending_approval;
    if (question?.id && typeof question.question === "string") {
      const card = node("section", undefined, "office-pending");
      card.append(node("h4", "Ajan sizden yanıt bekliyor"), node("p", question.question));
      const answer = async (value, control) => {
        control.disabled = true;
        try {
          await options.api(`/api/agents/runs/${encodeURIComponent(run.id)}/questions/${encodeURIComponent(question.id)}/answer`,
            { method: "POST", body: JSON.stringify({ answer: value }) });
          if (!alive) return;
          toast("Yanıtınız ajana iletildi."); card.remove(); refresh(true);
        } catch (error) { toast(error.message, true); control.disabled = false; }
      };
      const choices = node("div", undefined, "agent-actions");
      (Array.isArray(question.options) ? question.options : []).slice(0, 8).forEach((option) => {
        const choice = button(String(option), () => answer(option, choice)); choices.append(choice);
      });
      const text = node("textarea"); text.rows = 2; text.maxLength = 4000;
      const send = button("Yanıtla", () => { if (text.value.trim()) answer(text.value.trim(), send); });
      card.append(...(choices.children.length ? [choices] : []), field("Yanıtınız", text), send);
      box.append(card);
    }
    if (approval?.id && session?.can_approve) {
      const card = node("section", undefined, "office-pending");
      card.append(node("h4", "Onay bekleniyor"), node("p", `${approval.workflow_name || "Akış"} · ${approval.reason || ""}`));
      const inputs = node("ul", undefined, "office-recent");
      Object.entries(approval.inputs || {}).slice(0, 12).forEach(([key, value]) => inputs.append(node("li", `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`.slice(0, 300))));
      const decide = async (approved, control) => {
        control.disabled = true;
        try {
          await options.api(`/api/agents/runs/${encodeURIComponent(run.id)}/approvals/${encodeURIComponent(approval.id)}/decision`,
            { method: "POST", body: JSON.stringify({ approved }) });
          if (!alive) return;
          toast(approved ? "İşlem onaylandı." : "İşlem reddedildi."); card.remove(); refresh(true);
        } catch (error) { toast(error.message, true); control.disabled = false; }
      };
      const row = node("div", undefined, "agent-actions");
      const yes = button("Onayla", () => decide(true, yes)), no = button("Reddet", () => decide(false, no));
      yes.classList.add("primary"); row.append(yes, no);
      card.append(...(inputs.children.length ? [inputs] : []), node("p", "Girdileri düzenlemek için onay kartına gidin.", "agent-help"), row);
      box.append(card);
    }
  }
  async function selectPerson(identity, focus = "") {
    const person = lastData && population(lastData).find((item) => item.id === identity);
    if (!alive || !person) return;
    selected = identity; const version = ++panelVersion;
    panel.hidden = false; layout.classList.add("office-with-panel");
    const top = node("div", undefined, "office-detail-heading");
    top.append(node("h3", person.name), button("Kapat", closePanel));
    const live = node("p", `${stateName(person)} · ${person.task_label || "Görev bekliyor"}`, "office-detail-live");
    panel.replaceChildren(top, node("p", (person.kind === "human" ? "İnsan çalışan" : person.role === "manager" ? "Yönetici ajan" : `Departman ajanı · ${person.department}`) + placeOf(person), "agent-eyebrow"), live);
    if (person.kind === "human" && !person.can_view_tasks) { panel.append(node("p", "Bu çalışanın görev ayrıntılarını görüntüleme yetkiniz yok.", "agent-help")); return; }
    const human = person.kind === "human", actions = node("div", undefined, "agent-actions office-detail-actions");
    const work = node("div", undefined, "office-detail-work"), waiting = node("div", undefined, "office-detail-pending");
    if (human) {
      actions.append(button("Görevler ekranına git", () => options.openTab?.("tasks")));
      if (session?.can_manage && person.user_id) actions.append(button("Görev ata", () => humanTaskForm(person, work)));
    } else {
      if (person.run_id) actions.append(button(person.status === "waiting_approval" ? "Onay kartına git" : "Çalışma kaydına git", () => options.openAgentRun?.(person.run_id)));
      if (session) actions.append(button("Görev ver", () => taskForm(person, work)), button("Soru sor", () => chatForm(person, work, version)));
    }
    const details = node("div", "Ayrıntılar yükleniyor…", "office-detail-body");
    panel.append(actions, waiting, work, details);
    if (focus === "chat" && session && !human) chatForm(person, work, version);
    if (session && !human && person.run_id && ["waiting_user", "waiting_approval"].includes(person.status)) pendingWork(person, waiting, version);
    const end = new Date(), start = new Date(end); start.setHours(0, 0, 0, 0); start.setDate(1);
    const range = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
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

  // ----- views ---------------------------------------------------------------------------------
  function drawPlan(data) {
    if (layoutState) renderLayoutPlan(view, data, selectPerson, layoutState);
    else renderPlan(view, data, selectPerson);
  }
  function fallback(message) {
    if (!alive) return;
    mode = "2d"; scene?.dispose(); scene = null; generation++;
    drawPlan(lastData || { agents: [], people: [], departments: [] });
    status.textContent = message; updateMode();
  }
  function updateMode() {
    for (const [key, item] of buttons) item.setAttribute("aria-pressed", String(key === mode));
    frame.hidden = mode === "list"; reset.hidden = mode !== "3d"; legend.hidden = mode !== "3d";
    list.classList.toggle("office-list-primary", mode === "list");
  }
  function dropScene() { const previous = scene; scene = null; previous?.dispose(); }
  async function switchMode(next) {
    if (!alive || !lastData) return;
    if (demo && next !== "3d") stopDemo(false);
    mode = next; const version = ++generation; updateMode();
    // The current 3D scene stays on screen, paused on its last frame, until the next view is ready: people coming
    // and going never blank the office while the layout is read, and nothing draws a model being released.
    scene?.pause(true);
    if (mode === "list") { dropScene(); view.replaceChildren(); status.textContent = "Erişilebilir liste görünümü"; }
    else if (mode === "3d" && !scene) view.replaceChildren(node("p", "3D ofis hazırlanıyor…", "office-loading"));
    const reading = readLayout();
    if (reading) { await reading; if (!alive || generation !== version || mode !== next) return; }
    const office = layoutState;
    showCapacity(); updateList(lastData);
    if (mode === "list") return;
    if (mode === "2d") {
      dropScene(); drawPlan(lastData); status.textContent = modelNotice || (office ? "2D ofis planı · kendi modeliniz" : "2D ofis planı");
      return;
    }
    try {
      model ||= Promise.all([import("three"), import("three/addons/controls/OrbitControls.js")]);
      const [THREE, { OrbitControls }] = await model;
      if (!alive || generation !== version || mode !== "3d") return;
      let own = null;
      if (office) {
        try { own = await officeModel(THREE); }
        catch (error) { layoutState = null; showCapacity(); modelNotice = `Ofis modeli açılamadı (${error?.message || "bilinmeyen hata"}); hazır ofis gösteriliyor.`; }
      }
      if (!alive || generation !== version || mode !== "3d") return;
      dropScene();  // In the same task as the new scene: no frame without an office.
      scene = createScene(THREE, OrbitControls, view, lastData, fallback, selectPerson, seenEvents,
        own && layoutState ? { model: own, layout: layoutState.layout, places: layoutState.places, placement } : null);
      status.textContent = modelNotice || (own && layoutState ? "3D ofis · kendi modeliniz" : "3D ofis · yerel görünüm");
      if (modelNotice) modelMessage(modelNotice, true);
      scene.pause(document.hidden);
    } catch { if (alive && generation === version) fallback("3D bu cihazda açılamadı; 2D plan gösteriliyor."); }
  }
  // ----- the show: what a real task looks like, played on screen with the office's own agents ------------------
  const DEMO_STEP = 4500;
  function demoCast(data) {
    const manager = data.agents.find((item) => item.role === "manager");
    const departments = data.agents.filter((item) => item.role !== "manager").slice(0, 2);
    return manager && departments.length ? { manager, departments } : null;
  }
  // One task from start to finish; each walk gets time to arrive before the next turn.
  function demoScript({ manager, departments: [first, second] }) {
    let serial = 0;
    const event = (kind, to) => ({ id: `gosterim-${Date.now()}-${++serial}`, kind, to_agent_id: to.id });
    return [
      [[manager, { activity: "thinking", event: event("delegated", first) }], [first, { activity: "thinking" }]],
      second ? [[second, { activity: "workflow" }]] : [], [],
      [[first, { activity: "researching" }]], [], [],
      [[first, { activity: "asking_manager", event: event("question", manager) }], [manager, { activity: "reviewing" }]], [], [],
      [[manager, { activity: "thinking", event: event("answered", first) }], [first, { activity: "thinking" }]],
      [[first, { activity: "workflow" }]],
      [[first, { activity: null, status: "succeeded", event: event("completed", manager) }], [manager, { activity: "reviewing" }]],
      [], [], [],
    ];
  }
  // Each agent keeps its show state until the next change; an event plays once (seen events are remembered).
  function demoFrame(overrides) {
    for (const [person, values] of overrides) demo.state.set(person.id, { ...(demo.state.get(person.id) || {}), ...values });
    return { ...lastData, agents: lastData.agents.map((item) => ({ ...item, event: null, ...(demo.state.get(item.id) || {}) })) };
  }
  async function startDemo() {
    if (!alive || !lastData || demo) return;
    const cast = demoCast(lastData);
    if (!cast) {
      status.textContent = "Gösterim için ofiste bir yönetici ajan ve en az bir departman ajanı olmalı; Ajanlar sekmesinden ekleyin.";
      return;
    }
    if (mode !== "3d") await switchMode("3d");
    if (!alive || !scene || demo) return;
    const steps = demoScript(cast), step = Number(options.showStep) || DEMO_STEP;
    demo = { timers: [], state: new Map(), saved: status.textContent };
    demoButton.textContent = "Gösterimi durdur";
    status.textContent = matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "Gösterim · bilgisayarınızda Hareketi azalt açık: karakterler yürümez, yalnız balonlar görünür"
      : "Gösterim oynatılıyor · gerçek iş yapılmıyor";
    steps.forEach((turn, index) => {
      demo.timers.push(setTimeout(() => { if (demo && scene) scene.update(demoFrame(turn)); }, index * step));
    });
    demo.timers.push(setTimeout(() => stopDemo(), steps.length * step));
  }
  function stopDemo(restore = true) {
    if (!demo) return;
    demo.timers.forEach(clearTimeout);
    const saved = demo.saved; demo = null;
    demoButton.textContent = "Gösterimi oynat";
    if (restore && lastData) { scene?.update(lastData); status.textContent = saved; }
  }
  async function refresh(now = false) {
    if (now) { clearTimeout(timer); timer = setTimeout(() => refresh(), 300); return; }
    if (!alive || document.hidden || pending) return;
    pending = true;
    try {
      const [local, central] = await Promise.allSettled([options.api("/api/agents/office"), options.api("/api/agents/central/office")]);
      if (!alive) return;
      if (local.status === "rejected") throw local.reason;
      const data = safeData(local.value);
      heading.textContent = data.office ? `${data.office} ofisi` : "Ofis";
      const humans = central.status === "fulfilled" && Array.isArray(central.value?.people) ? central.value.people.slice(0, 500) : null;
      data.people = humans || []; humansLoaded = humans !== null;
      humanWarning.hidden = humans !== null; humanWarning.textContent = humans === null ? "İnsan çalışanların durumu alınamadı. Kurum bağlantısı yenilendiğinde tekrar gösterilecek." : "";
      // A new population needs new places; until they are read, a newcomer's place is unknown rather than "full".
      const key = JSON.stringify([data.departments, population(data).map((p) => [p.id, p.kind, p.role, p.department])]);
      const reshaped = shapeKey !== key;
      if (reshaped) { shapeKey = key; layoutStale = true; }
      lastData = data; updateList(data); updateFeed(data);
      if (selected) {
        const person = population(data).find((item) => item.id === selected);
        if (!person) closePanel();
        else if (person.kind === "human" && !person.can_view_tasks && panel.querySelector(".office-detail-body")) selectPerson(person.id);
        else if (panel.querySelector(".office-detail-live")) panel.querySelector(".office-detail-live").textContent = `${stateName(person)} · ${person.task_label || "Görev bekliyor"}`;
      }
      if (reshaped && demo) stopDemo(false);
      if (reshaped) await switchMode(mode);
      else if (mode === "2d") drawPlan(data);
      else if (!demo) scene?.update(data);
    } catch (error) { if (alive) { closePanel(); status.textContent = error?.message || "Ofis bilgisi güncellenemedi."; } }
    finally { pending = false; if (alive && !document.hidden) timer = setTimeout(refresh, 3000); }
  }
  function visibility() { clearTimeout(timer); scene?.pause(document.hidden); if (!document.hidden) refresh(); }
  document.addEventListener("visibilitychange", visibility); refresh();
  return () => {
    stopDemo(false);
    alive = false; panelVersion++; generation++; clearTimeout(timer); clearTimeout(placeTimer); scene?.dispose(); scene = null;
    releaseModel(); document.removeEventListener("visibilitychange", visibility); container.classList.remove("office-root");
  };
}

function svgFactory() {
  return (tag, attributes, text) => {
    const element = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const [key, value] of Object.entries(attributes || {})) element.setAttribute(key, String(value));
    if (text !== undefined) element.textContent = text; return element;
  };
}
function planPerson(create, person, x, y, selectPerson) {
  const mark = create("g", { role: "button", tabindex: "0", id: `rpa-office-plan-person-${++serial}`,
    "aria-label": `${person.name} · ${stateName(person)}`, class: "office-plan-person", "data-status": person.status, "data-activity": person.activity || person.status, "data-person": person.id });
  mark.append(create("circle", { cx: x, cy: y + 28, r: 12 }), create("text", { x, y: y + 34, "text-anchor": "middle", class: "office-plan-symbol" }, symbol(person)),
    create("text", { x, y: y + 59, "text-anchor": "middle", class: "office-plan-name" }, String(person.name).slice(0, 12)));
  mark.addEventListener("click", () => selectPerson(person.id));
  mark.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); selectPerson(person.id); } });
  return mark;
}
function renderPlan(host, data, selectPerson) {
  const focused = host.contains(document.activeElement) ? document.activeElement.dataset.person : null;
  const create = svgFactory();
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
    const x = px(seat.x), y = py(seat.z);
    floor.append(create("rect", { x: x - 28, y: y - 5, width: 56, height: 22, rx: 4, class: "office-plan-desk" }), planPerson(create, seat.person, x, y, selectPerson));
  }
  host.replaceChildren(floor); host.dataset.mode = "2d";
  if (focused) [...host.querySelectorAll("[data-person]")].find((item) => item.dataset.person === focused)?.focus({ preventScroll: true });
}
// The plan of an imported model: only its own points, paths and labels; no rooms are invented.
function renderLayoutPlan(host, data, selectPerson, state) {
  const focused = host.contains(document.activeElement) ? document.activeElement.dataset.person : null;
  const create = svgFactory(), { layout, places } = state, points = Object.entries(layout.points);
  const xs = [...points.map(([, item]) => item.position[0]), ...layout.labels.map((item) => item.position[0])];
  const zs = [...points.map(([, item]) => item.position[2]), ...layout.labels.map((item) => item.position[2])];
  const minX = Math.min(...xs) - 2, maxX = Math.max(...xs) + 2, minZ = Math.min(...zs) - 2, maxZ = Math.max(...zs) + 3;
  const scale = 920 / Math.max(1, maxX - minX), height = (maxZ - minZ) * scale + 80;
  const px = (x) => 40 + (x - minX) * scale, py = (z) => 40 + (z - minZ) * scale;
  const floor = create("svg", { viewBox: `0 0 1000 ${Math.round(height)}`, role: "group", "aria-label": "Ofis modelinin planı ve çalışan durumları", class: "office-plan" });
  floor.append(create("rect", { x: 20, y: 20, width: 960, height: height - 40, rx: 24, class: "office-plan-floor" }));
  for (const [first, second] of layout.edges) {
    const a = layout.points[first].position, b = layout.points[second].position;
    floor.append(create("line", { x1: px(a[0]), y1: py(a[2]), x2: px(b[0]), y2: py(b[2]), class: "office-plan-path" }));
  }
  for (const [, item] of points) {
    if (!["work", "wait", "manager"].includes(item.kind)) continue;
    floor.append(create("rect", { x: px(item.position[0]) - 18, y: py(item.position[2]) - 10, width: 36, height: 20, rx: 4,
      class: item.kind === "wait" ? "office-plan-wait" : "office-plan-desk" }));
  }
  for (const item of layout.labels) floor.append(create("text", { x: px(item.position[0]), y: py(item.position[2]), "text-anchor": "middle", class: "office-plan-area" }, item.text));
  const spots = new Map();
  for (const person of population(data)) {
    const point = places?.places?.[person.id];
    if (point && layout.points[point]) spots.set(person.id, layout.points[point].position);
  }
  const manager = population(data).find((person) => person.role === "manager" && spots.has(person.id));
  for (const person of population(data)) {
    if (!manager || person === manager || person.activity !== "asking_manager" || !spots.has(person.id)) continue;
    const a = spots.get(person.id), b = spots.get(manager.id);
    floor.append(create("line", { x1: px(a[0]), y1: py(a[2]) + 18, x2: px(b[0]), y2: py(b[2]) + 18, class: "office-plan-link" }),
      create("text", { x: (px(a[0]) + px(b[0])) / 2, y: (py(a[2]) + py(b[2])) / 2 + 14, "text-anchor": "middle", class: "office-plan-link-label" }, "Soru"));
  }
  for (const person of population(data)) {
    const at = spots.get(person.id);
    if (at) floor.append(planPerson(create, person, px(at[0]), py(at[2]) - 22, selectPerson));
  }
  const overflow = places?.overflow?.length || 0;
  if (overflow) floor.append(create("text", { x: 500, y: height - 30, "text-anchor": "middle", class: "office-plan-full" }, `Ofis kapasitesi dolu: ${overflow} çalışan listede`));
  host.replaceChildren(floor); host.dataset.mode = "2d";
  if (focused) [...host.querySelectorAll("[data-person]")].find((item) => item.dataset.person === focused)?.focus({ preventScroll: true });
}

function createScene(THREE, OrbitControls, host, data, fallback, selectPerson, seenEvents, office = null) {
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
    humanMat = material("mark"), headMat = material("surface"), bootMat = material("ink");
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

  // ----- the room: generated, or the imported model with its own points -----------------------
  const layout = office?.layout || null;
  let length = 18, centerZ = 0, target = new THREE.Vector3(0, 0, 1), extent = 22, outer = null;
  if (layout) {
    renderer.localClippingEnabled = true;
    // The model's RPA_ORIGIN becomes the office origin; every point already lies in that frame.
    outer = new THREE.Group(); outer.matrixAutoUpdate = false;
    outer.matrix.fromArray(layout.origin_matrix).invert(); outer.add(office.model.group.clone()); scene.add(outer);
    outer.updateMatrixWorld(true);
    const bounds = new THREE.Box3().setFromObject(outer), size = bounds.getSize(new THREE.Vector3());
    extent = Math.max(4, size.x, size.z);
    const middle = bounds.getCenter(new THREE.Vector3());
    target = layout.camera_target ? new THREE.Vector3(...layout.camera_target) : new THREE.Vector3(middle.x, 0, middle.z);
    for (const item of layout.labels) label(item.text, ...item.position);
    controls.minAzimuthAngle = -Infinity; controls.maxAzimuthAngle = Infinity;
    controls.minDistance = Math.max(3, extent * .25); controls.maxDistance = Math.max(20, extent * 3);
    Object.assign(light.shadow.camera, { left: -extent, right: extent, top: extent, bottom: -extent, near: 1, far: extent * 4 + 40 });
    light.position.set(target.x + extent * .35, extent * .8 + 10, target.z + extent * .45); light.target.position.copy(target); scene.add(light.target);
  } else {
    const areas = rooms(data);
    length = Math.max(18, ...areas.map((r) => r.z + r.depth / 2 + 9)); centerZ = length / 2 - 9; target = new THREE.Vector3(0, 0, centerZ);
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
    // Araştırma köşesi: agents that read the web walk here (bookshelf and globe beside the lounge).
    box(1.5, 2.3, .45, deskMat, -3.15, 1.15, 5.5);
    for (const height of [.55, 1.15, 1.75]) box(1.3, .08, .4, metalMat, -3.15, height, 5.5);
    for (const [offset, height, token] of [[-.35, .82, trimMat], [.1, .82, plantMat], [-.2, 1.42, humanMat], [.3, 1.42, trimMat]])
      box(.18, .42, .3, token, -3.15 + offset, height, 5.5);
    box(.12, 1.0, .12, metalMat, 3.15, .5, 5.5);
    mesh(new THREE.SphereGeometry(.45, 18, 12), plantMat, 3.15, 1.35, 5.5);
    label("Araştırma köşesi", -3.15, 2.75, 5.5);
  }
  light.shadow.camera.updateProjectionMatrix();
  function place(value) {
    if (!office) return;
    const cut = Number({ ...PLACEMENT, ...value }.cut_height) || 0;
    office.model.plane.constant = cut > 0 ? cut : 1e6;
    request();
  }

  // ----- people --------------------------------------------------------------------------------
  // Legs bend at the hip and the knee, so a seat is used with a real seated pose, never faked by moving.
  function character(spec) {
    const { person } = spec, root = new THREE.Group(); scene.add(root); root.position.copy(spec.origin); root.rotation.y = spec.yaw;
    const shirt = person.kind === "human" ? humanMat : chairMat, screen = material("ink"), statusMat = material("accent");
    if (spec.desk) desk(spec.desk.x, spec.desk.z, spec.desk.large, screen);
    const body = new THREE.Group(); root.add(body);
    mesh(new THREE.CylinderGeometry(.27, .34, .65, 5), shirt, 0, 1.13, 0, body);
    const head = mesh(new THREE.IcosahedronGeometry(.29, 1), headMat, 0, 1.67, 0, body);
    // Small eyes and a badge distinguish the generated office figures without external textures.
    for (const side of [-1, 1]) box(.055, .045, .035, bootMat, side * .10, 1.7, -.27, body);
    box(.10, .15, .025, person.kind === "human" ? chairMat : humanMat, .14, 1.25, -.26, body);
    const arms = [], legs = [], knees = [];
    for (const side of [-1, 1]) {
      const arm = new THREE.Group(); arm.position.set(side * .34, 1.33, 0); body.add(arm);
      box(.17, .46, .18, shirt, 0, -.18, 0, arm); mesh(new THREE.IcosahedronGeometry(.12, 0), headMat, 0, -.44, 0, arm); arms.push(arm);
      const hip = new THREE.Group(); hip.position.set(side * .17, .77, -.16); root.add(hip);
      box(.17, .24, .22, bootMat, 0, -.12, 0, hip);
      const knee = new THREE.Group(); knee.position.set(0, -.24, 0); hip.add(knee);
      const shin = box(.17, SHIN, .22, bootMat, 0, -SHIN / 2, 0, knee), boot = box(.19, .14, .32, bootMat, 0, -SHIN - .03, -.07, knee);
      legs.push(hip); knees.push({ knee, shin, boot });
    }
    const ring = mesh(new THREE.TorusGeometry(.52, .035, 5, 20, Math.PI * 1.5), statusMat, spec.ring.x, spec.ring.y, spec.ring.z);
    ring.rotation.x = Math.PI / 2; ring.visible = false;
    const folder = box(.35, .42, .065, humanMat, -.42, 1.05, -.18, body); folder.visible = false;
    const name = button("", () => selectPerson(person.id)); name.className = "office-person-label";
    name.dataset.person = person.id; overlay.append(name);
    const bubble = node("span", "", "office-person-bubble"), caption = node("span", "", "office-person-name");
    const speech = node("span", "", "office-person-speech"); speech.hidden = true; speech.setAttribute("aria-hidden", "true");
    name.append(speech, bubble, caption);
    const labelItem = { node: name, point: root.position.clone().add(new THREE.Vector3(0, 2.85, 0)), character: root }; labels.push(labelItem);
    root.traverse((child) => { if (child.isMesh) child.userData.personId = person.id; });
    characters.set(person.id, { root, body, head, arms, legs, knees, folder, ring, screen, statusMat, name, bubble, caption, labelItem,
      speech, said: null, origin: root.position.clone(), yaw: spec.yaw, seat: spec.seat || null, place: spec.place || null,
      person, delivery: null, trip: null });
  }
  if (layout) {
    for (const person of population(data)) {
      const point = office.places?.places?.[person.id], anchor = point ? layout.points[point] : null;
      if (!anchor) continue;  // No free point: the person stays in the list, never on top of someone else.
      const [x, y, z] = anchor.position, yaw = (anchor.yaw || 0) + CHARACTER_FORWARD;
      const seatName = layout.seats[point], seatPoint = seatName ? layout.points[seatName] : null;
      let seat = null;
      if (seatPoint) {
        const [sx, sy, sz] = seatPoint.position, seatYaw = (seatPoint.yaw ?? anchor.yaw ?? 0);
        seat = { position: new THREE.Vector3(sx + Math.sin(seatYaw) * SEAT_FORWARD, sy - THIGH_UNDERSIDE, sz + Math.cos(seatYaw) * SEAT_FORWARD),
          yaw: seatYaw + CHARACTER_FORWARD, shin: Math.min(2.2, Math.max(.6, (sy + .01 - y) / SHIN)) };
      }
      character({ person, origin: new THREE.Vector3(x, y - SOLE, z), yaw, seat, place: point, ring: { x, y: y + .06, z } });
    }
  } else {
    for (const seat of seating(data)) {
      character({ person: seat.person, origin: new THREE.Vector3(seat.x, .05, seat.z + .95), yaw: 0,
        desk: { x: seat.x, z: seat.z, large: seat.large }, ring: { x: seat.x, y: .25, z: seat.z + .95 } });
    }
  }
  function pose(item, seated) {
    item.legs.forEach((hip) => { hip.rotation.x = seated ? Math.PI / 2 : 0; });
    const length = seated ? SHIN * item.seat.shin : SHIN;
    item.knees.forEach(({ knee, shin, boot }) => {
      knee.rotation.x = seated ? -Math.PI / 2 : 0;
      shin.scale.y = length / SHIN; shin.position.y = -length / 2; boot.position.y = -length - .03;
    });
  }
  // Balloons show only the message type; the office never receives question or answer texts.
  function say(item, text, duration, stamp) { item.said = { text, until: stamp + duration }; }
  function eventFor(person, stamp) {
    const event = person.event;
    if (!event?.id || seenEvents.has(event.id)) return;
    seenEvents.add(event.id); if (seenEvents.size > 1000) seenEvents.delete(seenEvents.values().next().value);
    const source = characters.get(person.id);
    if (source && event.kind === "office_request") { say(source, "Diğer ofise", 4500, stamp); return; }
    if (source && event.kind === "office_answered") { say(source, "Diğer ofise sonuç", 4500, stamp); return; }
    if (source && event.kind === "office_received") { say(source, "Diğer ofisten", 4500, stamp); return; }
    const destination = characters.get(event.to_agent_id);
    if (!source || !destination) return;
    if (event.kind === "answered") say(source, "Yanıt", 4500, stamp);
    else if (event.kind === "delegated") say(source, "Görev", 3000, stamp);
    else if (event.kind === "completed" && person.status === "succeeded") say(source, "Sonuç", 4500, stamp);
    if (reduced.matches) return;
    const trip = event.kind === "completed" && person.status === "succeeded" ? deliveryRoute(source)
      : event.kind === "delegated" ? handOver(source, destination) : null;
    if (trip) source.delivery = { stamp, ...trip };
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

  // ----- walking: generated corridors, or only the model's declared path network ----------------
  const TRIP = 3500;
  const at = (name) => { const [x, y, z] = layout.points[name].position; return new THREE.Vector3(x, y - SOLE, z); };
  function journey(names) {
    const path = names.map(at);
    let total = 0;
    for (let index = 1; index < path.length; index++) total += path[index].distanceTo(path[index - 1]);
    // A large office is crossed faster: a trip never takes longer than MAX_TRIP, so people see where it ends.
    return { route: path, duration: Math.min(MAX_TRIP, Math.max(1200, total / WALK_SPEED * 1000)) };
  }
  // A destination point of the model (meeting or research point) that nobody else is heading to.
  function freePoint(item, kind) {
    const busy = new Set([...characters.values()].filter((other) => other !== item).map((other) => other.trip?.target || other.delivery?.target));
    return Object.keys(layout.points).sort().find((name) => layout.points[name].kind === kind && !busy.has(name)
      && shortestPath(layout, item.place, name)) || null;
  }
  function tripTo(item, kind) {
    if (!layout) {
      return kind === "ask" ? { route: route(item, askingSlot(item)), duration: TRIP, face: 0 }
        : { route: route(item, researchSlot(item), 4.4), duration: TRIP, face: Math.PI };
    }
    if (!item.place) return null;
    const destination = freePoint(item, kind === "ask" ? "meet" : "research");
    if (!destination) return null;  // The model defines no such area, or every spot is taken: stay with the balloon.
    return { ...journey(shortestPath(layout, item.place, destination)), target: destination,
      face: (layout.points[destination].yaw || 0) + CHARACTER_FORWARD };
  }
  function deliveryRoute(item) {
    if (!layout) return { route: route(item, 0), duration: 8000 };
    const destination = item.place && freePoint(item, "meet");
    if (!destination) return null;
    const trip = journey(shortestPath(layout, item.place, destination));
    return { ...trip, duration: trip.duration * 2 + 1500, target: destination };
  }
  function route(item, endX, endZ = 1.9) {
    const side = item.origin.x < 0 ? -4 : 4;
    return [item.origin, new THREE.Vector3(side, .05, item.origin.z), new THREE.Vector3(side, .05, 3.3),
      new THREE.Vector3(endX, .05, 3.3), new THREE.Vector3(endX, .05, endZ)];
  }
  // The manager leaves its place and hands the task card over next to the department's place.
  function handOver(manager, department) {
    if (layout) {
      const names = manager.place && department.place ? shortestPath(layout, manager.place, department.place) : null;
      if (!names || names.length < 3) return null;
      const trip = journey(names.slice(0, -1));
      return { ...trip, duration: trip.duration * 2 + 1500 };
    }
    const side = department.origin.x < 0 ? -4 : 4, front = department.origin.z + 1.2;
    return { route: [manager.origin, new THREE.Vector3(manager.origin.x, .05, 3.3), new THREE.Vector3(side, .05, 3.3),
      new THREE.Vector3(side, .05, front), new THREE.Vector3(department.origin.x, .05, front)], duration: 8000 };
  }
  function researchSlot(item) {
    const reading = [...characters.values()].filter((other) => (other.person.activity || other.person.status) === "researching");
    const index = Math.max(0, reading.indexOf(item));
    return (index % 2 ? 1 : -1) * (1.3 + Math.floor(index / 2) * 1.1);
  }
  function askingSlot(item) {
    // Several departments can wait in front of the manager at once; give each a fixed place.
    const waiting = [...characters.values()].filter((other) => (other.person.activity || other.person.status) === "asking_manager");
    const index = Math.max(0, waiting.indexOf(item));
    return (index % 2 ? 1 : -1) * (1.2 + Math.floor(index / 2) * 1.2);
  }
  // Moves along the polyline by distance, so every corridor is walked at the same pace.
  function walk(item, path, phase, back, stamp, stepping) {
    // A frame's timestamp can precede the moment an event was recorded; never step outside the path.
    phase = Math.max(0, Math.min(1, phase));
    const lengths = [];
    let total = 0;
    for (let index = 1; index < path.length; index++) { const piece = path[index].distanceTo(path[index - 1]); lengths.push(piece); total += piece; }
    let left = phase * total, index = 0;
    while (index < lengths.length - 1 && left > lengths[index]) { left -= lengths[index]; index++; }
    const from = path[index], to = path[Math.min(index + 1, path.length - 1)];
    item.root.position.lerpVectors(from, to, lengths[index] ? Math.min(1, left / lengths[index]) : 1);
    const direction = to.clone().sub(from);
    if (direction.lengthSq() > 1e-6) item.root.rotation.y = Math.atan2(-direction.x, -direction.z) + (back ? Math.PI : 0);
    if (stepping) item.legs.forEach((leg, number) => { leg.rotation.x = Math.sin(stamp / 130 + number * Math.PI) * .35; });
  }
  function animate(stamp) {
    let active = false;
    for (const item of characters.values()) {
      const state = item.person.activity || item.person.status, moving = !reduced.matches;
      item.root.position.copy(item.origin); item.root.rotation.y = item.yaw; item.body.position.y = 0; item.head.rotation.z = 0;
      item.arms[0].rotation.set(0, 0, 0); item.arms[1].rotation.set(0, 0, 0);
      pose(item, false);
      item.ring.visible = state === "workflow"; item.ring.rotation.z = moving ? stamp / 1300 : 0;
      item.folder.visible = Boolean(item.delivery) && moving;
      if (state === "waiting_approval") {
        item.body.position.y = moving ? Math.sin(stamp / 600) * .025 : 0;
        item.arms[1].rotation.z = -2.35; item.head.rotation.z = moving ? Math.sin(stamp / 650) * .04 : 0; active ||= moving;
      } else if (["thinking", "running", "workflow"].includes(state)) {
        item.arms.forEach((arm, index) => { arm.rotation.x = -.55 + (moving && state === "workflow" ? Math.sin(stamp / 180 + index) * .08 : 0); });
        item.body.position.y = moving ? Math.sin(stamp / 850) * .025 : 0; active ||= moving;
      }
      const asking = state === "asking_manager", researching = state === "researching";
      const wanted = asking ? "ask" : researching ? "research" : null;
      const speech = asking ? "Soru" : researching ? "Araştırıyor" : item.said && item.said.until > stamp ? item.said.text : "";
      if (item.said && item.said.until <= stamp) item.said = null;
      item.speech.textContent = speech; item.speech.hidden = !speech; active ||= Boolean(item.said);
      if (wanted && moving && !item.trip) {
        const trip = tripTo(item, wanted);
        // Without a reachable spot the person stays in place; the trip is not retried every frame.
        item.trip = trip ? { ...trip, out: true, stamp, kind: wanted } : { out: true, stamp, kind: wanted, idle: true };
        if (trip) item.delivery = null;
      } else if (item.trip?.out && (item.trip.kind !== wanted || !moving)) {
        const reached = item.trip.idle ? 1 : Math.min(1, (stamp - item.trip.stamp) / item.trip.duration);
        item.trip = { ...item.trip, out: false, stamp: stamp - (1 - reached) * (item.trip.duration || 0) };
      }
      let walked = false;
      if (item.trip) {
        if (item.trip.idle) { if (!item.trip.out) item.trip = null; }
        else {
          const elapsed = (stamp - item.trip.stamp) / item.trip.duration, phase = item.trip.out ? Math.min(1, elapsed) : 1 - elapsed;
          if ((!item.trip.out && phase <= 0) || !moving) item.trip = null;
          else {
            walk(item, item.trip.route, phase, !item.trip.out, stamp, phase < 1); walked = true;
            if (phase >= 1) item.root.rotation.y = item.trip.face;
            active ||= phase < 1;
          }
        }
      }
      if (item.delivery && moving && !item.trip) {
        const progress = (stamp - item.delivery.stamp) / item.delivery.duration;
        if (progress >= 1) { item.delivery = null; item.folder.visible = false; }
        else {
          // Walk to the destination, then return to the same place.
          const phase = progress < .5 ? progress * 2 : (1 - progress) * 2;
          walk(item, item.delivery.route, phase, progress >= .5, stamp, true); walked = true; active = true;
        }
      }
      if (item.seat && !walked) {
        pose(item, true); item.root.position.copy(item.seat.position); item.root.rotation.y = item.seat.yaw;
      }
      item.labelItem.point.copy(item.root.position).add(new THREE.Vector3(0, item.seat && !walked ? 2.85 - .2 : 2.85, 0));
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
    if (slow >= 6) {
      fallback(office ? "Ofis modeli bu cihazda ağır kaldı; 2D plan gösteriliyor. Daha sade bir model deneyin veya varsayılan ofise dönün."
        : "Bu cihazda daha akıcı görüntü için 2D plana geçildi.");
      return;
    }
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
    const scale = layout ? Math.max(.3, extent / 36) : Math.max(1, length / 22);
    camera.position.set(target.x + 23 * scale, 24 * scale, target.z + 29 * scale);
    controls.target.copy(target); controls.update(); request();
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
  place(office?.placement); motion(); reset(); resize(); theme(); update(data);
  return { reset, update, place, pause(value) {
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
