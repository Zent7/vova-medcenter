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
  assert.match(clientModalSource, /const CLIENT_DRIVER_DEFAULT_CATEGORIES = \["B"\];/);
  assert.doesNotMatch(clientModalSource, /const CLIENT_DRIVER_DEFAULT_CATEGORIES = \["A", "B", "C", "D", "BE", "M"\];/);
});
