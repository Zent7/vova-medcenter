import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const appSource = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

// Настоящие функции app.js с подставленным каталогом услуг: цена справки должна
// идти из «Услуг», а не из чисел, записанных в коде.
function loadDriverPrices(serverServices) {
  const context = vm.createContext({ data: { serverServices } });
  vm.runInContext(
    [
      sourceBetween("const DRIVER_SERVICE_LEGACY_IDS", "const GIMS_SERVICE_LEGACY_IDS"),
      sourceBetween("const DRIVER_BASE_CATEGORIES", "const OPERATOR_SERVICE_PRIORITY_BY_LEGACY_ID"),
      sourceBetween("function isDriverService", "function isGimsService"),
      sourceBetween("const DRIVER_CATEGORY_ALIASES", "const DRIVER_INDICATION_FIELD_TO_LABEL"),
      "this.categoryPrice = getDriverCategoryPrice;",
      "this.servicePrice = getVisitDriverServicePrice;",
    ].join("\n"),
    context,
  );
  return context;
}

const ADVANCED = { legacySourceId: 8, name: "Медицинская комиссия" };
const BASE = { legacySourceId: 29, name: "Медицинская комиссия" };

test("базовые категории берут цену услуги базовых категорий из каталога", () => {
  const prices = loadDriverPrices([
    { ...BASE, price: 3800 },
    { ...ADVANCED, price: 4500 },
  ]);
  assert.equal(prices.categoryPrice(["B"]), 3800);
  assert.equal(prices.categoryPrice(["A", "B", "M"]), 3800);
  assert.equal(prices.categoryPrice(["B", "C"]), 4500);
});

test("правка цены в «Услугах» сразу попадает в цену справки", () => {
  const services = [{ ...ADVANCED, price: 4000 }];
  const prices = loadDriverPrices(services);
  assert.equal(prices.servicePrice(ADVANCED, ["C"]), 4000);
  services[0].price = 4600;
  assert.equal(prices.servicePrice(ADVANCED, ["C"]), 4600);
});

test("без услуги в каталоге остаются прежние 3500 и 4000", () => {
  const prices = loadDriverPrices([]);
  assert.equal(prices.categoryPrice(["B"]), 3500);
  assert.equal(prices.categoryPrice(["B", "C"]), 4000);
  assert.equal(prices.categoryPrice([]), 0);
});
