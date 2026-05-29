(() => {
  "use strict";

  function getSelectedNoteIds() {
    return Array.from(document.querySelectorAll(".nota-check:checked"))
      .map((checkbox) => checkbox.value)
      .filter(Boolean);
  }

  function printSelectedNotes(button) {
    const ids = getSelectedNoteIds();

    if (!ids.length) {
      window.alert("Selecciona al menos una nota.");
      return;
    }

    const printUrl = button.dataset.printUrl;
    if (!printUrl) {
      window.alert("No se encontró la ruta de impresión.");
      return;
    }

    window.open(`${printUrl}?ids=${encodeURIComponent(ids.join(","))}`, "_blank");
  }

  document.addEventListener("DOMContentLoaded", () => {
    const printButton = document.getElementById("btnImprimirSeleccionadas");

    if (printButton) {
      printButton.addEventListener("click", () => printSelectedNotes(printButton));
    }

    document.querySelectorAll(".ventas-cancel-form").forEach((form) => {
      form.addEventListener("submit", (event) => {
        const message = form.dataset.confirmMessage || "¿Confirmar cancelación?";
        if (!window.confirm(message)) {
          event.preventDefault();
        }
      });
    });
  });
})();
