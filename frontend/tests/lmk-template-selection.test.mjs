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

function createTemplatePicker(templates) {
  const pickerSource = sourceBetween(
    "function pickDocumentTemplate",
    "function getChairmanTemplatePrintType",
  );
  const context = vm.createContext({
    data: { documentTemplates: templates },
    repairDemoText: (value) => value,
  });
  vm.runInContext(`${pickerSource}; this.pickTemplate = pickDocumentTemplate;`, context);
  return context.pickTemplate;
}

test("LMK print buttons select the workbook and certificate templates", () => {
  const pickTemplate = createTemplatePicker([
    {
      id: 59,
      name: "ЛМК справка",
      code: "лмк_справка_шаблон-21",
      file_name: "ЛМК_справка_шаблон.docx",
      template_type: "docx",
    },
    {
      id: 60,
      name: "ЛМК",
      code: "лмк-20",
      file_name: "ЛМК.xls",
      template_type: "xls",
    },
  ]);

  assert.equal(pickTemplate("lmk_title")?.file_name, "ЛМК.xls");
  assert.equal(pickTemplate("lmk")?.file_name, "ЛМК_справка_шаблон.docx");
});

test("chairman LMK actions route to the matching template types", () => {
  const routingSource = sourceBetween(
    "function getChairmanTemplatePrintType",
    "function shouldOpenChairmanResultsPrintMenu",
  );

  assert.match(routingSource, /lmk_title: "lmk_title"/);
  assert.match(routingSource, /lmk_certificate: "lmk"/);
  assert.match(appSource, /\["lmk_title", "lmk"\]/);
});
