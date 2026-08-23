import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

test("LMK certificate series resolves to the LMK blank type", () => {
  const resolverSource = sourceBetween(
    "function getBlankTypeForCertificatePrintType",
    "function resolveDriverPrintBlankType",
  );
  assert.match(
    resolverSource,
    /normalizedType === "lmk"\) return BLANK_TYPE_LMK_MEDICAL_CERTIFICATE/,
  );
  assert.match(
    appSource,
    /const BLANK_TYPE_LMK_MEDICAL_CERTIFICATE = "lmk_medical_certificate"/,
  );
});

test("chairman blank lookup uses the selected certificate blank type", () => {
  const lookupSource = sourceBetween(
    "const findChairmanBlank = async",
    "chairmanPrintBlankState.findBlank = findChairmanBlank",
  );
  assert.match(lookupSource, /blank_type: resolveDriverPrintBlankType\(/);
  assert.doesNotMatch(lookupSource, /blank_type: "driver_medical_certificate"/);
});

test("LMK print menu separates the typographic book blank from automatic documents", () => {
  const menuSource = sourceBetween(
    "const openChairmanPrintMenu = () =>",
    "const runChairmanPrint = async",
  );
  assert.match(menuSource, /Типографский бланк ЛМК/);
  assert.match(menuSource, /Документы профосмотра — номер присваивается автоматически/);
  assert.match(menuSource, /value="29Н"/);
  assert.match(menuSource, /value="При печати"/);
  assert.doesNotMatch(menuSource, /Присвоить ЛМК/);
  assert.equal((menuSource.match(/data-chairman-print-menu-kind="lmk_title"/g) || []).length, 1);
});

test("only the LMK book requires a pre-entered LMK blank", () => {
  assert.match(appSource, /\["lmk_title", "ЛМК"\]/);
  assert.doesNotMatch(appSource, /CHAIRMAN_AUTO_CREATE_BLANK_SERIES = new Set\(\["ЛМК"/);
  assert.match(appSource, /isChairmanAutoNumberedPrintKind\(printKind\)/);
  assert.match(appSource, /chairmanPrintBlankState\.findBlank\(requiredBlankSeries, null, \{/);
  assert.match(
    appSource,
    /\? getChairmanBlankSeriesForPrintKind\(printKind\)/,
  );
  assert.match(appSource, /findLatestCertificateDocument\("lmk_title"\)/);
});

// Справка ЛМК идёт на чистом листе А4: номерной бланк ей не нужен,
// порядковый номер подставляет бэкенд.
test("LMK certificate never consumes a numbered blank", () => {
  assert.doesNotMatch(appSource, /\["lmk_certificate", "29Н"\]/);
  assert.match(appSource, /const CHAIRMAN_UNNUMBERED_PRINT_KINDS = new Set\(\["lmk_certificate"\]\)/);
  assert.doesNotMatch(
    appSource,
    /CHAIRMAN_AUTO_NUMBERED_PRINT_KINDS = new Set\(\[\s*"lmk_certificate"/,
  );
  assert.match(
    appSource,
    /const requiredBlankSeries = isChairmanUnnumberedPrintKind\(printKind\)\s+\? ""/,
  );
});

test("LMK printing reads the selected blank series from shared state", () => {
  const printSource = sourceBetween(
    "const runChairmanPrint = async",
    "printButton.addEventListener",
  );
  assert.match(
    printSource,
    /chairmanPrintBlankState\.selectedSeries \|\| getChairmanBlankSeriesForPrintKind\(printKind\)/,
  );
  assert.doesNotMatch(printSource, /\bselectedBlankSeries\b/);
});
