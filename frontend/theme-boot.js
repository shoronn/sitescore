/* Sets the colour theme before the page paints, so there is no light flash in dark mode.
   Inlined into index.html at build time (vite.config.ts), so the page never waits for an extra
   download. The Content-Security-Policy in nginx/default.conf.template allows exactly this
   script by its hash; the build stops with the new hash if this file changes. */
(function () {
  var pref = "system";
  try {
    var saved = window.localStorage.getItem("sitescore-theme");
    if (saved === "light" || saved === "dark") pref = saved;
  } catch (e) {
    /* storage blocked: follow the system setting */
  }
  var dark = pref === "dark" || (pref === "system" && !!window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  var root = document.documentElement;
  root.setAttribute("data-theme", dark ? "dark" : "light");
  root.setAttribute("data-theme-pref", pref);
  var meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", dark ? "#000000" : "#F2F2F7");
})();
