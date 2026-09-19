/*
 * Site motion. Vanilla, no dependencies (the CSP only allows same-origin
 * scripts). Everything animates transform / opacity / filter, and all of it
 * stands down under prefers-reduced-motion.
 *
 *   [data-reveal]             blur-in when scrolled into view
 *   [data-reveal-group="90"]  staggers the reveals inside it (ms per step)
 *   [data-reveal-delay="200"] fixed extra delay for one element
 *   [data-site-header]        gets [data-scrolled] once the page moves
 *   .card, .row-link          pointer spotlight via --mx / --my
 *   [data-hero-scene]         eased scroll scene: the planet rises and
 *                             grows while the hero copy blurs away
 */
(function () {
  "use strict";

  var root = document.documentElement;
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function init() {
    root.classList.add("motion-live");
    initReveals();
    initHeader();
    initSpotlight();
    initHeroScene();
  }

  /* ---------------- Reveals ---------------- */
  function initReveals() {
    document.querySelectorAll("[data-reveal-group]").forEach(function (group) {
      var step = parseInt(group.getAttribute("data-reveal-group"), 10) || 90;
      group.querySelectorAll("[data-reveal]").forEach(function (el, i) {
        el.style.setProperty("--reveal-delay", i * step + "ms");
      });
    });

    document.querySelectorAll("[data-reveal-delay]").forEach(function (el) {
      el.style.setProperty("--reveal-delay", el.getAttribute("data-reveal-delay") + "ms");
    });

    var items = document.querySelectorAll("[data-reveal]");

    if (reduceMotion.matches || !("IntersectionObserver" in window)) {
      items.forEach(function (el) {
        el.classList.add("is-in");
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 }
    );

    items.forEach(function (el) {
      observer.observe(el);
    });
  }

  /* ---------------- Header ---------------- */
  function initHeader() {
    var header = document.querySelector("[data-site-header]");
    if (!header) return;

    var update = function () {
      header.toggleAttribute("data-scrolled", window.scrollY > 8);
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
  }

  /* ---------------- Pointer spotlight ---------------- */
  function initSpotlight() {
    if (!window.matchMedia("(hover: hover)").matches) return;

    document.addEventListener(
      "pointermove",
      function (event) {
        var target = event.target.closest && event.target.closest(".card, .row-link");
        if (!target) return;
        var rect = target.getBoundingClientRect();
        target.style.setProperty("--mx", event.clientX - rect.left + "px");
        target.style.setProperty("--my", event.clientY - rect.top + "px");
      },
      { passive: true }
    );
  }

  /* ---------------- Hero scroll scene ---------------- */
  function initHeroScene() {
    var scene = document.querySelector("[data-hero-scene]");
    if (!scene || reduceMotion.matches) return;

    var rig = scene.querySelector("[data-hero-planet]");
    var copy = scene.querySelector("[data-hero-copy]");
    if (!rig || !copy) return;

    var current = 0;
    var target = 0;
    var running = false;

    function measure() {
      var height = scene.offsetHeight || 1;
      target = Math.min(Math.max(window.scrollY / height, 0), 1);
    }

    function render() {
      // Ease toward the scroll position: a little inertia, never a jolt.
      current += (target - current) * 0.085;
      if (Math.abs(target - current) < 0.0005) current = target;

      var p = current;
      rig.style.transform =
        "translate3d(0," + (-p * 22).toFixed(3) + "svh,0) scale(" + (1 + p * 0.22).toFixed(4) + ")";

      var fade = Math.min(p * 1.7, 1);
      copy.style.opacity = (1 - fade).toFixed(3);
      copy.style.transform = "translate3d(0," + (-p * 7).toFixed(3) + "svh,0)";
      copy.style.filter = fade > 0.001 ? "blur(" + (fade * 10).toFixed(2) + "px)" : "none";

      if (current !== target) {
        window.requestAnimationFrame(render);
      } else {
        running = false;
      }
    }

    function onScroll() {
      measure();
      if (!running) {
        running = true;
        window.requestAnimationFrame(render);
      }
    }

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll, { passive: true });
    onScroll();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
