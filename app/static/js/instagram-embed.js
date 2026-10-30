/*
  /reels: play a reel in place, on request only.

  Each card's play control is a link to the post on Instagram. Here it is
  upgraded: pressing it swaps the cover for Instagram's embedded player, so
  Instagram loads - and can set cookies - only for someone who asked to watch.
*/
(function () {
  "use strict";

  document.addEventListener("click", function (event) {
    var control = event.target.closest("[data-ig-play]");
    if (!control) return;
    var stage = control.closest("[data-ig-frame]");
    if (!stage || !stage.dataset.embedSrc) return;   // no stage: let the link open Instagram
    event.preventDefault();
    if (stage.dataset.loaded) return;

    var player = document.createElement("iframe");
    player.className = "reel-iframe";
    player.src = stage.dataset.embedSrc;
    player.title = stage.dataset.embedTitle || "Instagram reel";
    player.setAttribute("allowfullscreen", "");
    player.setAttribute("scrolling", "no");

    stage.replaceChildren(player);
    stage.dataset.loaded = "1";
    stage.classList.add("is-playing");
    player.focus();
  });
})();
