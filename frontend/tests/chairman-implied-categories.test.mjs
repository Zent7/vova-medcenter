import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");

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
    sourceBetween("const CHAIRMAN_DRIVER_CATEGORY_FIELD_KEYS", "function collectChairmanDriverIndications"),
    "this.implied = getChairmanImpliedCategoryFieldKeys;",
    "this.normalize = normalizeDriverCategories;",
    "this.fieldKeys = CHAIRMAN_DRIVER_CATEGORY_FIELD_KEYS;",
  ].join("\n"),
  context,
);

test("отметка категории в карточке председателя открывает подкатегорию и M", () => {
  assert.deepEqual([...context.implied({ categoryA: true })].sort(), ["categoryA1", "categoryM"]);
  assert.deepEqual([...context.implied({ categoryB: true })].sort(), ["categoryB1", "categoryM"]);
  assert.deepEqual([...context.implied({ categoryC: true })].sort(), ["categoryC1", "categoryM"]);
  assert.deepEqual([...context.implied({ categoryD: true })].sort(), ["categoryD1", "categoryM"]);
});

test("несколько категорий дают каждую подкатегорию один раз, M — один раз", () => {
  const keys = [...context.implied({ categoryB: true, categoryC: true })].sort();
  assert.deepEqual(keys, ["categoryB1", "categoryC1", "categoryM"]);
});

test("без основной категории ничего не открывается", () => {
  assert.deepEqual([...context.implied({})], []);
  assert.deepEqual([...context.implied({ categoryM: true, categoryB1: true, categoryBE: true })], []);
});

test("правило карточки председателя совпадает с правилом карточки клиента", () => {
  const fieldToCategory = Object.fromEntries(Object.entries(context.fieldKeys).map(([category, field]) => [field, category]));
  for (const category of ["A", "B", "C", "D"]) {
    const fromClientCard = [...context.normalize([category])].filter((item) => item !== category).sort();
    const fromChairmanCard = [...context.implied({ [context.fieldKeys[category]]: true })].map((field) => fieldToCategory[field]).sort();
    assert.deepEqual(fromChairmanCard, fromClientCard, category);
  }
});

test("окно председателя рисует открытые подкатегории отмеченными и ставит их при клике", () => {
  assert.match(modalSource, /window\.getChairmanImpliedCategoryFieldKeys\?\.\(fields\)/);
  for (const name of ["categoryA", "categoryB", "categoryC", "categoryD", "categoryM", "categoryA1", "categoryB1", "categoryC1", "categoryD1"]) {
    assert.ok(modalSource.includes(`categoryChecked("${name}")`), `${name} must be drawn through categoryChecked`);
  }
  assert.match(modalSource, /\["categoryA", "categoryB", "categoryC", "categoryD"\]\.forEach\(\(name\) => \{/);
  assert.match(modalSource, /impliedInput\.dispatchEvent\(new Event\("change", \{ bubbles: true \}\)\)/);
});
