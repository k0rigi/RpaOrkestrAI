"use strict";

// Loaded only by the isolated native package diagnostic, never by Studio.
(() => {
  const marker = document.querySelector('meta[name="rpa-office-check"]');
  if (!marker) return;
  const errors = [];
  const note = (value) => { if (errors.length < 20) errors.push(String(value).slice(0, 200)); };
  window.addEventListener("error", () => note("Ofis kaynağında JavaScript hatası oluştu."));
  window.addEventListener("unhandledrejection", () => note("Ofis kaynağında beklenmeyen işlem hatası oluştu."));
  window.addEventListener("securitypolicyviolation", (event) => note(
    `İçerik güvenliği: ${event.effectiveDirective} · ${event.blockedURI} · ${event.lineNumber}:${event.columnNumber}`));
  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  async function until(predicate, label, ms = 12000) {
    const end = Date.now() + ms;
    while (!predicate()) {
      if (Date.now() > end) throw new Error(label);
      await delay(50);
    }
  }
  const checks = Object.fromEntries(["module_import", "three_rendered", "theme", "svg_fallback", "accessible_list",
    "safe_text", "cleanup", "readonly", "local_resources"].map((name) => [name, false]));
  let draws = 0, context = null, dispose = null, calls = 0, writes = 0, webglAvailable = false;
  const restorers = [];

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      // Observe actual native GL calls while leaving renderer behaviour unchanged.
      for (const name of ["WebGLRenderingContext", "WebGL2RenderingContext"]) {
        const prototype = window[name]?.prototype;
        if (!prototype) continue;
        for (const method of ["drawElements", "drawArrays"]) {
          const original = prototype[method];
          if (typeof original !== "function") continue;
          prototype[method] = function(...args) {
            const result = original.apply(this, args);
            if (this.canvas?.closest(".office-view")) { draws++; context = this; }
            return result;
          };
          restorers.push(() => { prototype[method] = original; });
        }
      }
      const probe = document.createElement("canvas");
      const gl = probe.getContext("webgl2") || probe.getContext("webgl");
      webglAvailable = Boolean(gl);
      gl?.getExtension("WEBGL_lose_context")?.loseContext();
      const module = await import("/office.js");
      checks.module_import = typeof module.mountOffice === "function";
      const data = { agents: [{ id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", name: "Kontrol ajanı", role: "manager",
        department: "Genel", status: "idle", task_id: null, task_label: "Görev bekliyor", queue_count: 0 }],
        departments: [{name: "Kontrol alanı", agent_count: 1}], totals: {agents: 1, queued: 0, running: 0, waiting: 0} };
      // Opening the office only reads: the scene, the people and whether this computer has an own model.
      const reads = ["/api/agents/office", "/api/agents/central/office", "/api/agents/office/model"];
      const options = { api: async (path, request = {}) => {
        calls++;
        if ((request.method || "GET") !== "GET" || !reads.includes(path)) {
          writes++; throw new Error("Ofis kontrolünde salt okunur sınır aşıldı.");
        }
        if (path === "/api/agents/central/office") return {success: true, people: []};
        if (path === "/api/agents/office/model") return {present: false, placement: {}};
        return structuredClone(data);
      } };
      const root = document.getElementById("native-office-root");
      dispose = module.mountOffice(root, options);
      await until(() => document.querySelector(".office-view[data-mode]"), "Ofis görünümü açılamadı.");
      if (webglAvailable) {
        await until(() => draws > 0, "Yerel WebGL ofisi çizemedi.");
        checks.three_rendered = Boolean(context && !context.isContextLost() && context.getError() === context.NO_ERROR
          && document.querySelector('.office-view[data-mode="3d"] canvas'));
      }
      const frame = document.querySelector(".office-frame");
      document.documentElement.dataset.theme = "light";
      await delay(100);
      const light = getComputedStyle(frame).backgroundColor;
      document.documentElement.dataset.theme = "dark";
      await delay(150);
      checks.theme = getComputedStyle(frame).backgroundColor !== light;
      dispose(); dispose = null;
      // Exercise fallback in the same native engine, even when WebGL is available.
      const original = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function(kind, ...args) {
        return String(kind).includes("webgl") ? null : original.call(this, kind, ...args);
      };
      restorers.push(() => { HTMLCanvasElement.prototype.getContext = original; });
      data.agents[0].name = '<img src=x onerror="window.nativeOfficeAttack=true">';
      dispose = module.mountOffice(root, options);
      await until(() => document.querySelector('.office-view[data-mode="2d"] svg'), "Ofis yedek planı açılamadı.");
      checks.svg_fallback = document.querySelectorAll(".office-plan").length === 1;
      const list = [...root.querySelectorAll("button")].find((item) => item.textContent === "Liste");
      list.click();
      checks.accessible_list = Boolean(root.querySelector(".office-frame")?.hidden && root.querySelector(".office-table"));
      checks.safe_text = !root.querySelector("img") && !window.nativeOfficeAttack
        && root.querySelector(".office-table").textContent.includes(data.agents[0].name);
      dispose(); dispose = null;
      const before = calls;
      await delay(3200);
      checks.cleanup = calls === before && !root.querySelector("canvas");
      checks.readonly = writes === 0;
      checks.local_resources = performance.getEntriesByType("resource").every((item) => new URL(item.name).origin === location.origin);
    } catch (error) {
      note(error?.message || "Ofis kontrolü tamamlanamadı.");
    } finally {
      dispose?.();
      for (const restore of restorers.reverse()) restore();
      await fetch("/__office_report", {method: "POST", headers: {"Content-Type": "application/json", "X-Office-Check": marker.content},
        body: JSON.stringify({checks, webgl_available: webglAvailable, draw_calls: Math.min(draws, 1000000), errors})});
      document.documentElement.dataset.nativeOfficeCheck = "done";
    }
  }, {once: true});
})();
