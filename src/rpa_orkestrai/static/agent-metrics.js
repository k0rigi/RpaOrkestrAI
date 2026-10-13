"use strict";
(() => {
  let sequence = 0;
  const el = (tag, text, css = "") => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (css) node.className = css;
    return node;
  };
  const identify = (node) => { node.id = `agent-metric-${++sequence}`; return node; };
  function control(label, kind = "input") {
    const wrap = el("div", undefined, "agent-field"), node = identify(el(kind));
    const caption = el("label", label); caption.htmlFor = node.id;
    wrap.append(caption, node); return { wrap, node };
  }
  function button(text, work) {
    const node = identify(el("button", text, "button")); node.type = "button";
    node.addEventListener("click", work); return node;
  }
  const number = (value) => Number(value || 0).toLocaleString("tr-TR", { maximumFractionDigits: 2 });
  const duration = (value) => `${number(Number(value || 0) / 60)} dk`;
  function mount(container, options) {
    let alive = true, pending = false, local = null, humans = null, members = [], prices = [], connections = [];
    const request = (path, method = "GET", body) => options.api(path, {
      method, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
    const error = (value) => { if (alive) options.toast(value?.message || "Performans yüklenemedi.", true); };
    const period = control("Dönem", "select"), start = control("İlk gün"), end = control("Son gün");
    for (const [value, label] of [["today", "Bugün"], ["week", "Bu hafta"], ["month", "Bu ay"], ["custom", "Özel aralık"]]) {
      const option = el("option", label); option.value = value; period.node.append(option);
    }
    start.node.type = end.node.type = "date";
    const day = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
    function setDates() {
      const now = new Date(), first = new Date(now);
      if (period.node.value === "week") first.setDate(first.getDate() - (first.getDay() + 6) % 7);
      if (period.node.value === "month") first.setDate(1);
      if (period.node.value !== "custom") { start.node.value = day(first); end.node.value = day(now); }
      start.node.disabled = end.node.disabled = period.node.value !== "custom";
    }
    function query() {
      if (!start.node.value || !end.node.value) throw new Error("Başlangıç ve bitiş günü seçin.");
      const first = new Date(`${start.node.value}T00:00:00`), last = new Date(`${end.node.value}T00:00:00`);
      last.setDate(last.getDate() + 1);
      if (!(first < last) || last - first > 366 * 86400000) throw new Error("En fazla 366 günlük geçerli bir aralık seçin.");
      return new URLSearchParams({ start: first.toISOString(), end: last.toISOString() }).toString();
    }
    setDates();
    const controls = el("div", undefined, "agent-toolbar");
    const output = el("section"), humanOutput = el("section");
    const exportLink = identify(el("a", "Ajan CSV indir", "button")); exportLink.hidden = true;
    exportLink.download = "ajan-performansi.csv";
    const exportHumans = button("İnsan CSV indir", () => {
      if (!humans) return;
      const safe = (value) => {
        let text = String(value ?? "");
        if (/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`;
        return `"${text.replaceAll('"', '""')}"`;
      };
      const rows = [["Çalışan", "Toplam", "Tamamlanan", "Başarısız", "İptal", "Başarı oranı", "Toplam saniye", "Ortalama saniye"]];
      for (const row of humans.users) rows.push([members.find((m) => m.kullanici_id === row.user_id)?.ad_soyad || `Çalışan ${row.user_id}`,
        row.total, row.succeeded, row.failed, row.cancelled, row.success_rate, row.total_seconds, row.average_seconds]);
      const url = URL.createObjectURL(new Blob(["\ufeff", rows.map((row) => row.map(safe).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8" }));
      const link = identify(el("a")); link.href = url; link.download = "insan-performansi.csv";
      link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    exportHumans.hidden = true;
    controls.append(period.wrap, start.wrap, end.wrap, button("Hesapla", load), exportLink, exportHumans);
    period.node.addEventListener("change", () => { setDates(); if (period.node.value !== "custom") load(); });
    container.append(el("h2", "Performans"), el("p", "Dönem, görevin oluşturulduğu güne göre seçilir. Tarihler bu bilgisayarın saat dilimindedir. Başarı oranı tamamlanan / (tamamlanan + başarısız + iptal) olarak hesaplanır.", "agent-help"),
      controls, output, humanOutput);
    const groups = control("Ajanları grupla", "select");
    for (const [value, label] of [["agents", "Ajan"], ["departments", "Departman"]]) {
      const option = el("option", label); option.value = value; groups.node.append(option);
    }
    controls.append(groups.wrap); groups.node.addEventListener("change", render);
    const sort = control("Sıralama", "select");
    for (const [value, label] of [["succeeded", "Tamamlanan"], ["failed", "Başarısız"], ["total_seconds", "Toplam süre"], ["total_tokens", "Token"]]) {
      const option = el("option", label); option.value = value; sort.node.append(option);
    }
    controls.append(sort.wrap); sort.node.addEventListener("change", render);

    function table(rows, human = false) {
      const wrap = el("div", undefined, "agent-metric-table"), result = el("table"), header = el("tr");
      const titles = ["Çalışan", "Toplam", "Tamamlanan", "Başarısız", "İptal", "Başarı", "Toplam süre", "Ortalama süre"];
      if (!human) titles.push("Akış", "Onay", "Onay bekleme", "Token", "Tahmini maliyet");
      for (const title of titles) { const th = el("th", title); th.scope = "col"; header.append(th); }
      const head = el("thead"); head.append(header); const body = el("tbody");
      for (const row of rows) {
        const tr = el("tr"), values = [row.name, number(row.total), number(row.succeeded), number(row.failed), number(row.cancelled),
          `%${number(row.success_rate * 100)}`, duration(row.total_seconds), duration(row.average_seconds)];
        if (!human) values.push(number(row.workflow_count), number(row.approval_count), duration(row.approval_wait_seconds),
          number(row.total_tokens), Object.entries(row.estimated_cost || {}).map(([currency, cost]) => `${number(cost)} ${currency}`).join(" · ") || "Fiyat girilmedi");
        for (const value of values) tr.append(el("td", value)); body.append(tr);
      }
      result.append(head, body); wrap.append(result); return wrap;
    }
    function chart(rows) {
      const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg");
      const shown = rows.slice(0, 10), height = Math.max(60, shown.length * 34);
      svg.setAttribute("viewBox", `0 0 700 ${height}`); svg.classList.add("agent-metric-chart");
      svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Tamamlanan görevler. Aynı değerler aşağıdaki tabloda bulunur.");
      const max = Math.max(1, ...shown.map((row) => row.succeeded));
      shown.forEach((row, index) => {
        const text = document.createElementNS(ns, "text"); text.textContent = row.name; text.setAttribute("x", "0"); text.setAttribute("y", String(index * 34 + 22));
        const bar = document.createElementNS(ns, "rect"); bar.setAttribute("x", "220"); bar.setAttribute("y", String(index * 34 + 6));
        bar.setAttribute("width", String(row.succeeded / max * 420)); bar.setAttribute("height", "22"); bar.setAttribute("rx", "4");
        const title = document.createElementNS(ns, "title"); title.textContent = `${row.name}: ${row.succeeded}`; bar.append(title); svg.append(text, bar);
      }); return svg;
    }
    function render() {
      if (!alive || !local) return;
      const totals = local.totals, rows = [...local[groups.node.value]].sort((a, b) => b[sort.node.value] - a[sort.node.value]);
      output.replaceChildren(el("h3", "Bu bilgisayardaki ajan görevleri"),
        el("p", `${totals.succeeded} tamamlandı · ${totals.failed} başarısız · ${totals.cancelled} iptal · ${number(totals.total_tokens)} token`),
        chart(rows), table(rows));
      output.append(el("p", "Süreler sonlanan görevlerin başlangıç ve bitişi arasındadır; beklemeler dahildir. Paralel görevlerin süreleri toplanır. Maliyet, burada girilen güncel fiyatlarla tahmin edilir; fatura tutarı değildir.", "agent-help"));
      if (totals.duration_missing_count) output.append(el("p", `${totals.duration_missing_count} görevde süre bilgisi eksik; süre hesabında 0 kabul edildi.`, "agent-warning"));
      if (totals.unpriced_tasks) output.append(el("p", `${totals.unpriced_tasks} görev için model fiyatı tanımlı değil.`, "agent-help"));
      if (humans) {
        exportHumans.hidden = false;
        const humanRows = humans.users.map((row) => ({ ...row,
          name: members.find((item) => item.kullanici_id === row.user_id)?.ad_soyad || `Çalışan ${row.user_id}` }));
        humanOutput.replaceChildren(el("h3", "Kurumdaki insan görevleri"), table(humanRows, true),
          el("p", "İnsan süreleri Studio'da bildirilen başlangıç/bitiş durumlarından hesaplanır. Kullanıcılar kendi görevlerini, yetkili kurumun görevlerini görür. İnsan hesaplarında departman tanımı bulunmadığından departman dağılımı verilmez.", "agent-help"));
      }
    }
    async function load() {
      if (!alive || pending) return;
      pending = true; container.setAttribute("aria-busy", "true");
      try {
        const suffix = query();
        const data = await request(`/api/agents/metrics?${suffix}`);
        if (!alive) return;
        local = data; exportLink.href = `/api/agents/metrics/csv?${suffix}`; exportLink.hidden = false; render();
        try {
          const [humanData, memberData] = await Promise.all([request(`/api/agents/central/metrics?${suffix}`), request("/api/agents/central/members")]);
          if (!alive) return;
          humans = humanData.metrics; members = memberData.uyeler || []; render();
        } catch (problem) {
          if (alive) { humans = null; exportHumans.hidden = true; humanOutput.replaceChildren(el("h3", "İnsan görevleri"), el("p", problem.message, "agent-warning")); }
        }
      } catch (problem) { error(problem); }
      finally { pending = false; container.removeAttribute("aria-busy"); }
    }

    if (options.session.can_manage) {
      const panel = el("details", undefined, "agent-panel"); identify(panel);
      panel.append(identify(el("summary", "Model fiyatları (isteğe bağlı)")));
      const priceList = el("div"), form = identify(el("form"));
      const connection = control("Sağlayıcı bağlantısı", "select"), model = control("Model"), currency = control("Para birimi (ör. USD)");
      const input = control("1 milyon girdi token fiyatı"), outputPrice = control("1 milyon çıktı token fiyatı");
      input.node.type = outputPrice.node.type = "number"; input.node.min = outputPrice.node.min = "0";
      input.node.step = outputPrice.node.step = "any"; currency.node.value = "USD"; currency.node.pattern = "[A-Z]{3}";
      for (const field of [connection, model, currency, input, outputPrice]) { field.node.required = true; form.append(field.wrap); }
      const save = identify(el("button", "Fiyatı kaydet", "button")); save.type = "submit"; form.append(save);
      connection.node.addEventListener("change", () => { model.node.value = connections.find((c) => c.id === connection.node.value)?.model || ""; });
      function renderPrices() {
        priceList.replaceChildren();
        prices.forEach((price) => {
          const row = el("p", `${connections.find((c) => c.id === price.connection_id)?.name || "Bağlantı"} · ${price.model}: ${price.input_per_million} / ${price.output_per_million} ${price.currency} `);
          row.append(button("Kaldır", async () => {
            try { const answer = await request("/api/agents/metrics/settings", "PUT", { prices: prices.filter((p) => p !== price) }); if (alive) { prices = answer.prices; renderPrices(); load(); } } catch (problem) { error(problem); }
          })); priceList.append(row);
        });
      }
      form.addEventListener("submit", async (event) => {
        event.preventDefault(); if (!form.reportValidity()) return;
        const value = { connection_id: connection.node.value, model: model.node.value.trim(), currency: currency.node.value.trim(),
          input_per_million: Number(input.node.value), output_per_million: Number(outputPrice.node.value) };
        try {
          const answer = await request("/api/agents/metrics/settings", "PUT", {
            prices: [...prices.filter((p) => p.connection_id !== value.connection_id || p.model !== value.model), value],
          }); if (alive) { prices = answer.prices; renderPrices(); load(); }
        } catch (problem) { error(problem); }
      });
      panel.append(el("p", "Ücretsiz yerel model için fiyat girmek gerekmez. Farklı para birimleri birbirine çevrilmez.", "agent-help"), priceList, form); container.append(panel);
      Promise.all([request("/api/agents/metrics/settings"), request("/api/agents/connections")]).then(([data, values]) => {
        if (!alive) return; prices = data.prices; connections = values;
        for (const value of values) { const item = el("option", value.name); item.value = value.id; connection.node.append(item); }
        model.node.value = values[0]?.model || ""; renderPrices();
      }).catch(error);
    }
    load();
    return () => { alive = false; };
  }
  window.RpaAgents.registerTab({ id: "performance", label: "Performans", mount });
})();
