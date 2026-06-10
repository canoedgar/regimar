(function () {
  "use strict";

  const shareBtn = document.getElementById("cotSharePdfBtn");
  if (!shareBtn) return;

  const pdfUrl = new URL(shareBtn.dataset.pdfUrl, window.location.origin).toString();

  async function openOrSharePdf() {
    if (navigator.share && window.matchMedia("(max-width: 767px)").matches) {
      try {
        await navigator.share({ title: shareBtn.dataset.folio || "Cotización", url: pdfUrl });
        return;
      } catch (err) {
        if (err && err.name === "AbortError") return;
      }
    }
    window.location.href = pdfUrl;
  }

  shareBtn.addEventListener("click", openOrSharePdf);

  const params = new URLSearchParams(window.location.search);
  if (params.get("open_pdf") === "1" && window.matchMedia("(max-width: 767px)").matches) {
    setTimeout(openOrSharePdf, 350);
  }
})();
