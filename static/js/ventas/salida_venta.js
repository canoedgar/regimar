(function(){
  const form = document.getElementById("ventaForm");
  if (!form) return;
  const logoUrls = {
    CPC: form.dataset.logoCpcUrl || form.dataset.logoUrl || "/static/resources/cpcnota.png",
    BAJA_BACON: form.dataset.logoBajaBaconUrl || "/static/resources/bajabaconnota.png",
  };
  const initialStep = Number(form.dataset.initialStep || "1");
  const btnPrev = document.getElementById("btnPrev");
  const btnNext = document.getElementById("btnNext");
  const btnSubmit = document.getElementById("btnSubmit");
  const badge = document.getElementById("stepBadge");
  const panels = Array.from(document.querySelectorAll(".wizard-panel"));
  const indicators = Array.from(document.querySelectorAll(".wizard-step"));

  const clienteRefReal = form.querySelector('select[name="cliente_ref"]');
  const clienteInputReal = form.querySelector('input[name="cliente"]');
  const formaPagoReal = form.querySelector('select[name="forma_pago_venta"]');
  const estadoPagoReal = form.querySelector('select[name="estado_pago"]');
  const logoNotaReal = form.querySelector('select[name="logo_nota"]');
  const confirmarEnvioAutorizacionPrecio = document.getElementById("confirmarEnvioAutorizacionPrecio");
  const clienteSearch = document.getElementById("clienteSearch");
  const clientesResults = document.getElementById("clientesResults");
  const clienteSelectedText = document.getElementById("clienteSelectedText");
  const btnClearCliente = document.getElementById("btnClearCliente");
  const clienteDireccionVenta = document.getElementById("clienteDireccionVenta");
  const clienteContactoVenta = document.getElementById("clienteContactoVenta");
  const clienteDireccionReal = form.querySelector('textarea[name="cliente_direccion"]');
  const clienteContactoReal = form.querySelector('input[name="cliente_contacto"]');
  const clientesData = JSON.parse((document.getElementById("clientes-data") ? document.getElementById("clientes-data").textContent : "") || "[]");
  const urlParams = new URLSearchParams(window.location.search);

  const productosData = JSON.parse(document.getElementById("productos-data").textContent || "[]");
  const productoSearch = document.getElementById("productoSearch");
  const productoQty = document.getElementById("productoQty");
  const productoQtyLabel = document.getElementById("productoQtyLabel");
  const productoCajasWrap = document.getElementById("productoCajasWrap");
  const productoCajas = document.getElementById("productoCajas");
  const productoPrecio = document.getElementById("productoPrecio");
  const productoAlmacenSelect = document.getElementById("productoAlmacenSelect");
  const productoAlmacenStockText = document.getElementById("productoAlmacenStockText");
  const btnAddProducto = document.getElementById("btnAddProducto");
  const productosResults = document.getElementById("productosResults");
  const productosEmptyState = document.getElementById("productosEmptyState");
  const selectedProductoNombre = document.getElementById("selectedProductoNombre");
  const selectedProductoStock = document.getElementById("selectedProductoStock");
  const selectedProductoPrecio = document.getElementById("selectedProductoPrecio");
  const productoPresentacionSelect = document.getElementById("productoPresentacionSelect");
  const productoPresentacionText = document.getElementById("productoPresentacionText");
  const selectedPresentacionInfo = document.getElementById("selectedPresentacionInfo");
  const productoQtyHelp = document.getElementById("productoQtyHelp");
  const productoPrecioClienteWarn = document.getElementById("productoPrecioClienteWarn");
  const productoPrecioError = document.getElementById("productoPrecioError");
  const precioMinimoModalEl = document.getElementById("precioMinimoModal");
  // El modal se declara dentro del layout principal, pero Bootstrap agrega el backdrop
  // directamente al <body>. Si algún contenedor del layout crea un stacking context,
  // el backdrop puede quedar por encima del modal y bloquear toda la pantalla.
  // Por eso se mueve el modal al <body> antes de inicializar Bootstrap.
  if (precioMinimoModalEl && precioMinimoModalEl.parentElement !== document.body){
    document.body.appendChild(precioMinimoModalEl);
  }
  const precioMinimoModal = precioMinimoModalEl && window.bootstrap ? bootstrap.Modal.getOrCreateInstance(precioMinimoModalEl) : null;
  const btnConfirmPrecioMinimo = document.getElementById("btnConfirmPrecioMinimo");
  const precioMinimoModalProducto = document.getElementById("precioMinimoModalProducto");
  const precioMinimoModalCapturado = document.getElementById("precioMinimoModalCapturado");
  const precioMinimoModalMinimo = document.getElementById("precioMinimoModalMinimo");

  const cartList = document.getElementById("cartList");
  const cartEmpty = document.getElementById("cartEmpty");
  const cartCount = document.getElementById("cartCount");
  const cartTotal = document.getElementById("cartTotal");
  const cartSubtotal = document.getElementById("cartSubtotal");
  const cartCommissionRow = document.getElementById("cartCommissionRow");
  const cartCommissionPercent = document.getElementById("cartCommissionPercent");
  const cartCommissionAmount = document.getElementById("cartCommissionAmount");
  const cartGrandTotal = document.getElementById("cartGrandTotal");
  const allocationsPayload = document.getElementById("allocationsPayload");

  const totalForms = form.querySelector('input[name$="-TOTAL_FORMS"]');
  const initialForms = form.querySelector('input[name$="-INITIAL_FORMS"]');
  const hiddenTbody = document.getElementById("hiddenFormsetTbody");
  const hiddenTpl = document.getElementById("hiddenRowTemplate");
  const ticketPreview = document.getElementById("ticketPreview");

  const folioInput = form.querySelector('input[name="folio"]');
  const fechaInput = form.querySelector('input[name="fecha"]');
  if (folioInput){
    folioInput.readOnly = true;
    folioInput.setAttribute("readonly", "readonly");
    folioInput.setAttribute("tabindex", "-1");
    folioInput.classList.add("bg-body-secondary");
  }
  if (fechaInput){
    fechaInput.type = "date";
    fechaInput.setAttribute("type", "date");
    normalizeDateInputValue(fechaInput);
  }

  let step = 1;
  const totalSteps = 4;
  let selectedClienteId = "";
  let clienteMatches = [];
  let highlightedClienteIndex = -1;
  let selectedProducto = null;
  let filteredProductos = [];
  let highlightedIndex = -1;
  const cart = new Map();
  const preciosMinimosConfirmados = new Set();
  let pendingPrecioMinimoAdd = null;

  function moneyUnit(n){
    return Number(n || 0).toLocaleString("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 0, maximumFractionDigits: 0 });
  }

  function moneyAmount(n){
    return Number(n || 0).toLocaleString("es-MX", { style: "currency", currency: "MXN", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function norm(s){
    return (s || "").trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function escapeHtml(str){
    return String(str || "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function getSelectedLogoUrl(){
    const value = logoNotaReal ? String(logoNotaReal.value || "CPC") : "CPC";
    return logoUrls[value] || logoUrls.CPC;
  }

  function decimal(v){
    const n = Number(v || 0);
    return Number.isFinite(n) ? n : 0;
  }

  function esAlmacenVentaSinStock(almacen){
    return !!(almacen && (almacen.permite_venta_sin_stock || almacen.es_virtual_sistema || String(almacen.tipo || "").toUpperCase() === "VIRTUAL"));
  }

  function getAlmacenLabel(almacen){
    if (!almacen) return "";
    return almacen.label || `${almacen.codigo || ""} - ${almacen.nombre || ""}`.trim();
  }

  function blockInvalidNumberKeys(e){
    if (["-", "+", "e", "E"].includes(e.key)){
      e.preventDefault();
    }
  }

  function normalizeDateInputValue(input){
    if (!input) return;
    const value = String(input.value || "").trim();
    if (!value) return;
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return;
    const match = value.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
    if (match){
      const dd = match[1].padStart(2, "0");
      const mm = match[2].padStart(2, "0");
      const yyyy = match[3];
      input.value = `${yyyy}-${mm}-${dd}`;
    }
  }

  function formatPlainNumber(value, maxDecimals = 2){
    const n = decimal(value);
    return n.toLocaleString("es-MX", { minimumFractionDigits: 0, maximumFractionDigits: maxDecimals });
  }

  function getPresentaciones(producto){
    return (producto && Array.isArray(producto.conversiones)) ? producto.conversiones : [];
  }

  function getSelectedPresentacion(){
    if (!selectedProducto || !productoPresentacionSelect) return null;
    return getPresentaciones(selectedProducto).find(p => String(p.id) === String(productoPresentacionSelect.value)) || null;
  }


  function selectMetricaBaseProducto(producto){
    if (!productoPresentacionSelect) return;
    const presentaciones = getPresentaciones(producto);
    const base = presentaciones.find(p => p.es_default || String(p.id) === "default") || presentaciones[0];
    productoPresentacionSelect.value = base ? String(base.id) : "";
  }

  function limpiarAlmacenSeleccionado(){
    if (!productoAlmacenSelect) return;
    productoAlmacenSelect.value = "";
  }

  function esProductoPesoVariable(producto){
    return !!(producto && producto.maneja_peso_variable);
  }

  function esItemPesoVariable(item){
    return !!(
      item && (
        item.es_peso_variable ||
        item.maneja_peso_variable ||
        String(item.equivalencia_texto || '').toLowerCase().includes('peso variable')
      )
    );
  }

  function getCajasCapturadas(){
    if (!productoCajas) return 0;
    return decimal(productoCajas.value || 0);
  }

  function syncPesoVariableUI(){
    const variable = esProductoPesoVariable(selectedProducto);
    if (productoQtyLabel){ productoQtyLabel.textContent = variable ? "Kilos" : "Cantidad"; }
    if (productoCajasWrap){ productoCajasWrap.classList.toggle("d-none", !variable); }
    if (productoCajas){
      productoCajas.disabled = !variable || !selectedProducto;
      if (!variable) productoCajas.value = "";
    }
  }

  function getCartKey(productoId, presentacionId){
    return `${productoId}::${presentacionId}`;
  }

  function syncClienteExtras(){
    if (clienteDireccionReal) clienteDireccionReal.value = (clienteDireccionVenta ? clienteDireccionVenta.value : '') || "";
    if (clienteContactoReal) clienteContactoReal.value = (clienteContactoVenta ? clienteContactoVenta.value : '') || "";
  }

  function renderClientesResults(query){
    if (!clientesResults) return;
    const q = norm(query);
    clientesResults.innerHTML = "";
    clienteMatches = [];
    highlightedClienteIndex = -1;
    if (!q){ clientesResults.classList.add("d-none"); return; }
    clienteMatches = clientesData.filter(c => norm(`${c.nombre} ${c.rfc} ${c.telefono || ""} ${c.contacto || ""} ${c.email || ""}`).includes(q)).slice(0, 12);
    if (!clienteMatches.length){
      clientesResults.innerHTML = '<div class="list-group-item text-muted small">Sin coincidencias. Selecciona un cliente existente o da de alta uno nuevo.</div>';
      clientesResults.classList.remove("d-none");
      return;
    }
    highlightedClienteIndex = 0;
    clienteMatches.forEach((c, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "list-group-item list-group-item-action client-result-item";
      if (idx === highlightedClienteIndex) btn.classList.add("active");
      btn.innerHTML = `<div class="fw-semibold">${escapeHtml(c.nombre)}</div><div class="small ${idx === highlightedClienteIndex ? '' : 'text-muted'}">RFC: ${escapeHtml(c.rfc)}${c.contacto ? ' · Contacto: ' + escapeHtml(c.contacto) : ''}${c.telefono ? ' · Tel: ' + escapeHtml(c.telefono) : ''}</div>`;
      btn.addEventListener("click", () => selectCliente(c));
      clientesResults.appendChild(btn);
    });
    clientesResults.classList.remove("d-none");
  }

  function moveClienteHighlight(delta){
    if (!clienteMatches.length) return;
    highlightedClienteIndex += delta;
    if (highlightedClienteIndex < 0) highlightedClienteIndex = clienteMatches.length - 1;
    if (highlightedClienteIndex >= clienteMatches.length) highlightedClienteIndex = 0;
    Array.from(clientesResults.querySelectorAll(".client-result-item")).forEach((el, idx) => {
      el.classList.toggle("active", idx === highlightedClienteIndex);
      const meta = el.querySelector(".small");
      if (meta) meta.classList.toggle("text-muted", idx !== highlightedClienteIndex);
    });
  }

  function selectHighlightedCliente(){
    if (highlightedClienteIndex < 0 || !clienteMatches[highlightedClienteIndex]) return false;
    selectCliente(clienteMatches[highlightedClienteIndex]);
    return true;
  }

  function selectCliente(c){
    selectedClienteId = c ? String(c.id || "") : "";
    if (clienteRefReal) clienteRefReal.value = selectedClienteId;
    clienteSearch.value = (c ? c.value : "") || "";
    setClienteText((c ? c.value : "") || "");
    if (clienteDireccionVenta) clienteDireccionVenta.value = (c ? c.direccion : "") || "";
    if (clienteContactoVenta) clienteContactoVenta.value = (c ? c.contacto : "") || "";
    if (logoNotaReal) logoNotaReal.value = (c && c.logo ? c.logo : "CPC");
    syncClienteExtras();
    clientesResults && clientesResults.classList.add("d-none");
    clienteSearch.classList.remove("is-invalid");
  }

  function cartToArray(){
    return Array.from(cart.values()).sort((a, b) => {
      const nameCmp = (a.nombre || "").localeCompare(b.nombre || "", "es");
      if (nameCmp !== 0) return nameCmp;
      return (a.presentacion_nombre || "").localeCompare(b.presentacion_nombre || "", "es");
    });
  }

  function getSubtotal(){
    let t = 0;
    cart.forEach(i => { t += decimal(i.qty_kg) * decimal(i.precio); });
    return t;
  }

  function getComisionTerminalPorcentaje(){
    return decimal(String(form.dataset.comisionTerminalPorcentaje || "0").replace(",", "."));
  }

  function isTerminalPayment(){
    return !!(formaPagoReal && String(formaPagoReal.value || "").toUpperCase() === "TERMINAL");
  }

  function getCommissionAmount(){
    const subtotal = getSubtotal();
    const pct = getComisionTerminalPorcentaje();
    if (!isTerminalPayment() || subtotal <= 0 || pct <= 0) return 0;
    return Math.round((subtotal * pct / 100) * 100) / 100;
  }

  function getTotal(){
    return getSubtotal() + getCommissionAmount();
  }

  function syncTerminalPagoState(){
    if (!formaPagoReal || !estadoPagoReal) return;
    if (isTerminalPayment()){
      estadoPagoReal.value = "PAG";
      estadoPagoReal.classList.add("bg-body-secondary");
    } else {
      estadoPagoReal.classList.remove("bg-body-secondary");
    }
    refreshCartSummary();
  }

  function getItemAllocationsQtyKg(item){
    return (item.allocations || []).reduce((acc, a) => acc + decimal(a.qty_kg), 0);
  }

  function getAllocationDisponibleKg(producto, almacenId){
    const almacen = (producto.almacenes || []).find(a => String(a.id) === String(almacenId));
    if (!almacen) return 0;
    if (esAlmacenVentaSinStock(almacen)) return Number.MAX_SAFE_INTEGER;

    let used = 0;
    cart.forEach(item => {
      if (String(item.producto_id) !== String(producto.id)) return;
      used += (item.allocations || [])
        .filter(a => String(a.almacen_id) === String(almacenId))
        .reduce((acc, a) => acc + decimal(a.qty_kg), 0);
    });

    return Math.max(0, decimal(almacen.stock) - used);
  }

  function setIndicator(){
    indicators.forEach(ind => {
      const n = Number(ind.dataset.stepIndicator);
      ind.classList.toggle("active", n === step);
      ind.classList.toggle("done", n < step);
    });
    badge.textContent = `Paso ${step} de ${totalSteps}`;
  }

  function showStep(n){
    step = Math.min(Math.max(1, n), totalSteps);
    panels.forEach(p => p.classList.add("d-none"));
    const currentPanel = document.querySelector(`.wizard-panel[data-step="${step}"]`);
    if (currentPanel){ currentPanel.classList.remove("d-none"); }
    btnPrev.disabled = (step === 1);
    btnNext.classList.toggle("d-none", step === totalSteps);
    if (btnSubmit){ btnSubmit.classList.toggle("d-none", step !== totalSteps); }
    setIndicator();
    if (step === 2) setTimeout(() => productoSearch && productoSearch.focus(), 50);
    if (step === 3) renderPreview();
    if (step === 4) syncFormsetFromCart();
  }

  function getClienteNombre(text){
    const value = String(text || "").trim();
    if (!value) return "";
    return value.replace(/\s*\([^)]*\)\s*$/, "").trim();
  }

  function setClienteText(text){
    if (clienteInputReal) clienteInputReal.value = text || "";
    clienteSelectedText.textContent = getClienteNombre(text) || "Sin cliente seleccionado";
  }

  function renderPresentacionesProducto(producto){
    productoPresentacionSelect.innerHTML = '<option value="">Selecciona una presentación…</option>';
    const presentaciones = getPresentaciones(producto);
    presentaciones.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = p.equivalencia_texto || `${formatPlainNumber(p.cantidad_origen)} ${p.unidad_origen} = ${formatPlainNumber(p.factor_conversion, 2)} ${producto.metrica_default || 'kg'}`;
      productoPresentacionSelect.appendChild(opt);
    });
    productoPresentacionSelect.disabled = !producto || !presentaciones.length;
  }

  function renderAlmacenesProducto(producto){
    productoAlmacenSelect.innerHTML = '<option value="">Selecciona un almacén…</option>';
    ((producto && producto.almacenes) ? producto.almacenes : []).forEach(a => {
      const disponibleKg = getAllocationDisponibleKg(producto, a.id);
      const ventaSinStock = esAlmacenVentaSinStock(a);
      const opt = document.createElement("option");
      opt.value = a.id;
      opt.textContent = ventaSinStock
        ? `${getAlmacenLabel(a)} · Venta sin inventario`
        : `${getAlmacenLabel(a)} · Disponible: ${formatPlainNumber(disponibleKg, 2)} kg`;
      opt.disabled = !ventaSinStock && disponibleKg <= 0;
      productoAlmacenSelect.appendChild(opt);
    });
    productoAlmacenSelect.disabled = !producto;
  }

  function clearProductoSeleccionado(){
    selectedProducto = null;
    selectedProductoNombre.textContent = "Ninguno";
    selectedProductoStock.textContent = "—";
    selectedProductoPrecio.textContent = moneyUnit(0);
    if (productoPrecio){ productoPrecio.value = "0"; productoPrecio.disabled = true; }
    if (productoPrecioClienteWarn){ productoPrecioClienteWarn.classList.add("d-none"); productoPrecioClienteWarn.textContent = ""; }
    selectedPresentacionInfo.textContent = "—";
    productoPresentacionSelect.innerHTML = '<option value="">Selecciona una presentación…</option>';
    productoPresentacionSelect.disabled = true;
    productoPresentacionText.textContent = "";
    productoAlmacenSelect.innerHTML = '<option value="">Selecciona un almacén…</option>';
    productoAlmacenSelect.disabled = true;
    productoAlmacenStockText.textContent = "";
    productoQtyHelp.textContent = "";
    productoQty.value = "1";
    productoQty.disabled = true;
    productoQty.classList.remove("is-invalid");
    if (productoCajas){ productoCajas.value = ""; productoCajas.disabled = true; productoCajas.classList.remove("is-invalid"); }
    syncPesoVariableUI();
    btnAddProducto.disabled = true;
    document.querySelectorAll(".product-item.active").forEach(el => el.classList.remove("active"));
  }

  function getPrecioParaCliente(producto){
    const precios = producto && producto.precios_clientes ? producto.precios_clientes : {};
    if (selectedClienteId && precios[String(selectedClienteId)]){
      return { tipo: "cliente", ...precios[String(selectedClienteId)] };
    }
    return { tipo: "sugerido", precio: decimal(producto ? producto.precio : 0), vigente: true, dias_sin_compra: null };
  }

  function getPrecioMinimoProducto(producto){
    return decimal(producto ? producto.precio_minimo : 0);
  }

  function isPrecioMenorAlMinimo(producto, precioKg){
    const minimo = getPrecioMinimoProducto(producto);
    return minimo > 0 && decimal(precioKg) > 0 && decimal(precioKg) < minimo;
  }

  function getPrecioMinimoKey(producto, precioKg){
    return `${producto ? producto.id : ''}::${decimal(precioKg).toFixed(2)}`;
  }

  function marcarEnvioAutorizacionConfirmado(){
    if (confirmarEnvioAutorizacionPrecio){
      confirmarEnvioAutorizacionPrecio.value = preciosMinimosConfirmados.size > 0 ? "1" : "0";
    }
  }

  function solicitarConfirmacionPrecioMinimo(producto, precioKg){
    pendingPrecioMinimoAdd = {
      productoId: String(producto.id),
      precioKg: decimal(precioKg),
      key: getPrecioMinimoKey(producto, precioKg),
    };

    if (precioMinimoModalProducto) precioMinimoModalProducto.textContent = producto.nombre || "—";
    if (precioMinimoModalCapturado) precioMinimoModalCapturado.textContent = moneyAmount(precioKg);
    if (precioMinimoModalMinimo) precioMinimoModalMinimo.textContent = moneyAmount(getPrecioMinimoProducto(producto));

    if (precioMinimoModal){
      precioMinimoModal.show();
    } else if (confirm("El precio es menor al mínimo. ¿Deseas confirmar el envío de solicitud de autorización al guardar?")){
      preciosMinimosConfirmados.add(pendingPrecioMinimoAdd.key);
      marcarEnvioAutorizacionConfirmado();
      pendingPrecioMinimoAdd = null;
      addSelectedProductoToCart();
    }
  }

  function setProductoSeleccionado(producto){
    selectedProducto = producto;
    selectedProductoNombre.textContent = producto.nombre;
    selectedProductoStock.textContent = formatPlainNumber(producto.stock, 2);
    const precioInfo = getPrecioParaCliente(producto);
    const precioBase = decimal(precioInfo.precio || 0);
    selectedProductoPrecio.textContent = moneyUnit(precioBase);
    if (productoPrecio){ productoPrecio.value = precioBase.toFixed(2); productoPrecio.disabled = false; productoPrecio.classList.remove("is-invalid"); }
    if (productoPrecioClienteWarn){
      productoPrecioClienteWarn.classList.add("d-none");
      productoPrecioClienteWarn.textContent = "";
      if (precioInfo.tipo === "cliente"){
        productoPrecioClienteWarn.classList.remove("d-none");
        productoPrecioClienteWarn.textContent = precioInfo.vigente ? "Usando último precio otorgado a este cliente." : `Último precio del cliente vencido o con inactividad (${precioInfo.dias_sin_compra || 0} días). Validar antes de guardar.`;
      }
    }
    selectedPresentacionInfo.textContent = "—";
    productoQty.value = "1";
    productoQty.classList.remove("is-invalid");
    if (productoCajas){ productoCajas.value = ""; productoCajas.classList.remove("is-invalid"); }
    syncPesoVariableUI();
    renderPresentacionesProducto(producto);
    selectMetricaBaseProducto(producto);
    renderAlmacenesProducto(producto);
    limpiarAlmacenSeleccionado();
    productoQty.disabled = true;
    btnAddProducto.disabled = true;
    productoPresentacionText.textContent = "";
    if (productoAlmacenStockText){
      const alm = (producto.almacenes || []).find(a => String(a.id) === String(productoAlmacenSelect.value));
      productoAlmacenStockText.textContent = productoAlmacenSelect.value
        ? (esAlmacenVentaSinStock(alm) ? "Venta sin inventario: generará entrada/salida automática" : `Disponible: ${formatPlainNumber(getAllocationDisponibleKg(producto, productoAlmacenSelect.value), 2)} kg`)
        : "Disponible: —";
    }
    validarCantidadSeleccionada();

    document.querySelectorAll(".product-item").forEach(el => {
      el.classList.toggle("active", el.dataset.id === String(producto.id));
    });
  }

  function validarCantidadSeleccionada(){
    if (!selectedProducto){
      productoQty.classList.remove("is-invalid");
      return false;
    }

    const presentacion = getSelectedPresentacion();
    const almacenId = productoAlmacenSelect.value;
    if (!presentacion){
      productoQty.classList.remove("is-invalid");
      btnAddProducto.disabled = true;
      return false;
    }
    if (!almacenId){
      productoQty.classList.remove("is-invalid");
      btnAddProducto.disabled = true;
      return false;
    }

    const almacen = (selectedProducto.almacenes || []).find(a => String(a.id) === String(almacenId));
    const ventaSinStock = esAlmacenVentaSinStock(almacen);
    const disponibleKg = getAllocationDisponibleKg(selectedProducto, almacenId);
    if (productoAlmacenStockText){
      productoAlmacenStockText.textContent = almacenId
        ? (ventaSinStock ? "Venta sin inventario: generará entrada/salida automática" : `Disponible: ${formatPlainNumber(disponibleKg, 2)} kg`)
        : "Disponible: —";
    }
    const variable = esProductoPesoVariable(selectedProducto);
    const qCapturada = decimal(productoQty.value || 0);
    const cajasCapturadas = getCajasCapturadas();
    const factor = decimal(presentacion.factor_conversion || 0);
    const requeridoKg = variable ? qCapturada : (qCapturada * factor);
    const precioKg = decimal((productoPrecio ? productoPrecio.value : '') || 0);
    const precioMenorMinimo = isPrecioMenorAlMinimo(selectedProducto, precioKg);
    const cajasOk = !variable || cajasCapturadas >= 0;
    const qtyOk = qCapturada > 0 && (variable || factor > 0) && (ventaSinStock || requeridoKg <= disponibleKg) && cajasOk;
    const precioOk = precioKg > 0;
    const ok = qtyOk && precioOk;

    productoQty.classList.toggle("is-invalid", !qtyOk);
    productoPrecio && productoPrecio.classList.toggle("is-invalid", !precioOk && !productoPrecio.disabled);
    if (productoPrecioError){
      productoPrecioError.textContent = precioOk ? "" : "El precio debe ser mayor a 0.";
    }
    btnAddProducto.disabled = !ok;
    productoQty.disabled = false;
    productoQtyHelp.textContent = variable
      ? `Se descontarán ${formatPlainNumber(requeridoKg, 2)} kg reales. ${cajasCapturadas > 0 ? 'Cajas informativas: ' + formatPlainNumber(cajasCapturadas, 2) + '. ' : ''}${ventaSinStock ? 'Entrada/salida automática en almacén virtual. ' : ''}Subtotal: ${moneyAmount(requeridoKg * precioKg)}.`
      : `Equivale a ${formatPlainNumber(requeridoKg, 2)} kg. ${ventaSinStock ? 'Entrada/salida automática en almacén virtual. ' : ''}Subtotal: ${moneyAmount(requeridoKg * precioKg)}.`;

    if (productoPrecioClienteWarn){
      if (precioMenorMinimo){
        productoPrecioClienteWarn.classList.remove("d-none");
        productoPrecioClienteWarn.textContent = `Precio menor al mínimo configurado (${moneyAmount(getPrecioMinimoProducto(selectedProducto))}). Requiere autorización.`;
      } else if (!selectedClienteId || !(selectedProducto.precios_clientes || {})[String(selectedClienteId)]){
        productoPrecioClienteWarn.classList.add("d-none");
        productoPrecioClienteWarn.textContent = "";
      }
    }

    return ok;
  }

  function buildBusquedaTexto(p){
    return norm([p.nombre || "", p.clave_busqueda || "", p.codigo || ""].join(" "));
  }

  function moveHighlight(delta){
    if (!filteredProductos.length) return;
    highlightedIndex += delta;
    if (highlightedIndex < 0) highlightedIndex = filteredProductos.length - 1;
    if (highlightedIndex >= filteredProductos.length) highlightedIndex = 0;
    document.querySelectorAll(".product-item").forEach((el, idx) => el.classList.toggle("pos-focus", idx === highlightedIndex));
    const highlightedEl = document.querySelectorAll(".product-item")[highlightedIndex];
    if (highlightedEl){ highlightedEl.scrollIntoView({ block: "nearest" }); }
  }

  function selectHighlightedProducto(){
    if (highlightedIndex < 0 || !filteredProductos[highlightedIndex]) return false;
    setProductoSeleccionado(filteredProductos[highlightedIndex]);
    return true;
  }

  function getProductoIdsEnCarrito(){
    return new Set(cartToArray().map(item => String(item.producto_id)));
  }

  function renderProductos(){
    const q = norm(productoSearch.value || "");
    const productosEnCarrito = getProductoIdsEnCarrito();
    productosResults.innerHTML = "";

    filteredProductos = productosData.filter(p => {
      if (productosEnCarrito.has(String(p.id))) return false;
      return !q || buildBusquedaTexto(p).includes(q);
    });
    highlightedIndex = filteredProductos.length ? 0 : -1;
    productosEmptyState.classList.toggle("d-none", filteredProductos.length > 0);
    if (!filteredProductos.length) return;

    filteredProductos.forEach((p, idx) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "list-group-item list-group-item-action product-item";
      item.dataset.id = p.id;
      if (idx === highlightedIndex) item.classList.add("pos-focus");
      if (selectedProducto && String(selectedProducto.id) === String(p.id)) item.classList.add("active");

      const almacenesConStock = (p.almacenes || []).filter(a => esAlmacenVentaSinStock(a) || decimal(getAllocationDisponibleKg(p, a.id)) > 0).length;
      item.innerHTML = `
        <div class="d-flex justify-content-between align-items-start gap-3">
          <div class="text-start">
            <div class="fw-semibold">${escapeHtml(p.nombre)}</div>
            <div class="small text-muted">
              Stock total: <span class="product-stock-${decimal(p.stock) > 0 ? "ok" : "low"}">${escapeHtml(formatPlainNumber(p.stock, 2))} kg</span>
              · Almacenes disponibles: <span class="fw-semibold">${almacenesConStock}</span>
            </div>
          </div>
          <div class="text-end small text-muted">
            ${moneyUnit(p.precio || 0)}
          </div>
        </div>
      `;
      item.addEventListener("click", () => {
        highlightedIndex = idx;
        setProductoSeleccionado(p);
      });
      productosResults.appendChild(item);
    });
  }

  function addSelectedProductoToCart(){
    if (!selectedProducto){ alert("Selecciona un producto de la lista."); productoSearch.focus(); return; }
    const presentacion = getSelectedPresentacion();
    if (!presentacion){ alert("Selecciona la presentación que se venderá."); productoPresentacionSelect.focus(); return; }

    const almacenId = productoAlmacenSelect.value;
    if (!almacenId){
      alert("Selecciona el almacén desde el que se descontará el inventario.");
      productoAlmacenSelect.focus();
      return;
    }

    if (!validarCantidadSeleccionada()){ productoQty.focus(); return; }
    const almacen = (selectedProducto.almacenes || []).find(a => String(a.id) === String(almacenId));
    const variable = esProductoPesoVariable(selectedProducto);
    const qCapturada = decimal(productoQty.value || 0);
    const cajasCapturadas = variable ? getCajasCapturadas() : qCapturada;
    const factor = variable
      ? (cajasCapturadas > 0 ? qCapturada / cajasCapturadas : 1)
      : decimal(presentacion.factor_conversion || 0);
    const qtyKg = variable ? qCapturada : (qCapturada * factor);
    const qPresentacion = variable ? cajasCapturadas : qCapturada;
    const ventaSinStock = esAlmacenVentaSinStock(almacen);
    const disponibleKg = getAllocationDisponibleKg(selectedProducto, almacenId);
    const precioKg = decimal(productoPrecio ? productoPrecio.value : 0);
    if (!almacen || !(qCapturada > 0) || !(qtyKg > 0) || (!ventaSinStock && qtyKg > disponibleKg) || qPresentacion < 0){ productoQty.classList.add("is-invalid"); productoQty.focus(); return; }
    if (!(precioKg > 0)){ if (productoPrecio){ productoPrecio.classList.add("is-invalid"); productoPrecio.focus(); } return; }

    const precioMinimoKey = getPrecioMinimoKey(selectedProducto, precioKg);
    if (isPrecioMenorAlMinimo(selectedProducto, precioKg) && !preciosMinimosConfirmados.has(precioMinimoKey)){
      solicitarConfirmacionPrecioMinimo(selectedProducto, precioKg);
      return;
    }

    const key = getCartKey(selectedProducto.id, presentacion.id);
    let item = cart.get(key);
    if (!item){
      item = {
        id: key,
        producto_id: String(selectedProducto.id),
        nombre: selectedProducto.nombre,
        metrica_default: selectedProducto.metrica_default || "kg",
        precio: precioKg,
        qty_presentacion: 0,
        qty_kg: 0,
        factor_conversion: factor,
        es_peso_variable: variable,
        presentacion_id: String(presentacion.id),
        presentacion_nombre: presentacion.unidad_origen || selectedProducto.metrica_default || "kg",
        presentacion_label: variable
          ? (qPresentacion > 0 ? `${formatPlainNumber(qPresentacion, 2)} ${presentacion.unidad_origen || 'cajas'} = ${formatPlainNumber(qtyKg, 2)} ${selectedProducto.metrica_default || 'kg'}` : `${formatPlainNumber(qtyKg, 2)} ${selectedProducto.metrica_default || 'kg'} reales`)
          : (presentacion.equivalencia_texto || `${formatPlainNumber(presentacion.cantidad_origen)} ${presentacion.unidad_origen}`),
        equivalencia_texto: variable
          ? (qPresentacion > 0 ? `Peso variable: ${formatPlainNumber(qPresentacion, 2)} ${presentacion.unidad_origen || 'cajas'} = ${formatPlainNumber(qtyKg, 2)} ${selectedProducto.metrica_default || 'kg'}` : `Peso variable: ${formatPlainNumber(qtyKg, 2)} ${selectedProducto.metrica_default || 'kg'} reales`)
          : (presentacion.equivalencia_texto || `${formatPlainNumber(presentacion.cantidad_origen)} ${presentacion.unidad_origen} = ${formatPlainNumber(presentacion.factor_conversion, 2)} ${selectedProducto.metrica_default || 'kg'}`),
        allocations: [],
      };
      cart.set(key, item);
    }

    item.precio = precioKg;

    const existingAllocation = item.allocations.find(a => String(a.almacen_id) === String(almacenId));
    if (existingAllocation){
      existingAllocation.qty_presentacion = decimal(existingAllocation.qty_presentacion) + qPresentacion;
      existingAllocation.qty_kg = decimal(existingAllocation.qty_kg) + qtyKg;
    } else {
      item.allocations.push({
        almacen_id: String(almacen.id),
        almacen_nombre: esAlmacenVentaSinStock(almacen) ? `${getAlmacenLabel(almacen)} (virtual)` : getAlmacenLabel(almacen),
        qty_presentacion: qPresentacion,
        qty_kg: qtyKg,
      });
    }

    item.qty_presentacion = (item.allocations || []).reduce((acc, a) => acc + decimal(a.qty_presentacion), 0);
    item.qty_kg = getItemAllocationsQtyKg(item);

    // Al agregar el producto se limpia la selección para evitar que el campo de kilos
    // quede vacío marcado como inválido. Como el producto ya está en carrito,
    // renderProductos() lo oculta del listado de disponibles.
    clearProductoSeleccionado();
    renderProductos();
    updateCartUI();
  }

  function refreshCartSummary(){
    const items = cartToArray();
    const subtotal = getSubtotal();
    const commission = getCommissionAmount();
    const total = getTotal();
    cartCount.textContent = String(items.length);
    cartTotal.textContent = moneyAmount(total);
    if (cartSubtotal){ cartSubtotal.textContent = moneyAmount(subtotal); }
    if (cartCommissionAmount){ cartCommissionAmount.textContent = moneyAmount(commission); }
    if (cartCommissionPercent){ cartCommissionPercent.textContent = `(${getComisionTerminalPorcentaje().toLocaleString("es-MX", { maximumFractionDigits: 4 })}%)`; }
    if (cartGrandTotal){ cartGrandTotal.textContent = moneyAmount(total); }
    if (cartCommissionRow){ cartCommissionRow.classList.toggle("d-none", !(isTerminalPayment() && commission > 0)); }
    const summaryTotal = document.getElementById("summaryTotal");
    const summaryCount = document.getElementById("summaryCount");
    if (summaryTotal){ summaryTotal.textContent = moneyAmount(total); }
    if (summaryCount){ summaryCount.textContent = String(items.length); }
  }

  function renderAllocationsChips(item){
    return (item.allocations || []).map((a, idx) => `
      <span class="allocation-chip">
        ${escapeHtml(a.almacen_nombre)} · ${escapeHtml(formatPlainNumber(a.qty_kg, 2))} kg
      </span>
    `).join("");
  }

  function updateCartUI(){
    const items = cartToArray();
    refreshCartSummary();

    if (!items.length){
      cartEmpty.classList.remove("d-none");
      cartList.classList.add("d-none");
      cartList.innerHTML = "";
      renderProductos();
      return;
    }

    cartEmpty.classList.add("d-none");
    cartList.classList.remove("d-none");
    cartList.innerHTML = "";

    for (const item of items){
      const el = document.createElement("div");
      el.className = "cart-item";
      el.dataset.id = item.id;
      el.innerHTML = `
        <div class="d-flex justify-content-between align-items-start gap-2">
          <div class="flex-grow-1">
            <div class="cart-name">${escapeHtml(item.nombre)}</div>
            <div class="cart-meta">
              ${escapeHtml(formatPlainNumber(item.qty_kg, 2))} kg
              ${decimal(item.qty_presentacion) > 0 && decimal(item.qty_presentacion) !== decimal(item.qty_kg) ? ' · Cajas: <span class="fw-semibold">' + escapeHtml(formatPlainNumber(item.qty_presentacion, 2)) + '</span>' : ''}
              · ${moneyUnit(item.precio)}
            </div>
            <div class="d-flex flex-wrap gap-2 mt-2 allocations-wrap">${renderAllocationsChips(item)}</div>
          </div>
          <button type="button" class="btn btn-outline-danger btn-sm" data-action="remove" title="Quitar producto">
            <i class="bi bi-trash"></i>
          </button>
        </div>
        <div class="d-flex justify-content-between align-items-center mt-2 pt-2 border-top">
          <span class="small text-muted">Subtotal</span>
          <span class="fw-bold item-subtotal">${moneyAmount(decimal(item.qty_kg) * decimal(item.precio))}</span>
        </div>
      `;
      cartList.appendChild(el);
    }
    renderProductos();
  }

  function syncFormsetFromCart(){
    hiddenTbody.innerHTML = "";
    allocationsPayload.innerHTML = "";
    const items = cartToArray();
    const n = items.length;
    if (initialForms) initialForms.value = "0";
    if (totalForms) totalForms.value = String(n);

    let allocIndex = 0;
    items.forEach((it, idx) => {
      const node = hiddenTpl.content.cloneNode(true);
      const row = node.querySelector("tr");
      row.querySelectorAll("input, select, textarea").forEach(el => {
        const name = el.getAttribute("name");
        const id = el.getAttribute("id");
        if (name) el.setAttribute("name", name.replaceAll("__prefix__", idx));
        if (id) el.setAttribute("id", id.replaceAll("__prefix__", idx));
      });
      row.querySelector('select[name$="-producto"]').value = it.producto_id;
      row.querySelector('input[name$="-cantidad"]').value = String(it.qty_kg);
      row.querySelector('input[name$="-precio_unitario"]').value = String(it.precio);
      hiddenTbody.appendChild(row);

      [
        ["detalle_producto_id", it.producto_id],
        ["detalle_presentacion_id", it.presentacion_id || "default"],
        ["detalle_cantidad_presentacion", it.qty_presentacion],
        ["detalle_factor_conversion", it.factor_conversion || 1],
        ["detalle_presentacion_nombre", it.presentacion_nombre || "Kilos"],
        ["detalle_metrica_default", it.metrica_default || "kg"],
        ["detalle_equivalencia_texto", it.equivalencia_texto || it.presentacion_label || ""],
      ].forEach(([name, value]) => {
        const input = document.createElement("input");
        input.type = "hidden";
        input.name = name;
        input.value = String(value ?? "");
        allocationsPayload.appendChild(input);
      });

      (it.allocations || []).forEach(a => {
        [["linea_item_index", idx], ["linea_producto_id", it.producto_id], ["linea_almacen_id", a.almacen_id], ["linea_cantidad", a.qty_kg]].forEach(([name, value]) => {
          const input = document.createElement("input");
          input.type = "hidden";
          input.name = name;
          input.value = String(value);
          input.dataset.allocIndex = String(allocIndex);
          allocationsPayload.appendChild(input);
        });
        allocIndex += 1;
      });
    });

    refreshCartSummary();
  }

  function formatDate(value){
    if (!value) return "";
    const text = String(value).trim();
    const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (iso) return `${iso[1]}-${iso[2]}-${iso[3]}`;
    const dmy = text.match(/^(\d{1,2})[\/-](\d{1,2})[\/-](\d{4})$/);
    if (dmy) return `${dmy[3]}-${dmy[2].padStart(2, "0")}-${dmy[1].padStart(2, "0")}`;
    return text;
  }

  function formatQty(value){
    const n = decimal(value);
    return Number.isInteger(n) ? String(n) : n.toLocaleString("es-MX", { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  }

  function getTotalKg(){
    let kg = 0;
    cart.forEach(i => { kg += decimal(i.qty_kg); });
    return kg;
  }

  function buildSaleNoteCopy(label){
    const folio = (form.querySelector('input[name="folio"]') ? form.querySelector('input[name="folio"]').value : "") || "";
    const fecha = (form.querySelector('input[name="fecha"]') ? form.querySelector('input[name="fecha"]').value : "") || "";
    const cliente = getClienteNombre((clienteInputReal ? clienteInputReal.value : "") || "");
    const items = cartToArray();
    const observaciones = (form.querySelector('textarea[name="observaciones"]') ? form.querySelector('textarea[name="observaciones"]').value : "") || "";
    const subtotal = getSubtotal();
    const commission = getCommissionAmount();
    const total = getTotal();

    const rows = items.length
      ? items.map(it => {
          const sub = decimal(it.qty_kg) * decimal(it.precio);
          return `
            <tr>
              <td class="qty">${escapeHtml(formatQty(it.qty_kg))}</td>
              <td class="qty">${decimal(it.qty_presentacion) > 0 && decimal(it.qty_presentacion) !== decimal(it.qty_kg) ? escapeHtml(formatQty(it.qty_presentacion)) : ''}</td>
              <td class="desc">${escapeHtml(it.nombre)}</td>
              <td class="price">${moneyUnit(it.precio)}</td>
              <td class="amount">${moneyAmount(sub)}</td>
            </tr>
          `;
        }).join("")
      : `
          <tr>
            <td colspan="5" class="text-center text-muted">Sin productos capturados</td>
          </tr>
        `;

    return `
      <article class="sale-note-copy ${label === 'COPIA' ? 'is-copy' : ''}">
        <div class="sale-note-copy-tag">${label}</div>

        <div class="sale-note-top mt-1">
          <div class="sale-note-header">
            <div class="sale-note-header-row">
              <img src="${escapeHtml(getSelectedLogoUrl())}" alt="Logo" class="sale-note-logo">
              <div class="sale-note-brand">
                <div class="brand-name">CPC Alimentos</div>
                <div class="brand-owner">Jaime Parada Villarreal</div>
                <div class="sale-note-address">Cerrada Coba 3612 Cp. 21376
Mayakhan Residencial Mexicali B.C
Teléfono: 686 162 7239
Email: cpcalimentosbc@gmail.com</div>
              </div>
            </div>
            <div class="sale-note-title">NOTA DE VENTA</div>
          </div>
        </div>

        <div class="sale-note-message">Atendiendo a su amable solicitud enviamos la nota de venta correspondiente quedando a sus órdenes.</div>

        <div class="sale-note-fields">
          <div class="sale-note-field">
            <div class="label">Cliente</div>
            <div class="value">${escapeHtml(cliente)}</div>
          </div>
          <div class="sale-note-field">
            <div class="label">Folio</div>
            <div class="value text-center">${escapeHtml(folio)}</div>
          </div>
          <div class="sale-note-field">
            <div class="label">Fecha de entrega</div>
            <div class="value text-center">${escapeHtml(formatDate(fecha))}</div>
          </div>

          <div class="sale-note-field">
            <div class="label">Dirección</div>
            <div class="value">${escapeHtml((clienteDireccionReal ? clienteDireccionReal.value : "") || (clienteDireccionVenta ? clienteDireccionVenta.value : '') || "") || "&nbsp;"}</div>
          </div>
          <div class="sale-note-field">
            <div class="label">Contacto</div>
            <div class="value">${escapeHtml((clienteContactoReal ? clienteContactoReal.value : "") || (clienteContactoVenta ? clienteContactoVenta.value : '') || "") || "&nbsp;"}</div>
          </div>
          <div class="sale-note-field">
            <div class="label">Forma de pago</div>
            <div class="value text-center">${escapeHtml((form.querySelector('select[name="forma_pago_venta"]') ? form.querySelector('select[name="forma_pago_venta"]').selectedOptions[0].text : 'Contado'))}</div>
          </div>          
        </div>

        <table class="sale-note-table">
          <thead>
            <tr>
              <th style="width: 12%;">Cantidad KG</th>
              <th style="width: 12%;">Cant. Cajas</th>
              <th>Descripción</th>
              <th style="width: 16%;">P. KG</th>
              <th style="width: 16%;">Importe</th>
            </tr>
          </thead>
          <tbody>
            ${rows}
          </tbody>
        </table>

        <div class="sale-note-totals">
          <div class="sale-note-totals-row"><span>Subtotal</span><strong>${moneyAmount(subtotal)}</strong></div>
          ${commission > 0 ? `<div class="sale-note-totals-row sale-note-commission-row"><span></span><strong>${moneyAmount(commission)}</strong></div>` : ``}
          <div class="sale-note-totals-row sale-note-grand-total"><span>Total</span><strong>${moneyAmount(total)}</strong></div>
        </div>

        <div class="mt-4">
          <h6 class="fw-bold text-center mb-2">PAGARÉ</h6>

          <p style="font-size: 12px; text-align: justify;">
            Por este pagaré me comprometo a pagar a la orden de: Jaime Parada Villarreal en la Ciudad de Mexicali, Baja California, México.
          </p>

          <p style="font-size: 12px; text-align: justify;">
            En caso de no cumplir con el pago en la fecha acordada, se generará un interés moratorio del 5% mensual.
          </p>

          <p style="font-size: 12px; text-align: justify;">
            Deudor: <strong id="clientePagareNombre">${escapeHtml(cliente || 'MOSTRADOR')}</strong>
          </p>
        </div>

        <div class="sale-note-footer">
          <div class="small text-muted">${escapeHtml(observaciones || '')}</div>
          <div class="sale-note-sign">Firma de recibido</div>
        </div>
      </article>
    `;
  }

  function renderPreview(){
    syncFormsetFromCart();
    ticketPreview.innerHTML = `
      <div class="sale-note-grid sale-note-grid-preview">
        ${buildSaleNoteCopy('ORIGINAL')}
      </div>
    `;
  }

  function validateStep(current){
    if (current === 1){
      syncTerminalPagoState();
      const fecha = form.querySelector('input[name="fecha"]');
      if (fecha && !fecha.value){ alert("Captura la fecha."); fecha.focus(); return false; }
      if (formaPagoReal && !formaPagoReal.value){ alert("Selecciona la forma de pago."); formaPagoReal.focus(); return false; }
      if (estadoPagoReal && !estadoPagoReal.value){ alert("Selecciona el estado de pago."); estadoPagoReal.focus(); return false; }
      if (logoNotaReal && !logoNotaReal.value){ alert("Selecciona el logo de la nota."); logoNotaReal.focus(); return false; }
      if (!selectedClienteId || (clienteRefReal && !clienteRefReal.value)){
        alert("Selecciona un cliente del catálogo antes de continuar.");
        clienteSearch.classList.add("is-invalid");
        clienteSearch.focus();
        return false;
      }
      return true;
    }
    if (current === 2){
      if (cart.size === 0){ alert("Agrega al menos un producto."); productoSearch.focus(); return false; }
      for (const it of cart.values()){
        const qtyKg = decimal(it.qty_kg);
        const qtyPresentacion = decimal(it.qty_presentacion);
        const cantidadValida = esItemPesoVariable(it)
          ? (qtyKg > 0 && qtyPresentacion >= 0)
          : (qtyKg > 0 && qtyPresentacion > 0);

        if (!cantidadValida){ alert(`El producto "${it.nombre}" tiene una cantidad inválida.`); return false; }
        if (!(it.allocations || []).length){ alert(`El producto "${it.nombre}" no tiene almacenes asignados.`); return false; }
      }
      return true;
    }
    return true;
  }

  function getCsrfToken(){
    return (document.querySelector('input[name="csrfmiddlewaretoken"]') ? document.querySelector('input[name="csrfmiddlewaretoken"]').value : "") || "";
  }

  indicators.forEach(ind => ind.addEventListener("click", () => {
    const target = Number(ind.dataset.stepIndicator);
    if (target <= step) showStep(target);
  }));

  function advanceFromCurrentStep(){
    if (!validateStep(step)) return;
    if (step === 2) syncFormsetFromCart();
    showStep(step + 1);
  }

  btnPrev.addEventListener("click", () => showStep(step - 1));
  btnNext.addEventListener("click", advanceFromCurrentStep);

  form.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;

    const target = e.target;
    const tag = (target && target.tagName ? target.tagName : "").toLowerCase();

    if (tag === "textarea") return;
    if (e.defaultPrevented) return;

    if (step < totalSteps){
      e.preventDefault();
      if (target === clienteSearch){
        selectHighlightedCliente();
        return;
      }
      if (step === 2 && target && (target.id === "productoQty" || target.id === "productoPrecio") && !btnAddProducto.disabled){
        addSelectedProductoToCart();
        return;
      }
      advanceFromCurrentStep();
    }
  });

  clienteSearch.addEventListener("input", () => {
    selectedClienteId = "";
    if (clienteRefReal) clienteRefReal.value = "";
    if (clienteInputReal) clienteInputReal.value = "";
    clienteSelectedText.textContent = "Sin cliente seleccionado";
    clienteSearch.classList.remove("is-invalid");
    renderClientesResults(clienteSearch.value);
    syncClienteExtras();
  });

  clienteSearch.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown"){ e.preventDefault(); moveClienteHighlight(1); }
    else if (e.key === "ArrowUp"){ e.preventDefault(); moveClienteHighlight(-1); }
    else if (e.key === "Enter"){
      e.preventDefault();
      if (!selectHighlightedCliente()){
        clienteSearch.classList.add("is-invalid");
      }
    }
  });
  clienteDireccionVenta && clienteDireccionVenta.addEventListener("input", syncClienteExtras);
  clienteContactoVenta && clienteContactoVenta.addEventListener("input", syncClienteExtras);
  logoNotaReal && logoNotaReal.addEventListener("change", () => { if (step === 3) renderPreview(); });
  btnClearCliente.addEventListener("click", () => {
    selectedClienteId = "";
    if (clienteRefReal) clienteRefReal.value = "";
    clienteSearch.value = "";
    clienteSearch.classList.remove("is-invalid");
    setClienteText("");
    if (clienteDireccionVenta) clienteDireccionVenta.value = "";
    if (clienteContactoVenta) clienteContactoVenta.value = "";
    if (logoNotaReal) logoNotaReal.value = "CPC";
    syncClienteExtras();
    clientesResults && clientesResults.classList.add("d-none");
    clienteSearch.focus();
  });

  productoSearch.addEventListener("input", renderProductos);
  productoSearch.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown"){ e.preventDefault(); moveHighlight(1); }
    else if (e.key === "ArrowUp"){ e.preventDefault(); moveHighlight(-1); }
    else if (e.key === "Enter"){ e.preventDefault(); selectHighlightedProducto(); }
  });

  productoPresentacionSelect.addEventListener("change", () => {
    const presentacion = getSelectedPresentacion();
    if (!presentacion){
      selectedPresentacionInfo.textContent = "—";
      productoQty.disabled = true;
      btnAddProducto.disabled = true;
      productoPresentacionText.textContent = "Selecciona la presentación que se venderá.";
      return;
    }
    const variable = esProductoPesoVariable(selectedProducto);
    selectedPresentacionInfo.textContent = variable ? `${presentacion.unidad_origen || 'Caja'} con peso variable` : (presentacion.equivalencia_texto || `${formatPlainNumber(presentacion.cantidad_origen)} ${presentacion.unidad_origen}`);
    productoPresentacionText.textContent = variable ? "Captura los kilos reales a descontar; las cajas son opcionales e informativas." : `Cada unidad descuenta ${formatPlainNumber(presentacion.factor_conversion, 2)} kg del inventario.`;
    if (productoAlmacenSelect.value){
      productoQty.disabled = false;
      validarCantidadSeleccionada();
    }
  });

  productoAlmacenSelect.addEventListener("change", () => {
    if (!selectedProducto){ return; }
    const aid = productoAlmacenSelect.value;
    if (!aid){
      productoQty.disabled = true;
      btnAddProducto.disabled = true;
      productoAlmacenStockText.textContent = "Selecciona el almacén desde el que se descontará el inventario.";
      return;
    }
    const disponibleKg = getAllocationDisponibleKg(selectedProducto, aid);
    productoQty.disabled = !getSelectedPresentacion();
    productoAlmacenStockText.textContent = `Disponible en el almacén seleccionado: ${formatPlainNumber(disponibleKg, 2)} kg.`;
    validarCantidadSeleccionada();
    if (disponibleKg > 0 && getSelectedPresentacion()){ productoQty.focus(); productoQty.select(); }
  });

  productoQty.addEventListener("keydown", blockInvalidNumberKeys);
  if (productoCajas){ productoCajas.addEventListener("keydown", blockInvalidNumberKeys); productoCajas.addEventListener("input", validarCantidadSeleccionada); }
  if (productoPrecio){ productoPrecio.addEventListener("keydown", blockInvalidNumberKeys); }
  productoQty.addEventListener("input", validarCantidadSeleccionada);
  productoQty.addEventListener("blur", () => {
    if (!(decimal(productoQty.value || 0) > 0)){
      productoQty.value = "1";
      validarCantidadSeleccionada();
    }
  });
  if (productoPrecio){
    productoPrecio.addEventListener("focus", () => {
      if (decimal(productoPrecio.value || 0) === 0){ productoPrecio.value = ""; }
    });
    productoPrecio.addEventListener("input", validarCantidadSeleccionada);
    productoPrecio.addEventListener("blur", () => {
      if (!(decimal(productoPrecio.value || 0) > 0)){
        productoPrecio.classList.add("is-invalid");
        btnAddProducto.disabled = true;
      } else {
        productoPrecio.classList.remove("is-invalid");
      }
    });
  }
  productoQty.addEventListener("keydown", (e) => { if (e.key === "Enter"){ e.preventDefault(); addSelectedProductoToCart(); } });
  btnAddProducto.addEventListener("click", addSelectedProductoToCart);

  if (precioMinimoModalEl){
    precioMinimoModalEl.addEventListener("hidden.bs.modal", () => {
      // Evita que una cancelación deje una confirmación pendiente para el siguiente intento.
      pendingPrecioMinimoAdd = null;
      document.body.classList.remove("modal-open");
      document.querySelectorAll(".modal-backdrop").forEach(backdrop => backdrop.remove());
    });
  }

  if (btnConfirmPrecioMinimo){
    btnConfirmPrecioMinimo.addEventListener("click", () => {
      if (pendingPrecioMinimoAdd){
        preciosMinimosConfirmados.add(pendingPrecioMinimoAdd.key);
        marcarEnvioAutorizacionConfirmado();
      }

      if (precioMinimoModal){
        precioMinimoModal.hide();
      }

      // Bootstrap termina de quitar el backdrop de forma asíncrona; esperar al siguiente
      // ciclo evita que la pantalla quede bloqueada mientras se agrega el producto.
      setTimeout(() => {
        addSelectedProductoToCart();
      }, 0);
    });
  }

  if (formaPagoReal){
    formaPagoReal.addEventListener("change", () => {
      syncTerminalPagoState();
      if (step === 3){ renderPreview(); }
    });
  }

  cartList.addEventListener("click", (e) => {
    const wrap = e.target.closest(".cart-item");
    if (!wrap) return;
    const id = String(wrap.dataset.id);
    const btn = e.target.closest("button[data-action]");
    if (!btn) return;
    if (btn.dataset.action === "remove"){
      cart.delete(id);
      updateCartUI();
    }
  });

  form.addEventListener("submit", (e) => {
    if (step !== totalSteps){
      e.preventDefault();
      advanceFromCurrentStep();
      return;
    }

    syncClienteExtras();
    syncFormsetFromCart();
    if (cart.size === 0){
      e.preventDefault();
      alert("Agrega al menos un producto.");
      showStep(2);
      return;
    }
  });

  const initialClienteId = urlParams.get("cliente_id") || (clienteRefReal ? clienteRefReal.value : "");
  if (initialClienteId){
    const clienteInicial = clientesData.find(c => String(c.id) === String(initialClienteId));
    if (clienteInicial){
      selectCliente(clienteInicial);
    }
  }

  syncTerminalPagoState();
  renderProductos();
  updateCartUI();
  showStep(initialStep);
})();
