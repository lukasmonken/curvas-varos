/* Só interface (seção 5): modo CORRIGIDO/LEGADO, taxa/fator, data de comparação e abas.
   Nenhum número é calculado aqui; os gráficos já trazem todos os traços e este
   arquivo só alterna a visibilidade deles (Plotly.restyle). */
(function () {
  "use strict";

  var root = document.documentElement;
  var MODE_KEY = "curvas-modo";

  function save(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (e) {
      /* sem armazenamento: a escolha vale só nesta página */
    }
  }

  function each(selector, fn, scope) {
    Array.prototype.forEach.call((scope || document).querySelectorAll(selector), fn);
  }

  function charts(scope) {
    return (scope || document).querySelectorAll(".js-plotly-plot");
  }

  function refreshCharts() {
    if (!window.Plotly) return;
    var mode = root.getAttribute("data-mode");
    var compare = root.getAttribute("data-compare") || "";
    Array.prototype.forEach.call(charts(), function (gd) {
      if (!gd.data) return;
      var visible = gd.data.map(function (trace) {
        var meta = trace.meta || {};
        if (meta.mode && meta.mode !== mode) return false;
        if (meta.role === "compare") return meta.date === compare;
        return true;
      });
      window.Plotly.restyle(gd, { visible: visible });
    });
  }

  function resizeCharts(scope) {
    if (!window.Plotly) return;
    Array.prototype.forEach.call(charts(scope), function (gd) {
      if (gd.offsetParent !== null) window.Plotly.Plots.resize(gd);
    });
  }

  function setMode(mode, remember) {
    if (mode !== "corrected" && mode !== "legacy") return;
    root.setAttribute("data-mode", mode);
    each("[data-set-mode]", function (button) {
      button.setAttribute("aria-pressed", String(button.getAttribute("data-set-mode") === mode));
    });
    if (remember) save(MODE_KEY, mode);
    refreshCharts();
  }

  function setMeasure(measure) {
    root.setAttribute("data-measure", measure);
    each("[data-set-measure]", function (button) {
      var on = button.getAttribute("data-set-measure") === measure;
      button.setAttribute("aria-pressed", String(on));
    });
    resizeCharts();
  }

  function setupTabs(list) {
    var tabs = Array.prototype.slice.call(list.querySelectorAll('[role="tab"]'));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        var panel = document.getElementById(t.getAttribute("aria-controls"));
        if (panel) panel.hidden = !on;
      });
      if (focus) tab.focus();
      resizeCharts(document.getElementById(tab.getAttribute("aria-controls")));
    }
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () {
        select(tab, false);
      });
      tab.addEventListener("keydown", function (event) {
        var next = null;
        if (event.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
        else if (event.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
        else if (event.key === "Home") next = tabs[0];
        else if (event.key === "End") next = tabs[tabs.length - 1];
        if (next) {
          event.preventDefault();
          select(next, true);
        }
      });
    });
  }

  function init() {
    each("[data-set-mode]", function (button) {
      button.addEventListener("click", function () {
        setMode(button.getAttribute("data-set-mode"), true);
      });
    });
    each("[data-set-measure]", function (button) {
      button.addEventListener("click", function () {
        setMeasure(button.getAttribute("data-set-measure"));
      });
    });
    each("select[data-compare]", function (select) {
      select.addEventListener("change", function () {
        root.setAttribute("data-compare", select.value);
        refreshCharts();
      });
      root.setAttribute("data-compare", select.value);
    });
    each('[role="tablist"]', setupTabs);
    setMode(root.getAttribute("data-mode"), false);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
