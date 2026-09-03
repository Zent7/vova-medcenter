import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const appSource = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");
const clientModalSource = readFileSync(resolve(import.meta.dirname, "../public/demo/client-modal.js"), "utf8");

test("driver categories are not invented from an empty value", () => {
  const normalizerMatch = appSource.match(/function normalizeDriverCategories\(categories\) \{([\s\S]*?)\n\}/);
  assert.ok(normalizerMatch, "normalizeDriverCategories must be declared");

  assert.match(normalizerMatch[1], /if \(!source\.length\) return \[\];/);
  assert.doesNotMatch(normalizerMatch[1], /\["A", "B"\]/);
});

test("new driver visits default to category B only", () => {
  assert.match(appSource, /const DRIVER_DEFAULT_CATEGORIES = \["B"\];/);
  assert.match(clientModalSource, /const CLIENT_DRIVER_DEFAULT_CATEGORIES = \["B"\];/);
  assert.doesNotMatch(clientModalSource, /const CLIENT_DRIVER_DEFAULT_CATEGORIES = \["A", "B", "C", "D", "BE", "M"\];/);
});

test("selected driver categories are never rewritten behind the operator", () => {
  assert.doesNotMatch(appSource, /DRIVER_LEGACY_DEFAULT_CATEGORY_SET/);
  assert.doesNotMatch(appSource, /normalizeStoredDriverCategories/);
});

test("the chairman card does not pre-tick categories the client did not choose", () => {
  const templatesSource = readFileSync(resolve(import.meta.dirname, "../public/demo/doctor-templates.js"), "utf8");
  for (const key of ["categoryA", "categoryC", "categoryD"]) {
    const label = key.slice("category".length);
    assert.ok(
      templatesSource.includes(`{ key: "${key}", label: "${label}", type: "checkbox", defaultValue: false }`),
      `${key} must stay unchecked by default`,
    );
  }
});
