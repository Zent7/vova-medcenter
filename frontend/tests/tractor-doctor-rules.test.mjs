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

const context = vm.createContext({
  doctorRoles: [],
  getClientSexKey: () => "",
  isChairmanMarkedService: () => false,
});

vm.runInContext(
  [
    sourceBetween("const DRIVER_SERVICE_LEGACY_IDS", "const GIMS_SERVICE_LEGACY_IDS"),
    sourceBetween("const DRIVER_BASE_CATEGORIES", "const OPERATOR_SERVICE_PRIORITY_BY_LEGACY_ID"),
    sourceBetween("function isDriverService", "function isGimsService"),
    sourceBetween("const DRIVER_CATEGORY_ALIASES", "const DRIVER_INDICATION_FIELD_TO_LABEL"),
    sourceBetween("function getDoctorRoleCodeById", "function isDoctorRoleVisibleForClient"),
    "this.normalize = normalizeDriverCategories;",
    "this.rolesForService = getDoctorRoleCodeSetFromService;",
    "this.servicePrice = getVisitDriverServicePrice;",
  ].join("\n"),
  context,
);

const DRIVER_SERVICE = { legacySourceId: 8, name: "Водительская справка" };
const TRACTOR_SERVICE = { legacySourceId: 7, name: "Справка 071у" };
const BASE_ROLES = ["chairman", "ophthalmologist", "therapist"];
const ADVANCED_ROLES = ["chairman", "neurologist", "ophthalmologist", "otolaryngologist", "therapist"];

function normalize(categories) {
  return [...context.normalize(categories)];
}

function rolesFor(service, categories) {
  return [...context.rolesForService(service, { categories })].sort();
}

test("категории А и В назначают на тракторную только терапевта и офтальмолога", () => {
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, ["A", "B"]), BASE_ROLES);
});

test("категории С и D добавляют на тракторную невролога и отоларинголога", () => {
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, ["A", "B", "C", "D"]), ADVANCED_ROLES);
});

test("водительская справка по-прежнему считает врачей по категориям", () => {
  assert.deepEqual(rolesFor(DRIVER_SERVICE, ["A", "B"]), BASE_ROLES);
  assert.deepEqual(rolesFor(DRIVER_SERVICE, ["B", "C"]), ADVANCED_ROLES);
});

test("категории, набранные кириллицей, читаются как латинские", () => {
  assert.deepEqual(normalize("А, Б"), ["A", "B"]);
  assert.deepEqual(normalize("А, В"), ["A", "B"]);
  assert.deepEqual(normalize("А, В, С, Д"), ["A", "B", "C", "D"]);
  assert.deepEqual(normalize("ВЕ"), ["BE"]);
});

test("кириллические категории назначают тех же врачей, что и латинские", () => {
  assert.deepEqual(rolesFor(DRIVER_SERVICE, "А, Б"), BASE_ROLES);
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, "А, Б"), BASE_ROLES);
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, "А, В, С, Д"), ADVANCED_ROLES);
});

test("цена тракторной справки не пересчитывается по водительским категориям", () => {
  assert.equal(context.servicePrice({ ...TRACTOR_SERVICE, price: 2200 }, ["A", "B"]), 2200);
  assert.equal(context.servicePrice({ ...TRACTOR_SERVICE, price: 2200 }, ["A", "B", "C", "D"]), 2200);
  assert.equal(context.servicePrice(DRIVER_SERVICE, ["A", "B"]), 3500);
  assert.equal(context.servicePrice(DRIVER_SERVICE, ["A", "B", "C"]), 4000);
});

test("регистр категорий не меняет состав врачей", () => {
  assert.deepEqual(normalize("a, b"), ["A", "B"]);
  assert.deepEqual(normalize(["tm", "tb"]), ["Tm", "Tb"]);
});
