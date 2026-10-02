"use strict";

// Runs before the page paints, so the chosen theme never flashes in the wrong colors.
(() => {
  let choice = "auto";
  try {
    choice = localStorage.getItem("rpa.theme") || "auto";
  } catch {}
  const dark = choice === "dark" ||
    (choice !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
