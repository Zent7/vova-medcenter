import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

const approvedSeries = [
  "070У",
  "071У",
  "072У",
  "082У",
  "086У",
  "095У",
  "001 ГСУ",
  "989Н",
  "342Н",
  "ГТО",
  "БАСС",
  "СПОРТ",
  "ЭКГ",
  "ЭКГР",
  "ЭКГН",
  "ЛМК",
  "ГИМС",
  "4026",
  "29Н",
  "ДРАГ",
  "МОРСКАЯ",
  "13082",
  "13098",
];

test("certificate picker exposes only the approved series", () => {
  const optionsMatch = appSource.match(/const CERTIFICATE_PRINT_SERIES_OPTIONS = \[([\s\S]*?)\n\];/);
  assert.ok(optionsMatch, "certificate series options must be declared");

  const actualSeries = [...optionsMatch[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual(actualSeries, approvedSeries);
});

test("certificate picker does not mix legacy, preentered, or service-derived suggestions", () => {
  const functionStart = appSource.indexOf("function getDriverPrintSeriesPickerOptions(");
  const functionEnd = appSource.indexOf("function closeDriverPrintSeriesPicker", functionStart);
  assert.ok(functionStart >= 0 && functionEnd > functionStart, "certificate picker option builder must be declared");

  const functionSource = appSource.slice(functionStart, functionEnd);
  assert.doesNotMatch(functionSource, /PREENTERED_BLANK_SERIES|getAutoServiceSeriesOptions|\"40\"/);
  assert.match(functionSource, /CERTIFICATE_PRINT_SERIES_OPTION_SET\.has/);
});
