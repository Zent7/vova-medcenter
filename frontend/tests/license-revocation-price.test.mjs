import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const modalSource = readFileSync(resolve(testDir, "../public/demo/client-modal.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = modalSource.indexOf(startMarker);
  const end = modalSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return modalSource.slice(start, end);
}

// Цена водительской комиссии при галочке «Лишение прав»: 1500 ₽ вместо цены категорий.
function loadDefaultUnitPrice({ revoked, categories }) {
  const source = sourceBetween("// Лишение прав:", "function syncClientPaymentRowsFromDom");
  const actionModalContent = {
    querySelector: (selector) =>
      selector === 'input[name="clientDriverLicenseRevoked"]' ? { checked: revoked } : null,
  };
  return new Function(
    "actionModalContent",
    "isDriverService",
    "normalizeDriverCategories",
    "getClientDriverCategoriesFromForm",
    "getDriverCategoryPrice",
    `${source}\nreturn getDefaultServiceUnitPrice;`,
  )(
    actionModalContent,
    () => true,
    (value) => value,
    () => categories,
    (value) => (value.length ? 4000 : 0),
  );
}

test("при лишении прав водительская комиссия стоит 1500 вместо цены категорий", () => {
  const getPrice = loadDefaultUnitPrice({ revoked: true, categories: ["A", "B", "C"] });
  assert.equal(getPrice({ name: "Водительская справка" }), 1500);
});

test("без лишения прав цена считается по категориям", () => {
  const getPrice = loadDefaultUnitPrice({ revoked: false, categories: ["B"] });
  assert.equal(getPrice({ name: "Водительская справка" }), 4000);
  const noCategories = loadDefaultUnitPrice({ revoked: false, categories: [] });
  assert.equal(noCategories({ name: "Водительская справка" }), 0);
});
