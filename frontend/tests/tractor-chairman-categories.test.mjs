import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");
const templatesSource = readFileSync(resolve(testDir, "../public/demo/doctor-templates.js"), "utf8");

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
    sourceBetween("const DRIVER_LIMITATION_FIELD_ALIASES", "function collectChairmanDriverIndications"),
    sourceBetween("function applyDriverSelectionsToChairmanFields", "function getDriverDetailFromVisit"),
    "this.apply = applyDriverSelectionsToChairmanFields;",
    "this.checks = getChairmanTractorCategoryChecks;",
    "this.restrictions = getChairmanTractorRestrictionChecks;",
  ].join("\n"),
  context,
);

const TRACTOR_CATEGORIES = ["AI", "AII", "AIII", "AIV", "B", "C", "D", "E", "F"];

function checked(fields) {
  return [...context.checks(fields)].filter((item) => item.checked).map((item) => item.category);
}

test("председатель тракторной видит категории тракториста-машиниста", () => {
  const checks = [...context.checks({})];
  assert.deepEqual(checks.map((item) => item.category), TRACTOR_CATEGORIES);
  assert.deepEqual(checks.map((item) => item.fieldKey), TRACTOR_CATEGORIES.map((category) => `tractorCategory${category}`));
});

test("категории карточки клиента переходят в тракторные галочки председателя", () => {
  assert.deepEqual(checked(context.apply({}, { categories: TRACTOR_CATEGORIES })), TRACTOR_CATEGORIES);
  const fields = context.apply({}, { categories: ["B", "E"] });
  assert.deepEqual(checked(fields), ["B", "E"]);
  assert.equal(fields.tractorCategoryAI, false);
  assert.equal(fields.tractorCategoryE, true);
});

test("без выбранных у клиента категорий галочки председателя не трогаются", () => {
  const fields = context.apply({ tractorCategoryB: true, tractorCategoryC: false }, { indications: [], limitations: [] });
  assert.equal(fields.tractorCategoryB, true);
  assert.equal(fields.tractorCategoryC, false);
});

test("водительские галочки председателя по-прежнему заполняются из ВУ", () => {
  const fields = context.apply({}, { categories: ["B"] });
  assert.equal(fields.categoryB, true);
  assert.equal(fields.categoryB1, true);
  assert.equal(fields.driverCategories, "B, M, B1");
});

test("снятая председателем тракторная категория остаётся снятой", () => {
  const fields = { tractorCategoryB: true, tractorCategoryC: false, tractorCategoryE: true };
  assert.deepEqual(checked(fields), ["B", "E"]);
});

test("старая карточка без тракторных галочек показывает B, C и D из водительских", () => {
  assert.deepEqual(checked({ categoryB: true, categoryC: true, categoryM: true, categoryB1: true }), ["B", "C"]);
  assert.deepEqual(checked({ categoryB: true }), ["B"]);
});

test("новая карточка председателя отмечает все тракторные категории", () => {
  for (const category of TRACTOR_CATEGORIES) {
    assert.ok(
      templatesSource.includes(`{ key: "tractorCategory${category}", label: "${category}", type: "checkbox", defaultValue: true }`),
      `tractorCategory${category} must be checked by default`,
    );
  }
});

test("окно председателя рисует тракторные галочки только для тракторной", () => {
  assert.match(modalSource, /chairmanType === "tractor"\s*\?\s*window\.getChairmanTractorCategoryChecks\?\.\(fields\)/);
});

test("председатель 071у отмечает ограничения по каждой тракторной категории", () => {
  const checks = [...context.restrictions({})];
  assert.deepEqual(checks.map((item) => item.category), TRACTOR_CATEGORIES);
  assert.deepEqual(checks.map((item) => item.fieldKey), TRACTOR_CATEGORIES.map((category) => `tractorRestriction${category}`));
  assert.deepEqual(checks.filter((item) => item.checked), []);

  const marked = [...context.restrictions({ tractorCategoryB: true, tractorRestrictionC: true, tractorRestrictionF: true })];
  assert.deepEqual(marked.filter((item) => item.checked).map((item) => item.category), ["C", "F"]);
});

test("новая карточка председателя не отмечает ограничений 071у", () => {
  for (const category of TRACTOR_CATEGORIES) {
    assert.ok(
      templatesSource.includes(`{ key: "tractorRestriction${category}", label: "${category}", type: "checkbox", defaultValue: false }`),
      `tractorRestriction${category} must be unchecked by default`,
    );
  }
});

test("окно председателя 071у показывает ограничения тракториста вместо ограничений ВУ", () => {
  assert.match(modalSource, /chairmanType === "tractor"\s*\?\s*renderTractorChecks\(tractorRestrictionChecks\)/);
});

test("в обращении с ВУ и 071у у председателя есть колонка ограничений 071у", () => {
  assert.match(modalSource, /chairmanType === "driver" && window\.chairmanExamHasTractorService\?\.\(exam\)/);
  assert.match(modalSource, /Ограничения 071у:<\/div>\s*\$\{renderTractorChecks\(tractorRestrictionChecks\)\}/);
});
