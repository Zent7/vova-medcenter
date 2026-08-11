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

test("document preparation syncs only existing non-suppressed exams", async () => {
  const prepareSource = sourceBetween(
    "async function prepareVisitDoctorExamsForDocuments",
    "function openDoctorExamCard",
  );
  const syncCalls = [];
  const syncedExams = [];
  const client = { id: 10 };
  const visit = { id: "encounter-20", suppressedDoctorRoleIds: ["surgeon"] };
  const existingTherapist = {
    id: "exam-1",
    clientId: 10,
    visitId: "encounter-20",
    doctorRoleId: "therapist",
    isCompleted: true,
  };
  const context = vm.createContext({
    data: {
      doctorExams: [
        existingTherapist,
        { id: "exam-2", clientId: 10, visitId: "encounter-20", doctorRoleId: "surgeon" },
        { id: "exam-3", clientId: 10, visitId: "encounter-99", doctorRoleId: "neurologist" },
      ],
    },
    syncVisitToBackend: async (...args) => syncCalls.push(args),
    getSuppressedDoctorRoleCodesForVisit: (targetVisit) => new Set(targetVisit.suppressedDoctorRoleIds || []),
    getChairmanFormInfo: () => ({ printMode: "default" }),
    syncDoctorExamToBackend: async (exam) => syncedExams.push(exam),
  });
  vm.runInContext(`${prepareSource}; this.prepareDocuments = prepareVisitDoctorExamsForDocuments;`, context);

  const result = await context.prepareDocuments(client, visit);

  assert.equal(syncCalls[0][2].syncRequiredDoctorExams, false);
  assert.deepEqual(Array.from(result), [existingTherapist]);
  assert.deepEqual(syncedExams, [existingTherapist]);
});

test("visit sync can skip required doctor creation during printing", () => {
  const syncSource = sourceBetween("async function syncVisitToBackend", "function getServerServiceNameById");
  assert.match(syncSource, /syncRequiredDoctorExams = true/);
  assert.match(syncSource, /if \(syncRequiredDoctorExams\)\s*{\s*await ensureRequiredDoctorExamsForVisit/);
});

test("backend document generation does not autofill doctor exams", () => {
  const generatorSource = readFileSync(
    resolve(testDir, "../../backend/app/services/document_generator.py"),
    "utf8",
  );
  assert.doesNotMatch(generatorSource, /autofill_completed_doctors_for_service/);
  assert.doesNotMatch(generatorSource, /_autofill_ambulatory_encounter_data/);
});
