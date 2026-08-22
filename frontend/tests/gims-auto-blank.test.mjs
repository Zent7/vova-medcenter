import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolve } from "node:path";

const appSource = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

test("GIMS print flow automatically loads the next free blank", () => {
  const printFlow = sourceBetween(
    "async function openDriverPrintFlow",
    "window.openDriverPrintFlow = openDriverPrintFlow",
  );

  assert.match(appSource, /if \(normalizedType === "gims"\) return BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE/);
  assert.match(printFlow, />Найти номер<\/button>/);
  assert.match(printFlow, /\/blanks\/forms\/next\?/);
  assert.match(printFlow, /blank_type: flowState\.blankType/);
  assert.match(printFlow, /series: lookupSeries \|\| ""/);
  assert.doesNotMatch(printFlow, /manualGimsBlank/);
  assert.doesNotMatch(printFlow, /\/blanks\/forms\/exact\?/);
  assert.doesNotMatch(printFlow, /Проверить номер/);
});
