(function () {
  const periodSelect = document.getElementById("periodo");
  const periodForm = document.getElementById("dashboardPeriodForm");

  if (periodSelect && periodForm) {
    periodSelect.addEventListener("change", function () {
      periodForm.submit();
    });
  }
})();
