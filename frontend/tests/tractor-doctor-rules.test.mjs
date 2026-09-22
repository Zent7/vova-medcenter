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
    "this.normalizeTractor = normalizeTractorCategories;",
    "this.rolesForService = getDoctorRoleCodeSetFromService;",
    "this.servicePrice = getVisitDriverServicePrice;",
    "this.categoryOptions = getCertificateCategoryOptions;",
    "this.defaultCategories = getCertificateDefaultCategories;",
    "this.certificateRoles = getCertificateRoleCodes;",
  ].join("\n"),
  context,
);

const DRIVER_SERVICE = { legacySourceId: 8, name: "Водительская справка" };
const TRACTOR_SERVICE = { legacySourceId: 7, name: "Справка 071у" };
const BASE_ROLES = ["chairman", "ophthalmologist", "therapist"];
const ADVANCED_ROLES = ["chairman", "neurologist", "ophthalmologist", "otolaryngologist", "therapist"];
const TRACTOR_CATEGORIES = ["AI", "AII", "AIII", "AIV", "B", "C", "D", "E", "F"];
const TRACTOR_BASE_ROLES = ["chairman", "ophthalmologist", "psychiatrist", "psychiatrist-narcologist", "therapist"];
const TRACTOR_ADVANCED_ROLES = [
  "chairman",
  "neurologist",
  "ophthalmologist",
  "otolaryngologist",
  "psychiatrist",
  "psychiatrist-narcologist",
  "therapist",
];

function normalize(categories) {
  return [...context.normalize(categories)];
}

function normalizeTractor(categories) {
  return [...context.normalizeTractor(categories)];
}

function rolesFor(service, detailOrCategories) {
  const detail = Array.isArray(detailOrCategories) || typeof detailOrCategories === "string"
    ? { categories: detailOrCategories }
    : detailOrCategories;
  return [...context.rolesForService(service, detail)].sort();
}

test("у тракторной свои категории, а не категории ВУ", () => {
  assert.deepEqual([...context.categoryOptions(TRACTOR_SERVICE)], TRACTOR_CATEGORIES);
  assert.deepEqual([...context.categoryOptions(DRIVER_SERVICE)], [
    "A", "B", "C", "D", "BE", "CE", "DE", "Tm", "Tb", "M", "A1", "B1", "C1", "D1", "C1E", "D1E",
  ]);
});

test("при выборе 071у отмечены все тракторные категории", () => {
  assert.deepEqual([...context.defaultCategories(TRACTOR_SERVICE)], TRACTOR_CATEGORIES);
  assert.deepEqual([...context.defaultCategories(DRIVER_SERVICE)], ["B"]);
});

test("тракторная без выбранных категорий зовёт всех шестерых врачей", () => {
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, {}), TRACTOR_ADVANCED_ROLES);
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, TRACTOR_CATEGORIES), TRACTOR_ADVANCED_ROLES);
});

test("базовые тракторные категории зовут терапевта, офтальмолога, психиатра и нарколога", () => {
  for (const categories of [["AI"], ["AII"], ["AIII"], ["AIV"], ["B"], ["F"], ["AI", "AII", "AIII", "AIV", "B", "F"]]) {
    assert.deepEqual(rolesFor(TRACTOR_SERVICE, categories), TRACTOR_BASE_ROLES, categories.join(","));
  }
});

test("категории C, D и E добавляют на тракторную невролога и отоларинголога", () => {
  for (const categories of [["C"], ["D"], ["E"], ["B", "E"], ["AI", "F", "C"]]) {
    assert.deepEqual(rolesFor(TRACTOR_SERVICE, categories), TRACTOR_ADVANCED_ROLES, categories.join(","));
  }
});

test("снятые все категории оставляют на тракторной только председателя, как у водительской", () => {
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, []), ["chairman"]);
  assert.deepEqual(rolesFor(DRIVER_SERVICE, []), ["chairman"]);
});

test("тракторные категории читаются из кириллицы и арабских цифр", () => {
  assert.deepEqual(normalizeTractor("В, С, Д, Е, Ф"), ["B", "C", "D", "E", "F"]);
  assert.deepEqual(normalizeTractor("А1, A2, АIII, aiv"), ["AI", "AII", "AIII", "AIV"]);
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, "А1, В"), TRACTOR_BASE_ROLES);
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, "В, С"), TRACTOR_ADVANCED_ROLES);
});

test("категории ВУ на тракторной не придумывают тракторных", () => {
  assert.deepEqual(normalizeTractor(["M", "BE", "CE", "Tm", "Tb", "C1E"]), []);
  // Обращение, заведённое до тракторных категорий, хранило ВУ: B, C и D
  // совпадают, поэтому врачи на C и D остаются.
  assert.deepEqual(normalizeTractor(["B", "M", "B1"]), ["B"]);
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, ["B", "M", "B1"]), TRACTOR_BASE_ROLES);
  assert.deepEqual(rolesFor(TRACTOR_SERVICE, ["A", "B", "C", "D", "M", "A1", "B1", "C1", "D1"]), TRACTOR_ADVANCED_ROLES);
});

