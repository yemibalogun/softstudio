/*
  Live dashboard.

  The page already arrives fully rendered; this file only keeps it current:
  it draws the traffic chart and, every 20 seconds, pulls fresh numbers and
  swaps them in place. Nothing here is required for the page to be readable,
  so a failed poll is logged and ignored rather than shown as an error.

  No chart library: the site's CSP allows scripts from this origin only, and
  one SVG path is cheaper than any dependency.
*/
(function () {
  "use strict";

  var POLL_MS = 20000;
  var root = document.querySelector("[data-dashboard]");
  if (!root) return;

  var endpoint = root.getAttribute("data-endpoint");
  var range = root.getAttribute("data-range") || "24h";
  var chartEl = root.querySelector("[data-chart]");
  var updatedEl = root.querySelector("[data-updated-at]");
  var lastUpdated = Date.now();

  // ---------------------------------------------------------------- helpers

  function at(obj, path) {
    return path.split(".").reduce(function (acc, key) {
      return acc == null ? undefined : acc[key];
    }, obj);
  }

  function formatNumber(value) {
    if (typeof value !== "number") return value;
    return value.toLocaleString();
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function relativeTime(ms) {
    var seconds = Math.round((Date.now() - ms) / 1000);
    if (seconds < 10) return "updated just now";
    if (seconds < 60) return "updated " + seconds + "s ago";
    var minutes = Math.round(seconds / 60);
    return "updated " + minutes + (minutes === 1 ? " minute ago" : " minutes ago");
  }

  function shortDate(value) {
    if (!value) return "";
    var d = new Date(value);
    if (isNaN(d)) return "";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }

  // ------------------------------------------------------------------ chart

  function drawChart(series) {
    if (!chartEl || !series || !series.length) return;

    var W = 800, H = 260, padL = 8, padR = 8, padT = 18, padB = 26;
    var innerW = W - padL - padR, innerH = H - padT - padB;
    var peak = Math.max.apply(null, series.map(function (p) { return p.views; }).concat([1]));

    function x(i) {
      return padL + (series.length === 1 ? innerW / 2 : (i * innerW) / (series.length - 1));
    }
    function y(value) {
      return padT + innerH - (value / peak) * innerH;
    }

    function pathFor(key) {
      return series.map(function (point, i) {
        return (i ? "L" : "M") + x(i).toFixed(1) + " " + y(point[key]).toFixed(1);
      }).join(" ");
    }

    var area =
      pathFor("views") +
      " L" + x(series.length - 1).toFixed(1) + " " + (padT + innerH) +
      " L" + x(0).toFixed(1) + " " + (padT + innerH) + " Z";

    // Four horizontal guides, labelled at the top one only — enough to read
    // the scale without turning the card into graph paper.
    var guides = "";
    for (var g = 0; g <= 3; g++) {
      var gy = padT + (innerH / 3) * g;
      guides += '<line class="dash-chart__grid" x1="' + padL + '" y1="' + gy.toFixed(1) +
                '" x2="' + (W - padR) + '" y2="' + gy.toFixed(1) + '"></line>';
    }

    // Sparse x labels: first, middle, last.
    var labels = "";
    [0, Math.floor(series.length / 2), series.length - 1].forEach(function (i, n) {
      if (i < 0 || i >= series.length) return;
      var anchor = n === 0 ? "start" : n === 2 ? "end" : "middle";
      labels += '<text x="' + x(i).toFixed(1) + '" y="' + (H - 8) + '" text-anchor="' + anchor + '">' +
                escapeHtml(series[i].label) + "</text>";
    });

    // One hover target per point, with a dot and a value that appears on it.
    var hits = "";
    var slot = innerW / Math.max(series.length - 1, 1);
    series.forEach(function (point, i) {
      var px = x(i), py = y(point.views);
      hits +=
        '<rect class="dash-chart__hit" x="' + (px - slot / 2).toFixed(1) + '" y="' + padT +
        '" width="' + slot.toFixed(1) + '" height="' + innerH + '" fill="transparent">' +
        "<title>" + escapeHtml(point.label) + ": " + point.views + " views, " +
        point.visitors + " visitors</title></rect>" +
        '<g class="dash-chart__marker"><circle cx="' + px.toFixed(1) + '" cy="' + py.toFixed(1) +
        '" r="3.5" fill="#7CCBFF"></circle></g>';
    });

    chartEl.innerHTML =
      '<defs><linearGradient id="dashArea" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="#3A78FF" stop-opacity="0.30"></stop>' +
      '<stop offset="100%" stop-color="#3A78FF" stop-opacity="0"></stop>' +
      "</linearGradient></defs>" +
      guides +
      '<path class="dash-chart__area" d="' + area + '"></path>' +
      '<path class="dash-chart__line dash-chart__line--muted" d="' + pathFor("visitors") + '"></path>' +
      '<path class="dash-chart__line" d="' + pathFor("views") + '"></path>' +
      labels + hits;
  }

  // ------------------------------------------------------------ list render

  var renderers = {
    top_pages: function (rows, peak) {
      return rows.map(function (row) {
        return bar(row.path, row.views, peak);
      }).join("") || empty("No visits recorded yet.");
    },
    top_sources: function (rows, peak) {
      return rows.map(function (row) {
        return bar(row.source || "direct", row.views, peak);
      }).join("") || empty("No sources recorded yet.");
    },
    devices: function (rows) {
      return rows.map(function (row) {
        return '<span class="dash-tag dash-tag--muted">' + escapeHtml(row.device) + " " + row.percent + "%</span>";
      }).join("");
    },
    products: function (rows) {
      return rows.map(function (row) {
        var tags = '<span class="dash-tag dash-tag--muted">' + row.views + " views</span>";
        if (row.downloads) tags += '<span class="dash-tag dash-tag--ok">' + row.downloads + " downloads</span>";
        if (row.signups) tags += '<span class="dash-tag dash-tag--info">' + row.signups + " waitlist</span>";
        return (
          '<div class="dash-row"><div class="min-w-0">' +
          '<div class="dash-row__label">' + escapeHtml(row.title) + "</div>" +
          '<div class="dash-row__sub">/products/' + escapeHtml(row.slug) + "</div></div>" +
          '<div class="flex items-center gap-2">' + tags + "</div></div>"
        );
      }).join("") || empty("No product activity in this period.");
    },
    recent_signups: function (rows) {
      return rows.map(function (row) {
        var sub = escapeHtml(row.kind) + (row.product ? " · " + escapeHtml(row.product) : "") +
                  " · " + escapeHtml(row.source || "direct");
        return (
          '<div class="dash-row"><div class="min-w-0">' +
          '<div class="dash-row__label">' + escapeHtml(row.email) + "</div>" +
          '<div class="dash-row__sub">' + sub + "</div></div>" +
          '<div class="dash-row__value text-xs">' + escapeHtml(shortDate(row.at)) + "</div></div>"
        );
      }).join("") || empty("No signups yet.");
    },
    "errors.recent": function (rows) {
      var tone = {
        server_error: "dash-tag--danger", not_found: "dash-tag--warn",
        security: "dash-tag--info", delivery: "dash-tag--warn",
      };
      return rows.map(function (row) {
        return (
          '<div class="dash-row"><div class="min-w-0">' +
          '<div class="dash-row__label"><a class="link link-hover" href="errors/' + row.id + '">' +
          escapeHtml(row.message) + "</a></div>" +
          '<div class="dash-row__sub">' + escapeHtml(row.path || "—") + " · " + row.occurrences + "×</div></div>" +
          '<span class="dash-tag ' + (tone[row.kind] || "dash-tag--muted") + '">' +
          escapeHtml(String(row.kind).replace("_", " ")) + "</span></div>"
        );
      }).join("") || empty("Nothing has gone wrong in this period.");
    },
    "renewals.due": function (rows) {
      return rows.map(function (row) {
        var tone = row.is_overdue ? "dash-tag--danger" : row.days_until_due <= 7 ? "dash-tag--warn" : "dash-tag--muted";
        var when = row.is_overdue
          ? Math.abs(row.days_until_due) + "d overdue"
          : row.days_until_due === 0 ? "due today" : "in " + row.days_until_due + "d";
        return (
          '<div class="dash-row"><div class="min-w-0">' +
          '<div class="dash-row__label">' + escapeHtml(row.name) +
          (row.vendor ? ' <span class="opacity-45">· ' + escapeHtml(row.vendor) + "</span>" : "") + "</div>" +
          '<div class="dash-row__sub">' + escapeHtml(row.currency) + " " + Number(row.amount).toFixed(2) +
          " · " + escapeHtml(String(row.cycle).replace("_", " ")) + " · " + escapeHtml(shortDate(row.due_on)) +
          "</div></div><span class='dash-tag " + tone + "'>" + when + "</span></div>"
        );
      }).join("") || empty("Nothing due in the next 60 days.");
    },
  };

  function bar(label, value, peak) {
    var share = Math.round((value * 100) / (peak || 1));
    return (
      '<div class="dash-row"><div class="min-w-0">' +
      '<div class="dash-row__label">' + escapeHtml(label) + "</div>" +
      '<span class="dash-bar"><span style="width: ' + share + '%"></span></span></div>' +
      '<div class="dash-row__value">' + formatNumber(value) + "</div></div>"
    );
  }

  function empty(message) {
    return '<p class="dash-empty">' + escapeHtml(message) + "</p>";
  }

  // ------------------------------------------------------------------ apply

  function apply(data) {
    root.querySelectorAll("[data-metric]").forEach(function (el) {
      var value = at(data, el.getAttribute("data-metric"));
      if (value === undefined) return;
      var next = formatNumber(value);
      if (el.textContent.trim() === String(next)) return;
      el.textContent = next;
      var tile = el.closest(".dash-stat__value") || (el.classList.contains("dash-stat__value") ? el : null);
      if (tile) {
        tile.classList.remove("is-updated");
        void tile.offsetWidth; // restart the animation
        tile.classList.add("is-updated");
      }
    });

    var live = root.querySelector(".dash-live");
    if (live && data.live) live.setAttribute("data-online", data.live.online_now);

    root.querySelectorAll("[data-list]").forEach(function (el) {
      var key = el.getAttribute("data-list");
      var rows = at(data, key);
      var render = renderers[key];
      if (!render || !rows) return;
      var peak = rows.length && rows[0].views ? rows[0].views : 1;
      el.innerHTML = render(rows, peak);
    });

    drawChart(data.series);
    lastUpdated = Date.now();
  }

  function poll() {
    if (document.hidden) return; // a background tab does not need fresh numbers
    fetch(endpoint + "?range=" + encodeURIComponent(range), {
      headers: { "Accept": "application/json" },
      credentials: "same-origin",
    })
      .then(function (response) {
        if (!response.ok) throw new Error("dashboard poll failed: " + response.status);
        return response.json();
      })
      .then(apply)
      .catch(function (err) {
        if (window.console) console.warn(err);
      });
  }

  // first paint from the server-rendered series, then keep it live
  try {
    drawChart(JSON.parse(chartEl.getAttribute("data-series") || "[]"));
  } catch (err) {
    if (window.console) console.warn("chart bootstrap failed", err);
  }

  window.setInterval(poll, POLL_MS);
  window.setInterval(function () {
    if (updatedEl) updatedEl.textContent = relativeTime(lastUpdated);
  }, 5000);
  document.addEventListener("visibilitychange", function () {
    if (!document.hidden) poll();
  });
})();
