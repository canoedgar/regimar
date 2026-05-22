(function () {
  "use strict";

  function normalizeText(value) {
    return (value || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .trim();
  }

  window.toggleSidebar = function toggleSidebar() {
    const sidebar = document.getElementById("solarSidebar");
    const overlay = document.getElementById("sidebarOverlay");
    if (!sidebar) return;

    const isOpen = sidebar.classList.toggle("show");
    overlay?.classList.toggle("show", isOpen);
    document.body.classList.toggle("sidebar-open", isOpen);
  };

  window.closeSidebar = function closeSidebar() {
    document.getElementById("solarSidebar")?.classList.remove("show");
    document.getElementById("sidebarOverlay")?.classList.remove("show");
    document.body.classList.remove("sidebar-open");
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
        target.classList.toggle("show", shouldShow);
        target.classList.remove("menu-search-open");
        toggle.classList.remove("d-none");
        toggle.setAttribute("aria-expanded", String(shouldShow));
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
        target.classList.toggle("show", shouldShow);
        target.classList.toggle("menu-search-open", shouldShow);
        toggle.setAttribute("aria-expanded", String(shouldShow));
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
    parentCollapse.classList.add("show");
    parentToggle?.classList.add("active", "is-active");
    parentToggle?.setAttribute("aria-expanded", "true");
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

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      window.closeSidebar?.();
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    initActiveMenu();
    initMenuSearch();
    initThemeSwitcher();
  });
})();
