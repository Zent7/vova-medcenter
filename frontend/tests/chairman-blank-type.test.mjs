import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

test("GIMS chairman lookup uses the GIMS blank inventory", () => {
  const blankTypeSource = sourceBetween(
    "function normalizeBlankSeries",
    "function getCertificatePrintTypeLabel",
  );
  const context = vm.createContext({});
  vm.runInContext(
    `${blankTypeSource}; this.resolveBlankType = resolveDriverPrintBlankType;`,
    context,
  );

  assert.equal(
    context.resolveBlankType({ selectedCertificateType: "gims", selectedSeries: "ГИМС" }),
    "gims_medical_certificate",
  );
});

test("chairman blank request resolves the inventory type from the selected certificate", () => {
  const chairmanLookupSource = sourceBetween(
    "const findChairmanBlank = async",
    "chairmanPrintBlankState.findBlank = findChairmanBlank",
  );

  assert.match(chairmanLookupSource, /const blankType = resolveDriverPrintBlankType/);
  assert.match(chairmanLookupSource, /blank_type: blankType/);
  assert.doesNotMatch(chairmanLookupSource, /blank_type: ["']driver_medical_certificate["']/);
});
