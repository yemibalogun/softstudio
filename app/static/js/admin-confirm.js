/*
  "Are you sure?" for destructive admin forms: <form data-confirm="...">.

  The site's Content-Security-Policy (script-src 'self') blocks inline
  handlers, so the onsubmit="return confirm(...)" these forms used to carry
  never ran and every Delete went through unasked. The message is read as
  plain text from the attribute, so a name or email in it can't run as code.
*/
(function () {
  "use strict";
  document.addEventListener("submit", function (event) {
    var form = event.target.closest("form[data-confirm]");
    if (form && !window.confirm(form.getAttribute("data-confirm"))) {
      event.preventDefault();
    }
  });
})();
