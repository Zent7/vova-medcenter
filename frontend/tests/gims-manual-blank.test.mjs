import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { resolve } from "node:path";

const appSource = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

test("only GIMS uses manual typographic blank selection", () => {
  const helpers = sourceBetween(
    "function isManualGimsBlankSelection",
    "const SERVICE_SERIES_OVERRIDES",
  );
  const context = vm.createContext({
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE: "gims_medical_certificate",
  });
  vm.runInContext(`${helpers}; this.isManual = isManualGimsBlankSelection;`, context);

  assert.equal(context.isManual("gims_medical_certificate", ""), true);
  assert.equal(context.isManual("driver_medical_certificate", "gims"), true);
  assert.equal(context.isManual("driver_medical_certificate", "071"), false);
});

test("GIMS print flow checks the entered number instead of asking for the next one", () => {
  const printFlow = sourceBetween(
    "async function openDriverPrintFlow",
    "window.openDriverPrintFlow = openDriverPrintFlow",
  );

  assert.match(printFlow, /manualGimsBlank \? "Проверить номер" : "Найти номер"/);
  assert.match(printFlow, /manualGimsBlank \? "" : "readonly"/);
  assert.match(printFlow, /\/blanks\/forms\/exact\?/);
  assert.match(printFlow, /Введите серию и напечатанный на бланке номер/);
  assert.match(printFlow, /Проверьте номер или добавьте его диапазон/);
  assert.match(printFlow, /Введите номер следующего бумажного бланка/);
});
