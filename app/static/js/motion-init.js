/*
 * Loaded synchronously in <head>, before first paint.
 *
 * Adds html.js so the reveal styles (tailwind.input.css) can start content
 * hidden without a flash. If motion.js never takes over (blocked, failed to
 * load, threw), the class is removed after a short grace period so content
 * can never stay invisible. External file because the CSP forbids inline
 * scripts.
 */
(function () {
  var root = document.documentElement;
  root.classList.add("js");
  window.setTimeout(function () {
    if (!root.classList.contains("motion-live")) {
      root.classList.remove("js");
    }
  }, 3000);
})();
