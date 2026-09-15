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
  getServicesForVisit: (visit) => visit.services,
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
    sourceBetween("function getCertificateExcludedDoctorRoles", "function mapApiService"),
    "this.excluded = getCertificateExcludedDoctorRoles;",
    "this.mark = buildDoctorMark;",
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

for (const service of [DRIVER_SERVICE, TRACTOR_SERVICE]) {
  test(`${service.name}: old completed neurologist and ENT do not mark an AB visit`, () => {
    const required = new Set(rolesFor(service, ["A", "B"]));
    const excluded = context.excluded({services: [service]}, required);
    const completed = new Set(ADVANCED_ROLES);
    for (const role of ["neurologist", "otolaryngologist"]) {
      assert.equal(context.mark(role, required, completed, excluded, completed).value, "");
    }
    for (const role of BASE_ROLES) assert.equal(context.mark(role, required, completed, excluded, completed).value, "✓");
    assert.equal(completed.size, 5, "saved examinations are preserved");
  });
  test(`${service.name}: CD and additional services retain required doctors`, () => {
    const required = new Set(ADVANCED_ROLES);
    assert.equal(context.excluded({services: [service]}, required).size, 0);
    assert.deepEqual(rolesFor(service, ["B", "BE"]), BASE_ROLES);
  });
}
test("other services retain existing examinations", () => {
  assert.equal(context.excluded({services: [{name: "Other"}]}, new Set()).size, 0);
});
