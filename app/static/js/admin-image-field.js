/*
 * Admin image field: live preview plus early feedback on type and size.
 *
 * Convenience only. The server re-validates and re-encodes every upload
 * (app/uploads.py); nothing here is a security boundary. The preview uses
 * a data: URL because the CSP allows data: images but not blob:.
 */
(function () {
  "use strict";

  var ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];
  var ALLOWED_EXTENSIONS = ["jpg", "jpeg", "png", "webp"];

  document.querySelectorAll("[data-image-field]").forEach(function (field) {
    var input = field.querySelector("[data-image-input]");
    var preview = field.querySelector("[data-image-preview]");
    var empty = field.querySelector("[data-image-empty]");
    var errorBox = field.querySelector("[data-image-error]");
    if (!input || !preview) return;

    var maxBytes = parseInt(input.getAttribute("data-max-bytes"), 10) || 5 * 1024 * 1024;
    var originalSrc = preview.getAttribute("src");

    function showError(message) {
      if (!errorBox) return;
      errorBox.textContent = message;
      errorBox.hidden = !message;
      errorBox.classList.toggle("hidden", !message);
    }

    function showPreview(src) {
      if (src) {
        preview.setAttribute("src", src);
      } else {
        preview.removeAttribute("src");
      }
      preview.classList.toggle("hidden", !src);
      if (empty) empty.classList.toggle("hidden", !!src);
    }

    input.addEventListener("change", function () {
      var file = input.files && input.files[0];
      showError("");

      if (!file) {
        showPreview(originalSrc);
        return;
      }

      var extension = (file.name.split(".").pop() || "").toLowerCase();
      if (ALLOWED_TYPES.indexOf(file.type) === -1 || ALLOWED_EXTENSIONS.indexOf(extension) === -1) {
        showError("Choose a JPG, PNG or WebP image.");
        input.value = "";
        showPreview(originalSrc);
        return;
      }

      if (file.size > maxBytes) {
        showError("That image is " + (file.size / 1048576).toFixed(1) + " MB. The limit is " + Math.floor(maxBytes / 1048576) + " MB.");
        input.value = "";
        showPreview(originalSrc);
        return;
      }

      var reader = new FileReader();
      reader.onload = function () {
        showPreview(reader.result);
      };
      reader.readAsDataURL(file);
    });
  });
})();
