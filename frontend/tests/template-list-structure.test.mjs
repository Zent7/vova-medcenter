import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolve } from "node:path";

const appSource = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");
const catalogSource = readFileSync(
  resolve(import.meta.dirname, "../../backend/app/services/template_catalog.py"),
  "utf8",
);

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

function serviceListNames() {
  const block = catalogSource.slice(
    catalogSource.indexOf("SERVICE_LIST_TEMPLATE_ORDER"),
    catalogSource.indexOf("EXTRA_TEMPLATE_ORDER"),
  );
  return [...block.matchAll(/\("([^"]+)",\s*"([^"]+)"\),/g)].map(([, fileName, name]) => ({ fileName, name }));
}

test("the templates page lists the customer blanks and the contract", () => {
  const templatePage = sourceBetween("function renderTemplatesPage", "function renderWorkflowLoadState");
  assert.match(templatePage, /template\.listed_on_templates_page !== false/);
  assert.match(catalogSource, /TEMPLATES_PAGE_EXTRA_FILE_NAMES = frozenset\(\{"Договор_шаблон_2\.docx"\}\)/);
});

test("the customer service list keeps its order and wording", () => {
  const expected = [
    "Проф",
    "Проф с выпиской",
    "ЛМК справка",
    "ЛМК-Н, ЛМК-ПР",
    "амб карта",
    "бассейн",
    "спорт",
    "002 (чод)",
    "гимс",
    "071у Лицевая",
    "071у оборотная",
    "ВУ (водительская) лицевая",
    "ВУ (водительская) оборотная",
    "086у (Ж)",
    "086у (М)",
    "ГС",
    "ГТ",
    "072 у СКК",
    "070у",
    "082у",
    "342н псих осв",
    "095у",
  ];
  assert.deepEqual(serviceListNames().map((item) => item.name), expected);
});

test("the 29н conclusion prints from the customer's own sheet", () => {
  const entries = serviceListNames();
  assert.equal(entries[0].fileName, "ПРОФОСМОТР 29Н.xls");
  assert.match(appSource, /normalizedType === "prof"\) return findNewXls\(\["профосмотр 29н"\]\)/);
  assert.doesNotMatch(appSource, /заключение29н/);
  assert.doesNotMatch(appSource, /профосмотрвыписка/);
});
