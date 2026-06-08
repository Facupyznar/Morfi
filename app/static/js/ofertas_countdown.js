/* Contador regresivo para las ofertas temporales.
 * Busca elementos `.promo-countdown[data-deadline]` (ISO local sin tz) y
 * actualiza el texto cada segundo con el tiempo restante hasta fecha_fin. */
(function () {
  "use strict";

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function formatRestante(ms) {
    var totalSeg = Math.floor(ms / 1000);
    var dias = Math.floor(totalSeg / 86400);
    var horas = Math.floor((totalSeg % 86400) / 3600);
    var min = Math.floor((totalSeg % 3600) / 60);
    var seg = totalSeg % 60;

    if (dias > 0) {
      return dias + "d " + pad(horas) + "h " + pad(min) + "m";
    }
    return pad(horas) + ":" + pad(min) + ":" + pad(seg);
  }

  function tick() {
    var ahora = new Date();
    document.querySelectorAll(".promo-countdown[data-deadline]").forEach(function (el) {
      var textEl = el.querySelector(".promo-countdown-text");
      if (!textEl) return;

      var deadline = new Date(el.getAttribute("data-deadline"));
      if (isNaN(deadline.getTime())) {
        textEl.textContent = "";
        return;
      }

      var restante = deadline.getTime() - ahora.getTime();
      if (restante <= 0) {
        textEl.textContent = "Expirada";
        el.classList.add("promo-countdown--expired");
      } else {
        textEl.textContent = "Termina en " + formatRestante(restante);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!document.querySelector(".promo-countdown[data-deadline]")) return;
    tick();
    setInterval(tick, 1000);
  });
})();
