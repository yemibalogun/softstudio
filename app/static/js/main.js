document.addEventListener("DOMContentLoaded", () => {
  initMobileNav();
  initCookieConsent();
  initModals();
});

/* ---------------- Mobile navigation ---------------- */
function initMobileNav() {
  const toggle = document.querySelector("[data-nav-toggle]");
  const panel = document.querySelector("[data-nav-panel]");

  if (!toggle || !panel) return;

  const closeMenu = () => {
    // `hidden` provides the actual visibility state. This avoids relying
    // on a custom CSS class just to show/hide the navigation panel.
    panel.hidden = true;

    toggle.setAttribute("aria-expanded", "false");
    toggle.setAttribute("aria-label", "Open menu");

    document.body.style.overflow = "";
  };

  const openMenu = () => {
    panel.hidden = false;

    toggle.setAttribute("aria-expanded", "true");
    toggle.setAttribute("aria-label", "Close menu");

    // Prevent the page behind the mobile menu from scrolling.
    document.body.style.overflow = "hidden";

    const firstLink = panel.querySelector("a");

    if (firstLink) {
      firstLink.focus();
    }
  };

  toggle.addEventListener("click", () => {
    panel.hidden ? openMenu() : closeMenu();
  });

  // Close the mobile menu when the user selects a navigation link.
  panel.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  // Allow keyboard users to close the menu with Escape.
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) {
      closeMenu();
      toggle.focus();
    }
  });

  // Ensure the menu starts closed even if the HTML state changes later.
  closeMenu();
}

/* ---------------- Cookie consent ---------------- */
function initCookieConsent() {
  const banner = document.querySelector("[data-cookie-banner]");
  if (!banner) return;

  const COOKIE_NAME = "cookie_consent";

  const getConsentCookie = () => {
    const match = document.cookie.match(new RegExp(`${COOKIE_NAME}=([^;]+)`));
    return match ? JSON.parse(decodeURIComponent(match[1])) : null;
  };

  const setConsentCookie = (value) => {
    const maxAge = 60 * 60 * 24 * 365;
    document.cookie = `${COOKIE_NAME}=${encodeURIComponent(
      JSON.stringify(value)
    )}; max-age=${maxAge}; path=/; SameSite=Lax`;
  };

  const applyConsent = (consent) => {
    if (consent.analytics) {
      document.dispatchEvent(new CustomEvent("consent:analytics-granted"));
    }
    if (consent.marketing) {
      document.dispatchEvent(new CustomEvent("consent:marketing-granted"));
    }
  };

  const existing = getConsentCookie();
  if (existing) {
    applyConsent(existing);
  } else {
    // Tailwind's `hidden` utility controls visibility.
    // Remove it when consent has not yet been provided.
    banner.classList.remove("hidden");
  }

  const persistAndHide = (consent) => {
    setConsentCookie(consent);
    applyConsent(consent);
    // Hide the banner after the user's choice has been saved.
    banner.classList.add("hidden");
  };

  banner.querySelector("[data-cookie-accept-all]")?.addEventListener("click", () =>
    persistAndHide({ necessary: true, analytics: true, marketing: true })
  );
  banner.querySelector("[data-cookie-reject]")?.addEventListener("click", () =>
    persistAndHide({ necessary: true, analytics: false, marketing: false })
  );
  banner.querySelector("[data-cookie-manage]")?.addEventListener("click", () => {
    const modal = document.querySelector("[data-cookie-preferences-modal]");
    if (modal) modal.classList.add("is-open");
  });

  const prefsForm = document.querySelector("[data-cookie-preferences-form]");
  prefsForm?.addEventListener("submit", (e) => {
    e.preventDefault();
    const formData = new FormData(prefsForm);
    persistAndHide({
      necessary: true,
      analytics: formData.get("analytics") === "on",
      marketing: formData.get("marketing") === "on",
    });
    document.querySelector("[data-cookie-preferences-modal]")?.classList.remove("is-open");
  });

  // Footer "Cookie Settings" link reopens the preferences modal.
  document.querySelectorAll("[data-open-cookie-settings]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      document.querySelector("[data-cookie-preferences-modal]")?.classList.add("is-open");
    });
  });
}

/* ---------------- Modals ---------------- */
function initModals() {
  document.querySelectorAll("[data-modal-close]").forEach((btn) => {
    btn.addEventListener("click", () => {
      btn.closest(".modal-overlay")?.classList.remove("is-open");
    });
  });

  document.querySelectorAll(".modal-overlay").forEach((overlay) => {
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) overlay.classList.remove("is-open");
    });
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-overlay.is-open").forEach((o) => o.classList.remove("is-open"));
    }
  });
}
