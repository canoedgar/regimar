(function () {
  "use strict";

  function isTextArea(el) {
    return el && el.tagName === "TEXTAREA";
  }

  function getFocusable(form) {
    return Array.from(
      form.querySelectorAll(
        'input:not([type="hidden"]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), a[href]'
      )
    ).filter(function (el) {
      return el.offsetParent !== null && !el.hasAttribute("aria-hidden");
    });
  }

  function focusNext(form, current) {
    const focusables = getFocusable(form);
    const index = focusables.indexOf(current);
    if (index >= 0 && index < focusables.length - 1) {
      focusables[index + 1].focus();
      return true;
    }
    return false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("form.sg-inventory-form").forEach(function (form) {
      form.addEventListener("keydown", function (event) {
        if (event.key !== "Enter") return;

        const target = event.target;
        const isSubmitButton = target && target.matches('button[type="submit"], input[type="submit"]');

        if (isTextArea(target) || isSubmitButton) return;

        if (form.hasAttribute("data-sg-prevent-enter-submit")) {
          event.preventDefault();
          focusNext(form, target);
        }
      });

      form.addEventListener("submit", function (event) {
        const message = form.getAttribute("data-sg-confirm");
        if (!message) return;

        const submitter = event.submitter;
        if (submitter && submitter.hasAttribute("formnovalidate")) return;

        if (!window.confirm(message)) {
          event.preventDefault();
        }
      });

      form.addEventListener("focusin", function (event) {
        if (event.target && event.target.matches("input, select, textarea, button, a")) {
          event.target.setAttribute("data-sg-focus-visible", "true");
        }
      });

      form.addEventListener("focusout", function (event) {
        if (event.target) {
          event.target.removeAttribute("data-sg-focus-visible");
        }
      });
    });
  });
})();
