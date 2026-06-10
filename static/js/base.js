(function () {
  "use strict";

  function normalizeText(value) {
    return (value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  function setSidebarOpen(isOpen) {
    const sidebar = document.getElementById("solarSidebar");
    const overlay = document.getElementById("sidebarOverlay");
    if (!sidebar) return;

    sidebar.classList.toggle("show", isOpen);
    overlay?.classList.toggle("show", isOpen);
    document.body.classList.toggle("sidebar-open", isOpen);
  }

  window.toggleSidebar = function toggleSidebar() {
    const sidebar = document.getElementById("solarSidebar");
    setSidebarOpen(!sidebar?.classList.contains("show"));
  };

  window.closeSidebar = function closeSidebar() {
    setSidebarOpen(false);
  };

  function setShown(element, shouldShow) {
    element?.classList.toggle("d-none", !shouldShow);
  }

  function getCollapseElements(rootNav) {
    const toggles = Array.from(rootNav.querySelectorAll('a.nav-link[data-bs-toggle="collapse"][href^="#"]'));
    return toggles
      .map((toggle) => {
        const target = document.querySelector(toggle.getAttribute("href"));
        return target ? { toggle, target } : null;
      })
      .filter(Boolean);
  }

  function setCollapseState(target, toggle, shouldShow) {
    if (!target) return;

    target.classList.remove("collapsing");
    target.style.height = "";
    target.style.width = "";

    if (window.bootstrap?.Collapse) {
      const instance = window.bootstrap.Collapse.getOrCreateInstance(target, { toggle: false });
      shouldShow ? instance.show() : instance.hide();
    } else {
      target.classList.toggle("show", shouldShow);
    }

    toggle?.setAttribute("aria-expanded", String(shouldShow));
  }

  function initMenuSearch() {
    const input = document.getElementById("menuSearch");
    const emptyState = document.getElementById("menuSearchEmpty");
    const rootNav = document.querySelector("#solarSidebar nav.nav");
    if (!input || !rootNav) return;

    const allLinks = Array.from(rootNav.querySelectorAll("a.nav-link"));
    const leafLinks = allLinks.filter((link) => !link.matches('[data-bs-toggle="collapse"]'));
    const sectionTitles = Array.from(rootNav.querySelectorAll(".nav-section-title"));
    const subtitles = Array.from(rootNav.querySelectorAll(".nav-subtitle"));
    const collapses = getCollapseElements(rootNav);

    collapses.forEach(({ target }) => {
      target.dataset.initialExpanded = target.classList.contains("show") ? "true" : "false";
    });

    function restoreMenu() {
      allLinks.forEach((link) => link.classList.remove("d-none"));
      sectionTitles.forEach((title) => title.classList.remove("d-none"));
      subtitles.forEach((subtitle) => subtitle.classList.remove("d-none"));
      collapses.forEach(({ toggle, target }) => {
        const shouldShow = target.dataset.initialExpanded === "true";
        setCollapseState(target, toggle, shouldShow);
        target.classList.remove("menu-search-open");
        toggle.classList.remove("d-none");
      });
      setShown(emptyState, false);
    }

    function sectionHasVisibleLinks(sectionTitle) {
      let node = sectionTitle.nextElementSibling;
      while (node && !node.classList.contains("nav-section-title")) {
        if (node.matches?.("a.nav-link:not(.d-none)")) return true;
        if (node.querySelector?.("a.nav-link:not(.d-none)")) return true;
        node = node.nextElementSibling;
      }
      return false;
    }

    function subtitleHasVisibleLinks(subtitle) {
      let node = subtitle.nextElementSibling;
      while (node && !node.classList.contains("nav-subtitle")) {
        if (node.matches?.("a.nav-link:not(.d-none)")) return true;
        node = node.nextElementSibling;
      }
      return false;
    }

    function filterMenu() {
      const query = normalizeText(input.value);

      if (!query) {
        restoreMenu();
        return;
      }

      leafLinks.forEach((link) => {
        const text = normalizeText(link.textContent);
        setShown(link, text.includes(query));
      });

      collapses.forEach(({ toggle, target }) => {
        const toggleMatches = normalizeText(toggle.textContent).includes(query);

        if (toggleMatches) {
          target.querySelectorAll("a.nav-link").forEach((link) => link.classList.remove("d-none"));
        }

        const hasVisibleChildren = target.querySelectorAll("a.nav-link:not(.d-none)").length > 0;
        const shouldShow = toggleMatches || hasVisibleChildren;

        setShown(toggle, shouldShow);
        setCollapseState(target, toggle, shouldShow);
        target.classList.toggle("menu-search-open", shouldShow);
      });

      subtitles.forEach((subtitle) => setShown(subtitle, subtitleHasVisibleLinks(subtitle)));
      sectionTitles.forEach((title) => setShown(title, sectionHasVisibleLinks(title)));

      const visibleLeafLinks = leafLinks.filter((link) => !link.classList.contains("d-none")).length;
      setShown(emptyState, visibleLeafLinks === 0);
    }

    input.addEventListener("input", filterMenu);
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        input.value = "";
        restoreMenu();
      }
    });
  }

  function initActiveMenu() {
    const rootNav = document.querySelector("#solarSidebar nav.nav");
    if (!rootNav) return;

    const currentPath = window.location.pathname.replace(/\/+$/, "");
    const allLinks = Array.from(rootNav.querySelectorAll("a.nav-link[href]"));
    let activeLink = null;

    allLinks.forEach((link) => {
      const href = link.getAttribute("href");
      if (!href || href.startsWith("#") || href.startsWith("javascript:")) return;

      const linkPath = new URL(href, window.location.origin).pathname.replace(/\/+$/, "");
      if (linkPath === currentPath) activeLink = link;
    });

    if (!activeLink) return;

    activeLink.classList.add("active", "is-active");

    const parentCollapse = activeLink.closest(".collapse");
    if (!parentCollapse?.id) return;

    const parentToggle = rootNav.querySelector(`a[href="#${parentCollapse.id}"]`);
    setCollapseState(parentCollapse, parentToggle, true);
    parentToggle?.classList.add("active", "is-active");
  }

  function initThemeSwitcher() {
    const root = document.documentElement;
    const body = document.body;
    const switcher = document.getElementById("themeSwitcher");
    const allowedThemes = new Set(["light", "dark"]);
    const savedTheme = localStorage.getItem("sg-theme");
    const initialTheme = allowedThemes.has(savedTheme) ? savedTheme : "light";

    function applyTheme(theme) {
      const nextTheme = allowedThemes.has(theme) ? theme : "light";

      root.setAttribute("data-theme", nextTheme);
      body?.setAttribute("data-theme", nextTheme);
      root.style.colorScheme = nextTheme === "dark" ? "dark" : "light";
      localStorage.setItem("sg-theme", nextTheme);

      if (switcher) {
        switcher.setAttribute("aria-checked", String(nextTheme === "dark"));
        switcher.dataset.theme = nextTheme;
      }
    }

    applyTheme(initialTheme);

    switcher?.addEventListener("click", () => {
      const currentTheme = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
      applyTheme(currentTheme === "dark" ? "light" : "dark");
    });

    switcher?.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        switcher.click();
      }
    });
  }



  function initResponsiveTables() {
    const MOBILE_LIST_CLASS = "sg-auto-mobile-list";
    const TABLE_WRAPPER_CLASS = "sg-has-mobile-grid";

    function normalizeLabel(text) {
      return (text || "")
        .replace(/\s+/g, " ")
        .replace(/[\n\r\t]+/g, " ")
        .trim();
    }

    function isActionsLabel(label) {
      return /^(accion|acciones|opcion|opciones)$/i.test(normalizeLabel(label));
    }

    function isEmptyRow(row) {
      const cells = Array.from(row.children).filter((cell) => cell.matches("td,th"));
      if (cells.length !== 1) return false;
      const colspan = Number(cells[0].getAttribute("colspan") || "1");
      return colspan > 1 || cells[0].classList.contains("sg-empty-state");
    }

    function tableCanBeConverted(table) {
      if (!table.matches(".sg-table")) return false;
      if (table.matches(".sg-no-mobile-grid, .dataTable")) return false;
      if (table.closest(".sg-no-mobile-grid, .modal, .dropdown-menu")) return false;
      if (!table.tHead || !table.tBodies.length) return false;
      if (table.querySelector("input, select, textarea, button[data-bs-toggle='modal']")) return false;
      return true;
    }

    function getLabels(table) {
      const headerRow = table.tHead?.querySelector("tr:last-child");
      if (!headerRow) return [];
      return Array.from(headerRow.children).map((cell) => normalizeLabel(cell.textContent));
    }

    function cloneCellContent(cell) {
      const clone = document.createElement("span");
      clone.innerHTML = cell.innerHTML;
      clone.querySelectorAll("script, style").forEach((node) => node.remove());
      clone.querySelectorAll("[id]").forEach((node) => node.removeAttribute("id"));
      clone.querySelectorAll(".text-end").forEach((node) => node.classList.remove("text-end"));
      return clone;
    }

    function getActionFallbackLabel(action) {
      const explicitLabel = normalizeLabel(action.getAttribute("aria-label") || action.dataset.mobileLabel || "");
      if (explicitLabel) return explicitLabel;

      const icon = action.querySelector("i");
      const iconClass = icon?.className || "";
      const href = action.getAttribute("href") || "";
      const className = action.className || "";
      const semanticSource = `${iconClass} ${href} ${className}`.toLowerCase();

      const map = [
        { pattern: /(bi-pencil|edit|editar)/, label: "Editar" },
        { pattern: /(bi-trash|delete|eliminar|borrar)/, label: "Eliminar" },
        { pattern: /(bi-eye|detail|detalle|ver)/, label: "Ver" },
        { pattern: /(bi-printer|print|imprimir)/, label: "Imprimir" },
        { pattern: /(bi-file-earmark-pdf|pdf)/, label: "PDF" },
        { pattern: /(bi-cash|bi-credit-card|pago|pagar)/, label: "Pagar" },
        { pattern: /(bi-check|aceptar|aprobar|confirmar)/, label: "Aceptar" },
        { pattern: /(bi-x|cancel|cancelar|rechazar)/, label: "Cancelar" },
        { pattern: /(bi-plus|add|agregar|nuevo)/, label: "Agregar" },
        { pattern: /(bi-arrow-repeat|refresh|actualizar)/, label: "Actualizar" },
        { pattern: /(bi-box-arrow-up-right|abrir)/, label: "Abrir" },
      ];

      const match = map.find((item) => item.pattern.test(semanticSource));
      if (match) return match.label;

      const title = normalizeLabel(action.getAttribute("title") || "");
      if (title && title.length <= 24 && !/^solo\s+puedes/i.test(title)) return title;

      return "Ver";
    }

    function buildCard(row, labels) {
      const cells = Array.from(row.children).filter((cell) => cell.matches("td,th"));
      const card = document.createElement("article");
      card.className = "sg-auto-mobile-card";

      if (isEmptyRow(row)) {
        const empty = document.createElement("div");
        empty.className = "sg-empty-state mb-0";
        empty.innerHTML = cells[0]?.innerHTML || "Sin datos para mostrar.";
        card.appendChild(empty);
        return card;
      }

      const actionIndexes = cells
        .map((cell, index) => ({ cell, index, label: labels[index] || "" }))
        .filter(({ cell, index, label }) => isActionsLabel(label) || cell.classList.contains("sg-table-actions") || (index >= cells.length - 1 && cell.querySelector("a, button")))
        .map(({ index }) => index);

      const statusIndex = cells.findIndex((cell) => cell.querySelector(".badge"));
      const titleIndex = cells.findIndex((_, index) => !actionIndexes.includes(index));
      const subtitleIndex = cells.findIndex((_, index) => index !== titleIndex && index !== statusIndex && !actionIndexes.includes(index));

      const header = document.createElement("div");
      header.className = "sg-auto-mobile-card__header";

      const titleWrap = document.createElement("div");
      titleWrap.className = "min-w-0";

      if (labels[titleIndex]) {
        const label = document.createElement("span");
        label.className = "sg-auto-mobile-card__label";
        label.textContent = labels[titleIndex];
        titleWrap.appendChild(label);
      }

      const title = document.createElement("strong");
      title.className = "sg-auto-mobile-card__title";
      title.appendChild(cloneCellContent(cells[titleIndex] || cells[0]));
      titleWrap.appendChild(title);

      if (subtitleIndex >= 0) {
        const subtitle = document.createElement("span");
        subtitle.className = "sg-auto-mobile-card__subtitle";
        subtitle.appendChild(cloneCellContent(cells[subtitleIndex]));
        titleWrap.appendChild(subtitle);
      }

      header.appendChild(titleWrap);

      if (statusIndex >= 0 && statusIndex !== titleIndex) {
        const status = document.createElement("div");
        status.className = "sg-auto-mobile-card__status";
        status.appendChild(cloneCellContent(cells[statusIndex]));
        header.appendChild(status);
      }

      card.appendChild(header);

      const grid = document.createElement("div");
      grid.className = "sg-auto-mobile-card__grid";

      cells.forEach((cell, index) => {
        if (index === titleIndex || index === subtitleIndex || index === statusIndex || actionIndexes.includes(index)) return;
        const labelText = labels[index] || `Dato ${index + 1}`;
        if (!normalizeLabel(cell.textContent) && !cell.querySelector("a, button, .badge")) return;

        const field = document.createElement("div");
        field.className = "sg-auto-mobile-card__field";

        const label = document.createElement("span");
        label.className = "sg-auto-mobile-card__label";
        label.textContent = labelText;

        const value = document.createElement("span");
        value.className = "sg-auto-mobile-card__value";
        value.appendChild(cloneCellContent(cell));

        field.append(label, value);
        grid.appendChild(field);
      });

      if (grid.children.length) card.appendChild(grid);

      if (actionIndexes.length) {
        const actions = document.createElement("div");
        actions.className = "sg-auto-mobile-card__actions";
        actionIndexes.forEach((index) => {
          const content = cloneCellContent(cells[index]);
          content.querySelectorAll("a, button").forEach((action) => {
            action.classList.add("sg-btn-sm", "sg-mobile-action-btn");
            if (!normalizeLabel(action.textContent)) {
              action.appendChild(document.createTextNode(` ${getActionFallbackLabel(action)}`));
            }
          });
          actions.appendChild(content);
        });
        card.appendChild(actions);
      }

      return card;
    }

    function getContainer(table) {
      const responsive = table.closest(".table-responsive");
      return responsive || table;
    }

    function hasManualMobileList(container) {
      let sibling = container.nextElementSibling;
      while (sibling && sibling.nodeType === 1) {
        if (sibling.matches(".d-md-none, .d-lg-none, .sg-mobile-list, [class*='mobile-list']")) return true;
        if (!sibling.matches("script, style")) return false;
        sibling = sibling.nextElementSibling;
      }
      return false;
    }

    function rebuildTable(table) {
      if (!tableCanBeConverted(table)) return;

      const container = getContainer(table);
      if (hasManualMobileList(container)) return;

      const labels = getLabels(table);
      const bodyRows = Array.from(table.tBodies[0]?.rows || [])
        .filter((row) => !row.classList.contains("d-none"));

      let list = container.nextElementSibling;
      if (!list || !list.classList?.contains(MOBILE_LIST_CLASS)) {
        list = document.createElement("div");
        list.className = MOBILE_LIST_CLASS;
        list.setAttribute("aria-label", "Listado móvil");
        container.insertAdjacentElement("afterend", list);
      }

      list.innerHTML = "";
      bodyRows.forEach((row) => list.appendChild(buildCard(row, labels)));
      container.classList.add(TABLE_WRAPPER_CLASS);
    }

    function rebuildAll() {
      document.querySelectorAll("table.sg-table").forEach(rebuildTable);
    }

    rebuildAll();

    if (window.jQuery) {
      window.jQuery(document).on("draw.dt", () => window.requestAnimationFrame(rebuildAll));
    }

    const observer = new MutationObserver((mutations) => {
      const shouldRebuild = mutations.some((mutation) => {
        const target = mutation.target;
        return target instanceof HTMLElement && Boolean(target.closest?.("table.sg-table"));
      });
      if (shouldRebuild) window.requestAnimationFrame(rebuildAll);
    });

    document.querySelectorAll("table.sg-table tbody").forEach((tbody) => {
      observer.observe(tbody, { childList: true, subtree: true, characterData: true });
    });
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      window.closeSidebar?.();
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth >= 992) {
      window.closeSidebar?.();
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    initActiveMenu();
    initMenuSearch();
    initThemeSwitcher();
    initResponsiveTables();
  });
})();
