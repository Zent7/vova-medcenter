import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");
const indexSource = readFileSync(resolve(testDir, "../public/demo/index.html"), "utf8");

test("набранный текст карточки помечается черновиком и снимает отметку после отправки", () => {
  // Черновик живет в памяти браузера: без отметки его стирала перезагрузка осмотров.
  assert.match(appSource, /exam\.draftPending = true;/);
  assert.match(appSource, /exam\.draftRevision = \(Number\(exam\.draftRevision\) \|\| 0\) \+ 1;/);
  assert.match(appSource, /exam\.draftPending = false;/);
  // Карточка, которая сейчас уходит на сервер, остается черновиком до ответа.
  assert.match(appSource, /exam\.__saving = true;\n  exam\.draftPending = true;/);
});

test("перезагрузка осмотров обращения оставляет несохраненный черновик", () => {
  assert.match(appSource, /const pendingDrafts = data\.doctorExams\.filter\(/);
  assert.match(appSource, /\.\.\.pendingDrafts,/);
  assert.match(appSource, /pendingDraftKeys\.has\(/);
});

test("черновик переживает перезагрузку страницы", () => {
  assert.match(appSource, /doctorExamDrafts: \(Array\.isArray\(data\.doctorExams\)/);
  assert.match(appSource, /const restoredDoctorExamDrafts = Array\.isArray\(saved\.doctorExamDrafts\)/);
  // Сохранение, которое было в полете при перезагрузке, после нее не продолжается.
  assert.match(appSource, /__saving: false \}\)/);
});

test("сохранение карточки передает роль врача, чтобы найти осмотр по роли", () => {
  assert.match(modalSource, /window\.saveDoctorExam\(examId, values, \{ doctorRoleId \}\)/);
  assert.doesNotMatch(modalSource, /window\.saveDoctorExam\(examId, values\);/);
});

test("устаревший номер осмотра не отбрасывает сохранение молча", () => {
  assert.match(appSource, /Карточка врача устарела\. Откройте её заново и сохраните ещё раз/);
});

test("app.js и карточка врача подняли версию в index.html", () => {
  assert.match(indexSource, /\.\/app\.js\?v=[\w-]*doctor-draft-keep-v1/);
  assert.match(indexSource, /\.\/doctor-exam-modal\.js\?v=[\w-]*doctor-draft-keep-v1/);
});
