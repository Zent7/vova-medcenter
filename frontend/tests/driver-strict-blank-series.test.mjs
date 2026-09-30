import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
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

function loadSeriesRules() {
  const source = [
    sourceBetween("const CHAIRMAN_AUTO_CREATE_BLANK_SERIES", "// Справка ЛМК печатается"),
    sourceBetween("function canAutoCreateChairmanBlankSeries", "const CHAIRMAN_NUMBERED_CERTIFICATE_SERIES"),
    sourceBetween("function normalizeBlankSeries", "// Серия 086у подписывается"),
    sourceBetween("const PREENTERED_BLANK_SERIES =", "const CERTIFICATE_PRINT_TYPE_LABELS"),
    sourceBetween("const BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE", "const SERVICE_SERIES_OVERRIDES"),
    sourceBetween("function getDriverPrintCertificateType", "function getBlankTypeForCertificatePrintType"),
    sourceBetween("function isPreenteredBlankSeries", "function buildServiceSeriesAbbreviation"),
  ].join("\n");
  return new Function(`${source}\nreturn { isPreenteredBlankFlow, isStrictDriverBlankSeries, isStockNumberedFlow };`)();
}

const { isPreenteredBlankFlow, isStrictDriverBlankSeries, isStockNumberedFlow } = loadSeriesRules();
const DRIVER = "driver_medical_certificate";

test("a driver series that names no certificate is a strict blank", () => {
  for (const series of ["41", "40", "77", " 41 "]) {
    assert.equal(isStrictDriverBlankSeries(series, DRIVER), true, series);
  }
});

test("certificate series keep their automatic numbers", () => {
  for (const series of ["ГТО", "095У", "095у", "086у (М)", "СПОРТ", "БАСС", "29Н", "ДРАГ", "СЭНД", "13082", "ЭКГ"]) {
    assert.equal(isStrictDriverBlankSeries(series, DRIVER), false, series);
  }
});

test("only the driver blank type is strict", () => {
  assert.equal(isStrictDriverBlankSeries("41", "gims_medical_certificate"), false);
  assert.equal(isStrictDriverBlankSeries("41", "lmk_medical_certificate"), false);
  assert.equal(isStrictDriverBlankSeries("", DRIVER), false);
});

test("a strict driver series is taken from the entered batches and never auto-numbered", () => {
  assert.equal(isStockNumberedFlow("41", DRIVER), true);
  assert.equal(isStockNumberedFlow("40", DRIVER), true);
  assert.equal(isStockNumberedFlow("ГМ", DRIVER), true);
  assert.equal(isStockNumberedFlow("095У", DRIVER), false);
  assert.equal(isStockNumberedFlow("ГТО", DRIVER), false);
});

test("GIMS and pre-entered series stay stock-numbered, and isPreenteredBlankFlow is unchanged", () => {
  assert.equal(isStockNumberedFlow("ГМ", "gims_medical_certificate"), true);
  assert.equal(isPreenteredBlankFlow("41", DRIVER), false);
  assert.equal(isPreenteredBlankFlow("40", DRIVER), true);
});

test("driver print window asks the server for stock-only blanks on a strict series", () => {
  const printFlow = sourceBetween("async function openDriverPrintFlow", "window.openDriverPrintFlow = openDriverPrintFlow");

  assert.match(printFlow, /isOrdinaryDriverFlow && blankType === BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE\) query\.set\("strict_only", "true"\)/);
  assert.match(printFlow, /isStrictDriverBlankSeries\(requestedSeries, flowState\.blankType\)/);
  assert.match(printFlow, /isStrictDriverBlankSeries\(flowState\.selectedSeries, flowState\.blankType\)/);
});
