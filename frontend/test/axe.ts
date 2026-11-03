import axe from "axe-core";

/** Runs real axe-core rules against a rendered DOM node inside jsdom.
 * Important, honest caveat: jsdom has no layout/paint engine, so
 * axe-core's `color-contrast` rule cannot run here (axe-core itself
 * detects this and skips it) -- contrast is verified separately via
 * scripts/contrast-check.py against the actual token values, not by this
 * test. What this DOES catch in a real jsdom environment: missing
 * accessible names, invalid ARIA attribute values/combinations, missing
 * form labels, duplicate ids, invalid landmark structure, and other
 * static-markup rules that don't require rendering. */
export async function expectNoAxeViolations(container: Element) {
  const results = await axe.run(container, {
    rules: {
      "color-contrast": { enabled: false }, // not meaningful in jsdom -- verified separately
    },
  });
  if (results.violations.length > 0) {
    const details = results.violations
      .map((v) => `- [${v.id}] ${v.help}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`)
      .join("\n");
    throw new Error(`axe-core found ${results.violations.length} violation(s):\n${details}`);
  }
}
