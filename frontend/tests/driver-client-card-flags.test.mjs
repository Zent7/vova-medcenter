import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const clientModalSource = readFileSync(resolve(testDir, "../public/demo/client-modal.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

function buildContext(chairmanExam, driverDetail) {
  const syncedExams = [];
  const context = vm.createContext({
    data: { doctorExams: [chairmanExam] },
    syncVisitToBackend: async () => {},
    getSuppressedDoctorRoleCodesForVisit: () => new Set(),
    getChairmanFormInfo: () => ({ printMode: "driver-flow" }),
    getDriverDetailFromVisit: () => driverDetail,
    applyDriverSelectionsToChairmanFields: (fields) => fields,
    persistDemoState: () => {},
    syncDoctorExamToBackend: async (exam) => syncedExams.push(exam),
  });
  const source = [
    sourceBetween("const DRIVER_INDICATION_FIELD_TO_LABEL", "const DRIVER_INDICATION_LABEL_TO_FIELD"),
    sourceBetween("const DRIVER_LIMITATION_FIELD_TO_LABEL", "const DRIVER_LIMITATION_LABEL_TO_FIELD"),
    sourceBetween("const DRIVER_LIMITATION_FIELD_ALIASES", "function collectChairmanDriverCategories"),
    sourceBetween("function mergeDriverDetailFlagsIntoChairmanFields", "function applyDriverSelectionsToChairmanFields"),
    sourceBetween("async function prepareVisitDoctorExamsForDocuments", "function openDoctorExamCard"),
    "this.prepareDocuments = prepareVisitDoctorExamsForDocuments;",
  ].join("\n");
  vm.runInContext(source, context);
  return { context, syncedExams };
}

test("client card indications and limitations reach a saved chairman card", async () => {
  const chairmanExam = {
    id: "exam-1",
    clientId: 7,
    visitId: "encounter-3",
    doctorRoleId: "chairman",
    isCompleted: true,
    fields: { doctor: "Сибирцев Вячеслав Александрович", indicationGlasses: false, restrictionBBE: false },
  };
  const { context, syncedExams } = buildContext(chairmanExam, {
    indications: ["ТС мед. изд. для коррекции зрения"],
    limitations: ["Категории B, BE, B1"],
  });

  await context.prepareDocuments({ id: 7 }, { id: "encounter-3" });

  assert.equal(syncedExams.length, 1);
  assert.equal(syncedExams[0].fields.indicationGlasses, true);
  assert.equal(syncedExams[0].fields.hasGlasses, true);
  assert.equal(syncedExams[0].fields.restrictionBBE, true);
});

test("an empty client card leaves the chairman's own marks alone", async () => {
  const chairmanExam = {
    id: "exam-2",
    clientId: 7,
    visitId: "encounter-3",
    doctorRoleId: "chairman",
    isCompleted: true,
    fields: { indicationManual: true, restrictionAM: false },
  };
  const { context, syncedExams } = buildContext(chairmanExam, { indications: [], limitations: [] });

  await context.prepareDocuments({ id: 7 }, { id: "encounter-3" });

  assert.equal(syncedExams[0].fields.indicationManual, true);
  assert.equal(syncedExams[0].fields.restrictionAM, false);
});

test("the client card offers the same labels the merge looks for", () => {
  for (const label of [
    "С ручным упр-ем",
    "С автоматич. трансмиссией",
    "Акустич. парковочная система",
    "ТС мед. изд. для коррекции зрения",
    "ТС мед. изд. для компенсации потери слуха",
  ]) {
    assert.ok(clientModalSource.includes(`"${label}"`), `клиентская карточка должна предлагать «${label}»`);
    assert.ok(appSource.includes(`"${label}"`), `печать должна знать «${label}»`);
  }
  for (const label of [
    "Категории A, M, A1, B1",
    "Категории B, BE, B1",
    "Категории C, CE, D, DE, Tm, Tb, C1, D1, C1E, D1E",
  ]) {
    assert.ok(clientModalSource.includes(`"${label}"`), `клиентская карточка должна предлагать «${label}»`);
    assert.ok(appSource.includes(`"${label}"`), `печать должна знать «${label}»`);
  }
});