test("панель показывает для каждой справки её врачей", () => {
  assert.deepEqual([...context.certificateRoles(TRACTOR_SERVICE, ["B"])].sort(), TRACTOR_BASE_ROLES);
  assert.deepEqual([...context.certificateRoles(DRIVER_SERVICE, ["B"])].sort(), BASE_ROLES);
});

test("водительская справка по-прежнему считает врачей по категориям", () => {
  assert.deepEqual(rolesFor(DRIVER_SERVICE, ["A", "B"]), BASE_ROLES);
  assert.deepEqual(rolesFor(DRIVER_SERVICE, ["B", "C"]), ADVANCED_ROLES);
  assert.deepEqual(rolesFor(DRIVER_SERVICE, {}), BASE_ROLES);
});

test("категории, набранные кириллицей, читаются как латинские", () => {
  assert.deepEqual(normalize("А, Б"), ["A", "B", "M", "A1", "B1"]);
  assert.deepEqual(normalize("А, В"), ["A", "B", "M", "A1", "B1"]);
  assert.deepEqual(normalize("А, В, С, Д"), ["A", "B", "C", "D", "M", "A1", "B1", "C1", "D1"]);
  assert.deepEqual(normalize("ВЕ"), ["BE"]);
});

test("основная категория открывает подкатегорию и M", () => {
  assert.deepEqual(normalize(["B"]), ["B", "M", "B1"]);
  assert.deepEqual(normalize(["A"]), ["A", "M", "A1"]);
  assert.deepEqual(normalize(["C"]), ["C", "M", "C1"]);
  assert.deepEqual(normalize(["D"]), ["D", "M", "D1"]);
  // Прицепные и трамвай/троллейбус ничего не открывают.
  assert.deepEqual(normalize(["BE"]), ["BE"]);
  assert.deepEqual(normalize(["Tm"]), ["Tm"]);
});

test("кириллические категории назначают тех же врачей, что и латинские", () => {
  assert.deepEqual(rolesFor(DRIVER_SERVICE, "А, Б"), BASE_ROLES);
  assert.deepEqual(rolesFor(DRIVER_SERVICE, "А, В, С, Д"), ADVANCED_ROLES);
});

test("цена тракторной справки не пересчитывается по категориям", () => {
  assert.equal(context.servicePrice({ ...TRACTOR_SERVICE, price: 2200 }, ["B"]), 2200);
  assert.equal(context.servicePrice({ ...TRACTOR_SERVICE, price: 2200 }, TRACTOR_CATEGORIES), 2200);
  assert.equal(context.servicePrice(DRIVER_SERVICE, ["A", "B"]), 3500);
  assert.equal(context.servicePrice(DRIVER_SERVICE, ["A", "B", "C"]), 4000);
});

test("регистр категорий не меняет состав врачей", () => {
  assert.deepEqual(normalize("a, b"), ["A", "B", "M", "A1", "B1"]);
  assert.deepEqual(normalize(["tm", "tb"]), ["Tm", "Tb"]);
  assert.deepEqual(normalizeTractor("ai, b, f"), ["AI", "B", "F"]);
});

for (const [service, baseCategories, baseRoles] of [
  [DRIVER_SERVICE, ["A", "B"], BASE_ROLES],
  [TRACTOR_SERVICE, ["AI", "B", "F"], TRACTOR_BASE_ROLES],
]) {
  test(`${service.name}: old completed neurologist and ENT do not mark a base-category visit`, () => {
    const required = new Set(rolesFor(service, baseCategories));
    const excluded = context.excluded({services: [service]}, required);
    const completed = new Set([...ADVANCED_ROLES, ...TRACTOR_ADVANCED_ROLES]);
    for (const role of ["neurologist", "otolaryngologist"]) {
      assert.equal(context.mark(role, required, completed, excluded, completed).value, "");
    }
    for (const role of baseRoles) assert.equal(context.mark(role, required, completed, excluded, completed).value, "✓");
    assert.equal(completed.size, 7, "saved examinations are preserved");
  });
  test(`${service.name}: extended categories and additional services retain required doctors`, () => {
    const required = new Set(service === TRACTOR_SERVICE ? TRACTOR_ADVANCED_ROLES : ADVANCED_ROLES);
    assert.equal(context.excluded({services: [service]}, required).size, 0);
  });
}
test("водительская B и BE не зовёт невролога и ЛОРа", () => {
  assert.deepEqual(rolesFor(DRIVER_SERVICE, ["B", "BE"]), BASE_ROLES);
});
test("other services retain existing examinations", () => {
  assert.equal(context.excluded({services: [{name: "Other"}]}, new Set()).size, 0);
});
