import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Правки карточки врача, ещё не сохранённые через «ОК», не должны пропадать, когда
// осмотры загружаются с сервера (открытие карточки из главной таблицы загружает их).

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const indexHtml = readFileSync(resolve(testDir, "../public/demo/index.html"), "utf8");

function extractFrom(source, name) {
  const start = source.search(new RegExp(`(async )?function ${name}\\(`));
  assert.ok(start >= 0, `Не найдена функция ${name}`);
  let depth = 0;
  for (let index = source.indexOf("{", source.indexOf(")", start)); index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  assert.fail(`Не удалось вырезать функцию ${name}`);
}

function makeLoader(serverExams, data) {
  const loadSource = extractFrom(appSource, "loadDoctorExamsForClient");
  const load = new Function(
    "data",
    "apiRequest",
    "showToast",
    "getDoctorSignatureName",
    "syncCompletedDoctorMarksToClient",
    `${loadSource}\nreturn loadDoctorExamsForClient;`,
  )(
    data,
    async () => serverExams,
    () => {},
    (roleId, client, name) => name || "",
    () => {},
  );
  return load;
}

const CLIENT = { id: 3, backendId: 3 };
const VISIT = { id: "visit-2", backendId: 2 };

function serverExam(id, roleId, complaints, completed = true) {
  return {
    id,
    client_id: 3,
    encounter_id: 2,
    doctor_role_id: roleId,
    doctor_name: "Врач",
    fields_json: { complaints },
    is_completed: completed,
  };
}

test("несохранённая правка закрытого осмотра переживает загрузку осмотров", async () => {
  const data = {
    doctorExams: [
      {
        id: "exam-local-1",
        backendId: 1,
        clientId: 3,
        visitId: "visit-2",
        doctorRoleId: "therapist",
        isCompleted: true,
        hasUnsavedChanges: true,
        fields: { complaints: "ПРАВКА до ОК" },
      },
    ],
    visits: [],
  };
  await makeLoader([serverExam(1, "therapist", "СТАРОЕ")], data)(CLIENT, VISIT);

  const therapist = data.doctorExams.find((exam) => exam.doctorRoleId === "therapist");
  assert.equal(therapist.fields.complaints, "ПРАВКА до ОК");
  assert.equal(therapist.id, "exam-local-1");
  assert.equal(data.doctorExams.filter((exam) => exam.doctorRoleId === "therapist").length, 1);
});

test("черновик, которого нет на сервере, не стирается загрузкой осмотров", async () => {
  const data = {
    doctorExams: [
      {
        id: "exam-local-2",
        clientId: 3,
        visitId: "visit-2",
        doctorRoleId: "surgeon",
        isCompleted: false,
        fields: { complaints: "ЧЕРНОВИК хирурга" },
      },
    ],
    visits: [],
  };
  await makeLoader([serverExam(1, "therapist", "СТАРОЕ")], data)(CLIENT, VISIT);

  const surgeon = data.doctorExams.find((exam) => exam.doctorRoleId === "surgeon");
  assert.equal(surgeon.fields.complaints, "ЧЕРНОВИК хирурга");
  assert.ok(data.doctorExams.some((exam) => exam.doctorRoleId === "therapist"));
});

test("без несохранённых правок осмотры берутся с сервера", async () => {
  const data = {
    doctorExams: [
      {
        id: "exam-local-3",
        backendId: 1,
        clientId: 3,
        visitId: "visit-2",
        doctorRoleId: "therapist",
        isCompleted: true,
        fields: { complaints: "УЖЕ ЗАПИСАНО ранее" },
      },
    ],
    visits: [],
  };
  await makeLoader([serverExam(1, "therapist", "С СЕРВЕРА")], data)(CLIENT, VISIT);

  const therapist = data.doctorExams.find((exam) => exam.doctorRoleId === "therapist");
  assert.equal(therapist.fields.complaints, "С СЕРВЕРА");
  assert.equal(therapist.id, "exam-1");
});

test("осмотры другого обращения загрузка не трогает", async () => {
  const data = {
    doctorExams: [
      {
        id: "exam-other",
        clientId: 3,
        visitId: "visit-9",
        doctorRoleId: "surgeon",
        isCompleted: false,
        fields: { complaints: "ДРУГОЕ обращение" },
      },
    ],
    visits: [],
  };
  await makeLoader([], data)(CLIENT, VISIT);

  assert.ok(data.doctorExams.some((exam) => exam.id === "exam-other"));
});

test("после «ОК» флаг снят: сохранённый осмотр берётся с сервера", async () => {
  const data = {
    doctorExams: [
      {
        id: "exam-local-4",
        backendId: 1,
        clientId: 3,
        visitId: "visit-2",
        doctorRoleId: "therapist",
        isCompleted: true,
        hasUnsavedChanges: false,
        fields: { complaints: "СТАРОЕ" },
      },
    ],
    visits: [],
  };
  await makeLoader([serverExam(1, "therapist", "ПОСЛЕ ОК")], data)(CLIENT, VISIT);

  const therapist = data.doctorExams.find((exam) => exam.doctorRoleId === "therapist");
  assert.equal(therapist.fields.complaints, "ПОСЛЕ ОК");
});

test("флаг несохранённого ввода ставит только ввод врача, а не перерисовка карточки", () => {
  const draftSource = extractFrom(appSource, "saveDoctorExamDraft");
  assert.match(draftSource, /if \(options\.userInput\) exam\.hasUnsavedChanges = true;/);
  const syncSource = extractFrom(appSource, "syncDoctorExamToBackend");
  assert.match(syncSource, /exam\.hasUnsavedChanges = false;/);
  const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");
  assert.match(modalSource, /captureDoctorExamDraftFromDom\(\{ userInput: true \}\);/);
});

test("index.html грузит app.js с токеном этой правки", () => {
  assert.match(indexHtml, /app\.js\?v=20261024-doctor-unsaved-edits-v1/);
  assert.match(indexHtml, /doctor-exam-modal\.js\?v=20261024-doctor-unsaved-edits-v1/);
});
