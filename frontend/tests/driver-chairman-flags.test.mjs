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

const context = vm.createContext({});
vm.runInContext(
  [
    sourceBetween("const DRIVER_CATEGORY_OPTIONS =", "const DRIVER_CATEGORY_ADVANCED_ROLES"),
    sourceBetween("const DRIVER_CATEGORY_ALIASES", "function getDriverCategoryPrice"),
    sourceBetween("const DRIVER_INDICATION_FIELD_TO_LABEL", "const DRIVER_INDICATION_LABEL_TO_FIELD"),
    sourceBetween("const DRIVER_LIMITATION_FIELD_TO_LABEL", "const DRIVER_LIMITATION_LABEL_TO_FIELD"),
    sourceBetween("const DRIVER_LIMITATION_FIELD_ALIASES", "function collectChairmanDriverCategories"),
    sourceBetween("function applyDriverSelectionsToChairmanFields", "function getDriverDetailFromVisit"),
    "this.apply = applyDriverSelectionsToChairmanFields;",
  ].join("\n"),
  context,
);

const GLASSES = "ТС мед. изд. для коррекции зрения";
const LIMIT_BBE = "Категории B, BE, B1";

test("галочка председателя не стирается пустой карточкой клиента", () => {
  const fields = context.apply(
    { indicationGlasses: true, restrictionBBE: true, indicationManual: true },
    { categories: ["B"], indications: [], limitations: [] },
  );

  assert.equal(fields.indicationGlasses, true);
  assert.equal(fields.restrictionBBE, true);
  assert.equal(fields.indicationManual, true);
  assert.equal(fields.hasGlasses, true);
});

test("отметки карточки клиента добавляются к отметкам председателя", () => {
  const fields = context.apply(
    { indicationGlasses: true },
    { categories: ["B"], indications: [GLASSES], limitations: [LIMIT_BBE] },
  );

  assert.equal(fields.indicationGlasses, true);
  assert.equal(fields.restrictionBBE, true);
});

test("неотмеченное нигде показание остаётся снятым", () => {
  const fields = context.apply({}, { categories: ["B"], indications: [], limitations: [] });

  assert.equal(fields.indicationGlasses, false);
  assert.equal(fields.indicationManual, false);
  assert.equal(fields.restrictionAM, false);
  assert.equal(fields.restrictionCCE, false);
});

test("категории карточки клиента открывают подкатегорию и M", () => {
  const fields = context.apply({}, { categories: ["B"], indications: [], limitations: [] });

  assert.equal(fields.categoryB, true);
  assert.equal(fields.categoryB1, true);
  assert.equal(fields.categoryM, true);
  assert.equal(fields.categoryA, false);
  assert.equal(fields.driverCategories, "B, M, B1");
});
