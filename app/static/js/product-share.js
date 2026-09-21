/*
  Product sharing.

  Native share sheet where the browser has one (phones, Safari, Edge);
  copy-to-clipboard everywhere else. The URL always comes from the server-
  rendered data-share-url (the canonical product URL), never from
  location.href, so a link shared from a page opened with campaign
  parameters still points at the clean canonical URL.

  No dependencies; the page works without this file (the network links and
  the copy button's fallback both degrade gracefully).
*/
(function () {
  "use strict";

  function flash(statusEl, labelEl, message) {
    if (statusEl) statusEl.textContent = message;
    if (!labelEl) return;
    var original = labelEl.dataset.originalLabel || labelEl.textContent;
    labelEl.dataset.originalLabel = original;
    labelEl.textContent = message;
    window.setTimeout(function () {
      labelEl.textContent = original;
    }, 2000);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }
    // Fallback for http:// origins and older browsers.
    return new Promise(function (resolve, reject) {
      var field = document.createElement("textarea");
      field.value = text;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.left = "-9999px";
      document.body.appendChild(field);
      field.select();
      try {
        var ok = document.execCommand("copy");
        document.body.removeChild(field);
        ok ? resolve() : reject(new Error("copy rejected"));
      } catch (err) {
        document.body.removeChild(field);
        reject(err);
      }
    });
  }

  document.querySelectorAll("[data-share]").forEach(function (root) {
    var url = root.getAttribute("data-share-url") || "";
    var title = root.getAttribute("data-share-title") || document.title;
    var text = root.getAttribute("data-share-text") || "";
    var statusEl = root.querySelector("[data-share-status]");
    var shareButton = root.querySelector("[data-share-button]");
    var copyButton = root.querySelector("[data-share-copy]");
    var copyLabel = root.querySelector("[data-share-copy-label]");

    if (shareButton && navigator.share) {
      shareButton.hidden = false;
      shareButton.addEventListener("click", function () {
        navigator
          .share({ title: title, text: text, url: url })
          .catch(function () {
            /* the user dismissed the sheet — nothing to report */
          });
      });
    }

    if (copyButton) {
      copyButton.addEventListener("click", function () {
        copyText(url).then(
          function () {
            flash(statusEl, copyLabel, "Link copied");
          },
          function () {
            flash(statusEl, copyLabel, "Press Ctrl+C to copy");
            window.prompt("Copy this link", url);
          }
        );
      });
    }
  });
})();
