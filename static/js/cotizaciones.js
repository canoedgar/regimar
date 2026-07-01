(function(){
  const form = document.getElementById("cotizacionForm");
  if (!form) return;

  const logoUrl = form.dataset.logoUrl || "/static/resources/regimar.jpg";
  const panels = Array.from(document.querySelectorAll(".wizard-panel"));
  const indicators = Array.from(document.querySelectorAll(".wizard-step"));
  const badge = document.getElementById("cotStepBadge");
  const btnPrev = document.getElementById("btnPrev");
  const btnNext = document.getElementById("btnNext");
  const btnSubmit = document.getElementById("btnSubmit");
  const btnOpenPreviewPdf = document.getElementById("btnOpenPreviewPdf");
  const clienteSelect = form.querySelector('select[name="cliente"]');
  const clienteSearch = document.getElementById("clienteSearch");
  const clientesResults = document.getElementById("clientesResults");
  const clienteSelectedText = document.getElementById("clienteSelectedText");
  const btnClearCliente = document.getElementById("btnClearCliente");
  const clientesData = JSON.parse((document.getElementById("clientes-data") || {}).textContent || "[]");
  const productosData = JSON.parse((document.getElementById("productos-data") || {}).textContent || "[]");
  const productoSearch = document.getElementById("productoSearch");
  const productosResults = document.getElementById("productosResults");
  const selectedProducts = document.getElementById("selectedProducts");
  const selectedEmpty = document.getElementById("selectedEmpty");
  const itemsCount = document.getElementById("itemsCount");
  const detallesJson = document.getElementById("detallesJson");
  const preview = document.getElementById("cotizacionPreview");
  const previewCliente = document.getElementById("previewCliente");
  const previewTotal = document.getElementById("previewTotal");
  const previewUtilidad = document.getElementById("previewUtilidad");
  const fechaVigenciaInput = form.querySelector('input[name="fecha_vigencia"]');
  const fechaInput = document.getElementById("fechaCotizacion");
  const urlParams = new URLSearchParams(window.location.search);

  let step = 1;
  let selectedCliente = null;
  let clienteMatches = [];
  const selected = new Map();
  const inputTimers = new WeakMap();

  function norm(s){ return String(s || "").trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, ""); }
  function num(v){ const n = Number(v || 0); return Number.isFinite(n) ? n : 0; }
  function roundInt(v){ return Math.round(num(v)); }
  function money(v){ return num(v).toLocaleString("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 0, maximumFractionDigits: 0 }); }
  function money2(v){ return num(v).toLocaleString("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function escapeHtml(str){ return String(str || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;"); }

  function setStep(next){
    commitActiveField();
    step = Math.max(1, Math.min(4, next));
    panels.forEach(panel => panel.classList.toggle("d-none", Number(panel.dataset.step) !== step));
    indicators.forEach(ind => ind.classList.toggle("active", Number(ind.dataset.stepIndicator) === step));
    if (badge) badge.textContent = `Paso ${step} de 4`;
    if (btnPrev) btnPrev.disabled = step === 1;
    if (btnNext) btnNext.classList.toggle("d-none", step === 4);
    if (btnSubmit) btnSubmit.classList.toggle("d-none", step !== 4);
    if (step === 4) renderPreview();
  }

  function validateCurrentStep(){
    commitActiveField();
    if (step === 1 && !selectedCliente){ alert("Selecciona un cliente del sistema."); return false; }
    if (step === 2 && !fechaVigenciaInput.value){ alert("Selecciona la fecha de vencimiento."); return false; }
    if (step === 3 && selected.size === 0){ alert("Selecciona al menos un producto."); return false; }
    return true;
  }

  function renderClientesResults(query){
    const q = norm(query);
    clientesResults.innerHTML = "";
    clienteMatches = [];
    if (!q){ clientesResults.classList.add("d-none"); return; }
    clienteMatches = clientesData.filter(c => norm(`${c.nombre} ${c.rfc} ${c.contacto} ${c.telefono} ${c.email}`).includes(q)).slice(0, 12);
    if (!clienteMatches.length){
      clientesResults.innerHTML = '<div class="list-group-item text-muted small">Sin coincidencias. Puedes dar de alta un cliente nuevo.</div>';
      clientesResults.classList.remove("d-none");
      return;
    }
    clienteMatches.forEach(c => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-group-item list-group-item-action client-result-item";
      btn.innerHTML = `<div class="fw-semibold">${escapeHtml(c.nombre)}</div><div class="small text-muted">RFC: ${escapeHtml(c.rfc || "—")}${c.contacto ? " · Contacto: " + escapeHtml(c.contacto) : ""}${c.telefono ? " · Tel: " + escapeHtml(c.telefono) : ""}</div>`;
      btn.addEventListener("click", () => selectCliente(c));
      clientesResults.appendChild(btn);
    });
    clientesResults.classList.remove("d-none");
  }

  function selectCliente(c){
    selectedCliente = c;
    if (clienteSelect) clienteSelect.value = c.id;
    if (clienteSearch) clienteSearch.value = c.nombre;
    if (clienteSelectedText) clienteSelectedText.textContent = c.nombre;
    clientesResults.classList.add("d-none");
    renderPreview();
  }

  function clearCliente(){
    selectedCliente = null;
    if (clienteSelect) clienteSelect.value = "";
    if (clienteSearch) clienteSearch.value = "";
    if (clienteSelectedText) clienteSelectedText.textContent = "Sin cliente seleccionado";
  }

  function renderProductosResults(){
    const q = norm(productoSearch.value);
    const rows = productosData.filter(p => !selected.has(String(p.id)) && (!q || norm(`${p.nombre} ${p.metrica}`).includes(q))).slice(0, 50);
    productosResults.innerHTML = "";
    if (!rows.length){
      productosResults.innerHTML = '<div class="list-group-item text-muted small">Sin productos disponibles para agregar.</div>';
      return;
    }
    rows.forEach(p => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-group-item list-group-item-action cot-product-item";
      btn.innerHTML = `<div class="fw-semibold">${escapeHtml(p.nombre)}</div><div class="small text-muted">Costo ${money2(p.costo_base)} · Sugerido ${money(p.precio_sugerido)} · Mínimo ${money(p.precio_minimo)} / ${escapeHtml(p.metrica || "KG")}</div>`;
      btn.addEventListener("click", () => addProducto(p));
      productosResults.appendChild(btn);
    });
  }

  function addProducto(p){
    const costo = roundInt(p.costo_base || 0);
    const precio = roundInt(p.precio_sugerido || 0);
    const utilidad = roundInt(precio - costo);
    const margen = costo > 0 ? roundInt(((precio - costo) / costo) * 100) : 0;
    selected.set(String(p.id), {
      producto_id: p.id,
      nombre: p.nombre,
      metrica: p.metrica || "KG",
      costo_base: costo,
      precio_sugerido: roundInt(p.precio_sugerido || 0),
      precio_minimo: roundInt(p.precio_minimo || 0),
      precio_propuesto: precio,
      margen_pesos: utilidad,
      margen_porcentaje: margen,
      maneja_peso_variable: !!p.maneja_peso_variable,
    });
    productoSearch.value = "";
    renderProductosResults();
    renderSelectedProducts();
  }

  function recalcFromPrice(item){
    item.precio_propuesto = roundInt(item.precio_propuesto);
    item.margen_pesos = roundInt(item.precio_propuesto - item.costo_base);
    item.margen_porcentaje = item.costo_base > 0 ? roundInt((item.margen_pesos / item.costo_base) * 100) : 0;
  }

  function recalcFromPesos(item){
    item.margen_pesos = roundInt(item.margen_pesos);
    item.precio_propuesto = roundInt(item.costo_base + item.margen_pesos);
    item.margen_porcentaje = item.costo_base > 0 ? roundInt((item.margen_pesos / item.costo_base) * 100) : 0;
  }

  function recalcFromPercent(item){
    item.margen_porcentaje = roundInt(item.margen_porcentaje);
    item.margen_pesos = roundInt(item.costo_base * (item.margen_porcentaje / 100));
    item.precio_propuesto = roundInt(item.costo_base + item.margen_pesos);
  }

  function hasWarning(item){
    return item.precio_minimo > 0 && normalizedItemValue(item, "precio_propuesto") < item.precio_minimo;
  }

  function updateCardFields(card, item, activeInput){
    card.querySelectorAll("input[data-field]").forEach(input => {
      if (input !== activeInput) input.value = normalizedItemValue(item, input.dataset.field);
    });
    const warning = card.querySelector(".cot-price-warning");
    if (warning) warning.classList.toggle("d-none", !hasWarning(item));
    syncPayload();
    renderPreview();
  }

  function commitInput(input){
    if (!input || !input.matches("input[data-field]")) return;
    const item = selected.get(String(input.dataset.productId));
    if (!item || input.value === "") return;
    const field = input.dataset.field;
    item[field] = field === "margen_pesos" ? Math.max(-999999, roundInt(input.value)) : Math.max(0, roundInt(input.value));
    if (field === "precio_propuesto") recalcFromPrice(item);
    if (field === "margen_pesos") recalcFromPesos(item);
    if (field === "margen_porcentaje") recalcFromPercent(item);
    updateCardFields(input.closest(".cot-product-card"), item, input);
  }

  function commitActiveField(){
    const active = document.activeElement;
    if (active && active.matches && active.matches("input[data-field]")) commitInput(active);
  }

  function scheduleInputCommit(input){
    const oldTimer = inputTimers.get(input);
    if (oldTimer) clearTimeout(oldTimer);
    const timer = setTimeout(() => {
      if (document.activeElement === input && input.value !== "") commitInput(input);
    }, 650);
    inputTimers.set(input, timer);
  }

  function renderSelectedProducts(){
    selectedProducts.innerHTML = "";
    if (selectedEmpty) selectedEmpty.classList.toggle("d-none", selected.size > 0);
    if (itemsCount) itemsCount.textContent = selected.size;

    selected.forEach(item => {
      const card = document.createElement("article");
      card.className = "cot-product-card";
      card.dataset.productId = item.producto_id;
      const warning = hasWarning(item);
      card.innerHTML = `
        <div class="cot-product-card-header">
          <div><div class="cot-product-card-title">${escapeHtml(item.nombre)}</div><div class="small text-muted">Precio por ${escapeHtml(item.metrica)}</div></div>
          <button type="button" class="sg-btn-outline sg-btn-sm cot-product-card-remove" data-action="remove"><i class="bi bi-trash"></i><span>Eliminar</span></button>
        </div>
        <div class="cot-ref-grid">
          <div class="cot-ref"><span>Costo</span><strong>${money(item.costo_base)}</strong></div>
          <div class="cot-ref"><span>Sugerido</span><strong>${money(item.precio_sugerido)}</strong></div>
          <div class="cot-ref"><span>Mínimo</span><strong>${money(item.precio_minimo)}</strong></div>
        </div>
        <div class="alert alert-warning py-2 small mb-2 cot-price-warning ${warning ? "" : "d-none"}">El precio está por debajo del mínimo de referencia.</div>
        <div class="cot-edit-grid cot-edit-grid-prices">
          <div><label>Margen $</label><input class="form-control form-control-sm" type="number" inputmode="numeric" step="1" data-product-id="${escapeHtml(item.producto_id)}" data-field="margen_pesos" value="${normalizedItemValue(item, "margen_pesos")}"></div>
          <div><label>Margen %</label><input class="form-control form-control-sm" type="number" inputmode="numeric" step="1" data-product-id="${escapeHtml(item.producto_id)}" data-field="margen_porcentaje" value="${normalizedItemValue(item, "margen_porcentaje")}"></div>
          <div><label>Precio de venta</label><input class="form-control form-control-sm" type="number" inputmode="numeric" min="0" step="1" data-product-id="${escapeHtml(item.producto_id)}" data-field="precio_propuesto" value="${normalizedItemValue(item, "precio_propuesto")}"></div>
        </div>`;

      card.querySelector('[data-action="remove"]').addEventListener("click", () => {
        selected.delete(String(item.producto_id));
        renderProductosResults();
        renderSelectedProducts();
      });

      card.querySelectorAll("input[data-field]").forEach(input => {
        input.addEventListener("input", () => {
          const field = input.dataset.field;
          item[field] = input.value;
          syncPayload();
          scheduleInputCommit(input);
        });
        input.addEventListener("change", () => commitInput(input));
        input.addEventListener("blur", () => commitInput(input));
      });
      selectedProducts.appendChild(card);
    });
    syncPayload();
    renderPreview();
  }

  function normalizedItemValue(item, field){
    if (field === "margen_pesos") return Math.max(-999999, roundInt(item[field]));
    return Math.max(0, roundInt(item[field]));
  }

  function syncPayload(){
    const payload = Array.from(selected.values()).map(item => ({
      producto_id: item.producto_id,
      cantidad_estimada: 1,
      cantidad_cajas: null,
      costo_base: item.costo_base,
      precio_sugerido: item.precio_sugerido,
      precio_minimo: item.precio_minimo,
      precio_propuesto: normalizedItemValue(item, "precio_propuesto"),
      margen_porcentaje: normalizedItemValue(item, "margen_porcentaje"),
      margen_pesos: normalizedItemValue(item, "margen_pesos"),
    }));
    detallesJson.value = JSON.stringify(payload);
  }

  function renderPreview(){
    const items = Array.from(selected.values());
    if (previewCliente) previewCliente.textContent = selectedCliente ? selectedCliente.nombre : "—";
    if (previewTotal) previewTotal.textContent = `${items.length} seleccionado${items.length === 1 ? "" : "s"}`;
    if (previewUtilidad) previewUtilidad.textContent = "Lista de precios";
    if (!preview) return;
    preview.innerHTML = buildPreviewSheetHtml(items);
  }

  function buildPreviewSheetHtml(items){
    return `
      <div class="cot-preview-top">
        <div class="cot-preview-brand"><img src="${escapeHtml(logoUrl)}" alt="Regimar"><div><strong>Regimar</strong><div class="small text-muted">Regimar</div></div></div>
        <div class="cot-preview-meta"><div class="cot-preview-title">COTIZACIÓN</div><div><strong>Fecha:</strong> ${escapeHtml(fechaInput ? fechaInput.value : "")}</div><div><strong>Vigencia:</strong> ${escapeHtml(fechaVigenciaInput ? fechaVigenciaInput.value : "")}</div></div>
      </div>
      <p class="mt-3 mb-2">Atendiendo a su amable solicitud enviamos la cotización correspondiente quedando a sus órdenes.</p>
      <table class="cot-preview-info"><tr><th>Cliente</th><td>${escapeHtml(selectedCliente ? selectedCliente.nombre : "—")}</td></tr><tr><th>Dirección</th><td>${escapeHtml(selectedCliente ? selectedCliente.direccion : "—")}</td></tr><tr><th>Contacto</th><td>${escapeHtml(selectedCliente ? (selectedCliente.contacto || selectedCliente.telefono || selectedCliente.email || "—") : "—")}</td></tr></table>
      <table class="cot-preview-table"><thead><tr><th>Producto</th><th class="num">Precio de venta</th></tr></thead><tbody>
        ${items.map(i => `<tr><td>${escapeHtml(i.nombre)}</td><td class="num">${money(normalizedItemValue(i, "precio_propuesto"))} / ${escapeHtml(i.metrica)}</td></tr>`).join("")}
      </tbody></table>
      <div class="cot-preview-note">Los precios indicados respetan la vigencia de esta cotización. La presente cotización no representa apartado de producto ni compromiso de inventario.</div>`;
  }

  function openPrintablePreview(){
    if (!validateCurrentStep()) return;
    commitActiveField();
    renderPreview();
    const printWindow = window.open("", "_blank", "noopener,noreferrer");
    if (!printWindow){
      alert("Permite las ventanas emergentes para abrir la vista PDF.");
      return;
    }
    const html = `<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Vista PDF - Cotización</title><style>
      @page { size: letter; margin: 12mm; }
      * { box-sizing: border-box; }
      body { margin: 0; padding: 12px; background: #f7f2ea; color: #201f1d; font-family: Arial, sans-serif; font-size: 12px; }
      .actions { max-width: 780px; margin: 0 auto 12px; text-align: right; }
      .actions button { padding: 8px 12px; border: 0; background: #9f1117; color: #fff; border-radius: 6px; }
      .cot-preview-sheet { max-width: 780px; min-height: 960px; margin: 0 auto; background: #fff; color: #201f1d; padding: 24px; box-shadow: 0 10px 30px rgba(15, 23, 42, .12); }
      .cot-preview-top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; border-bottom: 2px solid #9f1117; padding-bottom: 12px; }
      .cot-preview-brand { display: flex; gap: 12px; align-items: center; }
      .cot-preview-brand img { width: 86px; max-height: 70px; object-fit: contain; }
      .cot-preview-title { margin: 0; font-size: 25px; letter-spacing: 2px; color: #9f1117; font-weight: 800; }
      .cot-preview-meta { text-align: right; line-height: 1.6; }
      .text-muted { color: #6b6259; }
      .cot-preview-info { width: 100%; border-collapse: collapse; margin: 18px 0; }
      .cot-preview-info th { text-align: left; width: 90px; color: #4b4540; padding: 5px; vertical-align: top; }
      .cot-preview-info td { border-bottom: 1px solid #e8ded2; padding: 5px; }
      .cot-preview-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
      .cot-preview-table th { background: #9f1117; color: #fff; text-align: left; padding: 8px; }
      .cot-preview-table td { padding: 8px; border-bottom: 1px solid #e8ded2; vertical-align: top; }
      .cot-preview-table .num { text-align: right; white-space: nowrap; }
      .cot-preview-note { margin-top: 18px; font-size: 11px; color: #4b4540; line-height: 1.5; }
      @media print { body { padding: 0; background: #fff; } .actions { display: none; } .cot-preview-sheet { box-shadow: none; min-height: auto; } }
      @media (max-width: 576px) { body { padding: 0; } .actions { padding: 10px; } .cot-preview-sheet { width: 100%; min-height: auto; padding: 18px; box-shadow: none; } }
    </style></head><body><div class="actions"><button onclick="window.print()">Imprimir / Guardar PDF</button></div><div class="cot-preview-sheet">${buildPreviewSheetHtml(Array.from(selected.values()))}</div></body></html>`;
    printWindow.document.open();
    printWindow.document.write(html);
    printWindow.document.close();
  }

  clienteSearch && clienteSearch.addEventListener("input", () => renderClientesResults(clienteSearch.value));
  btnClearCliente && btnClearCliente.addEventListener("click", clearCliente);
  productoSearch && productoSearch.addEventListener("input", renderProductosResults);
  btnPrev && btnPrev.addEventListener("click", () => setStep(step - 1));
  btnNext && btnNext.addEventListener("click", () => { if (validateCurrentStep()) setStep(step + 1); });
  btnOpenPreviewPdf && btnOpenPreviewPdf.addEventListener("click", openPrintablePreview);
  form.addEventListener("submit", (e) => {
    commitActiveField();
    if (!selectedCliente || selected.size === 0){
      e.preventDefault();
      alert("Selecciona cliente y al menos un producto antes de guardar.");
      return;
    }
    syncPayload();
  });

  function selectInitialCliente(){
    const initialClienteId = urlParams.get("cliente_id") || (clienteSelect ? clienteSelect.value : "");
    if (!initialClienteId) return;
    const cliente = clientesData.find(c => String(c.id) === String(initialClienteId));
    if (cliente) selectCliente(cliente);
  }

  selectInitialCliente();
  renderProductosResults();
  renderSelectedProducts();
  setStep(1);
})();
