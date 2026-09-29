import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const modalSource = readFileSync(resolve(testDir, "../public/demo/client-modal.js"), "utf8");
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const cases = JSON.parse(readFileSync(resolve(testDir, "../../backend/tests/fixtures/address_cases.json"), "utf8"));

function sourceBetween(startMarker, endMarker) {
  const start = modalSource.indexOf(startMarker);
  const end = modalSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return modalSource.slice(start, end);
}

const context = vm.createContext({});
vm.runInContext(
  [
    'const CLIENT_DEFAULT_COUNTRY = "Россия";',
    sourceBetween("const CLIENT_STREET_TYPE_PATTERN", "function getClientAddressSuggestionsFromClients"),
    "this.parse = parseClientAddressSuggestion;",
    "this.splitStreet = splitClientStreetType;",
    "this.composeStreet = composeClientStreet;",
    "this.marker = withClientAddressMarker;",
    "this.streetTypes = CLIENT_STREET_TYPE_OPTIONS;",
  ].join("\n"),
  context,
);

// Формат объекта, который читает форма карточки клиента.
const toFormShape = (expected) => ({
  subject: expected.subject,
  district: expected.district,
  city: expected.city,
  street: expected.street,
  house: expected.house,
  building: expected.body,
  flat: expected.apartment,
});
const pick = (parsed) => ({
  subject: parsed.subject,
  district: parsed.district,
  city: parsed.city,
  street: parsed.street,
  house: parsed.house,
  building: parsed.building,
  flat: parsed.flat,
});

test("карточка клиента разбирает адрес так же, как печать (общий список случаев)", () => {
  assert.ok(cases.length >= 10);
  for (const item of cases) {
    assert.deepEqual(pick(context.parse(item.address)), toFormShape(item.expected), item.name);
  }
});

test("страна остаётся страной, а без неё подставляется Россия", () => {
  assert.equal(context.parse("Россия, Москва, ул. Тверская, д. 1").country, "Россия");
  assert.equal(context.parse("г. Москва, ул. Тверская, д. 1").country, "Россия");
});

test("тип улицы отделяется от названия только если он есть в списке", () => {
  assert.deepEqual({ ...context.splitStreet("пр. Невский") }, { type: "пр.", name: "Невский" });
  assert.deepEqual({ ...context.splitStreet("бул. Авиаторов") }, { type: "бул.", name: "Авиаторов" });
  assert.deepEqual({ ...context.splitStreet("проезд Кирова") }, { type: "проезд", name: "Кирова" });
  assert.deepEqual({ ...context.splitStreet("Невский проспект") }, { type: "", name: "Невский проспект" });
  assert.deepEqual({ ...context.splitStreet("Ленина") }, { type: "", name: "Ленина" });
  assert.deepEqual({ ...context.splitStreet("ул.") }, { type: "", name: "ул." });
});

test("выбранный тип ставится перед названием и не задваивается", () => {
  assert.equal(context.composeStreet("пр.", "Невский"), "пр. Невский");
  assert.equal(context.composeStreet("", "Невский"), "Невский");
  assert.equal(context.composeStreet("ул.", ""), "");
  assert.equal(context.composeStreet("ул.", "ул. Ленина"), "ул. Ленина");
  assert.equal(context.composeStreet("пр.", "Невский проспект"), "Невский проспект");
});

test("номера получают приставки один раз", () => {
  assert.equal(context.marker("10", "д.", "house"), "д. 10");
  assert.equal(context.marker("д. 10", "д.", "house"), "д. 10");
  assert.equal(context.marker("2", "корп.", "body"), "корп. 2");
  assert.equal(context.marker("5", "кв.", "apartment"), "кв. 5");
  assert.equal(context.marker("  ", "кв.", "apartment"), "");
});

test("все типы улиц из списка карточки узнаёт разбор адреса", () => {
  for (const [value] of context.streetTypes) {
    const parsed = context.parse(`Россия, Ленинградская область, Всеволожский район, Мурино, ${value} Кирова, д. 10`);
    assert.equal(parsed.street, `${value} Кирова`, value);
    assert.equal(parsed.house, "10", value);
    assert.equal(parsed.city, "Мурино", value);
  }
});

test("адрес, собранный карточкой, разбирается обратно без сдвига при любых пустых частях", () => {
  const regions = [
    { subject: "Санкт-Петербург", city: "Санкт-Петербург", districts: [""] },
    { subject: "Ленинградская область", city: "Мурино", districts: ["", "Всеволожский район"] },
  ];
  let checked = 0;
  for (const region of regions) {
    for (const district of region.districts) {
      for (const streetType of ["", "пр.", "проезд"]) {
        for (const building of ["", "2"]) {
          for (const flat of ["", "5"]) {
            const street = context.composeStreet(streetType, "Невский");
            const text = [
              "Россия",
              region.subject,
              district,
              region.city,
              street,
              context.marker("10", "д.", "house"),
              context.marker(building, "корп.", "body"),
              context.marker(flat, "кв.", "apartment"),
            ]
              .filter(Boolean)
              .join(", ");
            const parsed = context.parse(text);
            const label = `${text}`;
            assert.equal(parsed.subject, region.subject, label);
            assert.equal(parsed.district, district, label);
            assert.equal(parsed.city, region.city, label);
            assert.deepEqual({ ...context.splitStreet(parsed.street) }, { type: streetType, name: "Невский" }, label);
            assert.equal(parsed.house, "10", label);
            assert.equal(parsed.building, building, label);
            assert.equal(parsed.flat, flat, label);
            checked += 1;
          }
        }
      }
    }
  }
  assert.equal(checked, 36);
});

test("карточка клиента собирает адрес с типом улицы и приставками", () => {
  assert.match(modalSource, /const streetValue = composeClientStreet\(formData\.get\("streetType"\), formData\.get\("street"\)\);/);
  assert.match(modalSource, /withClientAddressMarker\(formData\.get\("house"\), "д\.", "house"\)/);
  assert.match(modalSource, /withClientAddressMarker\(formData\.get\("building"\), "корп\.", "body"\)/);
  assert.match(modalSource, /withClientAddressMarker\(formData\.get\("flat"\), "кв\.", "apartment"\)/);
  assert.match(modalSource, /<select name="streetType">/);
  assert.match(modalSource, /<span>Тип улицы<\/span>\s*<select name="streetType">/);
});

test("автозаполнение по городу не стирает район и регион, набранные руками", () => {
  assert.match(modalSource, /if \(String\(input\.value \|\| ""\)\.trim\(\) && input\.dataset\.autofilled !== "true"\) return;/);
});

test("амбулаторный лист разбирает адрес со страной тем же кодом", () => {
  assert.match(appSource, /window\.parseClientAddressSuggestion\?\.\(source\)/);
});
