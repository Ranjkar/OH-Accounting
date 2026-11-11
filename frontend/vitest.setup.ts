import "@testing-library/jest-dom/vitest";

// jsdom implements focus() but not scrollIntoView, which real browsers have
// had since forever. Components call it to centre an invalid field after a
// blocked submit; without this shim those tests throw a TypeError for a
// method that exists in every browser we ship to.
if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
