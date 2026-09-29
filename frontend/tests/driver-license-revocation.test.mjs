import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");
const stylesSource = readFileSync(resolve(testDir, "../public/demo/styles.css"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

function buildSyncContext({ formInfo, detail, visit = { id: "encounter-3", backendId: 3 } }) {
  const client = { id: 7, rawApiClient: { id: 7, last_name: "Иванов", first_name: "Иван" }, services: [] };
  const visitSyncs = [];
  const context = vm.createContext({
    data: { visits: [visit], medicalRecords: [] },
    getClientPool: () => [client],
    getChairmanFormInfo: () => formInfo,
    getDriverDetailFromVisit: () => detail,
    resolveAdmissionCategoryValue: () => "",
    parseRuDateToIso: () => "",
    apiRequest: async () => ({}),
    upsertClientInMemory: () => {},
    persistDemoState: () => {},
    syncVisitToBackend: async () => {
      visitSyncs.push(JSON.parse(JSON.stringify(detail)));
    },
  });
  vm.runInContext(
    [
      sourceBetween("const DRIVER_INDICATION_FIELD_TO_LABEL", "const DRIVER_INDICATION_LABEL_TO_FIELD"),
      sourceBetween("const DRIVER_LIMITATION_FIELD_TO_LABEL", "const DRIVER_LIMITATION_LABEL_TO_FIELD"),
      sourceBetween("const DRIVER_LIMITATION_FIELD_ALIASES", "function mergeDriverDetailFlagsIntoChairmanFields"),
      sourceBetween("function normalizeChairmanRecordValue", "function getCompletedChairmanExam"),
      sourceBetween("async function syncChairmanExamToClientAndMedicalRecord", "async function saveDoctorExam"),
      "this.sync = syncChairmanExamToClientAndMedicalRecord;",
    ].join("\n"),
    context,
  );
  const exam = (fields) => ({ id: "exam-1", clientId: 7, visitId: visit.id, doctorRoleId: "chairman", fields });
  return { context, exam, visitSyncs };
}

test("отметка «Лишение прав» председателя ВУ записывается в обращение", async () => {
  const detail = { categories: ["B"], licenseRevoked: false };
  const { context, exam, visitSyncs } = buildSyncContext({ formInfo: { type: "driver", printMode: "driver-flow" }, detail });

  await context.sync(exam({ licenseRevoked: true, categoryB: true }));

  assert.equal(detail.licenseRevoked, true);
  assert.equal(visitSyncs.length, 1);
  assert.equal(visitSyncs[0].licenseRevoked, true);
});

test("председатель может снять «Лишение прав», поставленное в карточке клиента", async () => {
  const detail = { licenseRevoked: true };
  const { context, exam } = buildSyncContext({ formInfo: { type: "driver", printMode: "driver-flow" }, detail });

  await context.sync(exam({ licenseRevoked: false, categoryB: true }));

  assert.equal(detail.licenseRevoked, false);
});

test("у председателя 071у отметка тоже уходит в обращение, а категории ВУ не трогаются", async () => {
  const detail = { categories: ["B", "C"], licenseRevoked: false };
  const { context, exam, visitSyncs } = buildSyncContext({ formInfo: { type: "tractor", printMode: "document" }, detail });

  await context.sync(exam({ licenseRevoked: true, tractorCategoryB: true }));

  assert.equal(detail.licenseRevoked, true);
  assert.deepEqual(detail.categories, ["B", "C"]);
  assert.equal(visitSyncs.length, 1);
});

test("карточки других справок обращение не трогают", async () => {
  const detail = { licenseRevoked: true };
  const { context, exam, visitSyncs } = buildSyncContext({ formInfo: { type: "lmk", printMode: "document" }, detail });

  await context.sync(exam({ licenseRevoked: false }));

  assert.equal(detail.licenseRevoked, true);
  assert.equal(visitSyncs.length, 0);
});

test("открытая карточка председателя берёт отметку из обращения", () => {
  const detail = {};
  const context = vm.createContext({ getDriverDetailFromVisit: () => detail });
  vm.runInContext(
    [
      sourceBetween("function carryLicenseRevocationFromVisit", "function getDoctorRoleCodeById"),
      "this.carry = carryLicenseRevocationFromVisit;",
    ].join("\n"),
    context,
  );
  const visit = { id: "encounter-3" };

  // в обращении отметки нет — карточку не трогаем
  const untouched = { categoryB: true };
  assert.equal(context.carry(untouched, visit), untouched);

  detail.licenseRevoked = true;
  assert.equal(context.carry({ categoryB: true }, visit).licenseRevoked, true);
  assert.equal(context.carry({ licenseRevoked: false }, visit).licenseRevoked, true);

  detail.licenseRevoked = false;
  assert.equal(context.carry({ licenseRevoked: true }, visit).licenseRevoked, false);
  assert.equal(context.carry({ categoryB: true }, visit).licenseRevoked, false);

  // уже совпадающая карточка возвращается как есть, лишней записи не будет
  const same = { licenseRevoked: false };
  assert.equal(context.carry(same, visit), same);
});

test("окно председателя ВУ и 071у рисует крупную отметку «Лишение прав» сразу под заголовком", () => {
  assert.match(modalSource, /const revocationControl = isDriverChairmanFlow \|\| chairmanType === "tractor"/);
  assert.match(modalSource, /<input type="checkbox" name="licenseRevoked" \$\{fields\.licenseRevoked \? "checked" : ""\} \/>/);
  assert.match(modalSource, /ЛИШЕНИЕ ПРАВ/);
  assert.match(
    modalSource,
    /<span>\$\{escapeHtml\(chairmanInfo\.note \|\| ""\)\}<\/span>\s*<\/div>\s*\$\{revocationControl\}\s*<div class="chairman-top">/,
  );
});

test("цвет плашки «Лишение прав» следует за галочкой без сохранения карточки", () => {
  assert.match(modalSource, /classList\.toggle\("chairman-revocation--on", revocationInput\.checked\)/);
  assert.match(stylesSource, /\.chairman-revocation--on\s*\{[^}]*background:\s*#c62828/);
});
