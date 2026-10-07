import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");
const indexSource = readFileSync(resolve(testDir, "../public/demo/index.html"), "utf8");

test("every doctor card template carries data-doctor-role-id on its form", () => {
  const owners = [...modalSource.matchAll(/<(\w+)\b[^<>]*?\bdata-doctor-role-id=/g)].map((match) => match[1]);
  assert.ok(owners.length > 0);
  assert.deepEqual([...new Set(owners)], ["form"]);
});

test("doctor button handler skips the card form, so deleting a doctor is not undone", () => {
  // Форма карточки несёт data-doctor-role-id. Обработчик на всех таких элементах
  // ловил клик по «удалить врача» и по подписям полей: заново грузил осмотры,
  // открывал карточку и снимал исключение врача из обращения, после чего
  // сохранение возвращало его отметкой.
  assert.doesNotMatch(appSource, /querySelectorAll\("\[data-doctor-role-id\]"\)/);
  assert.match(appSource, /contentRoot\.querySelectorAll\("button\[data-doctor-role-id\]"\)/);
});

test("app.js cache token was bumped for the doctor button fix", () => {
  assert.match(indexSource, /app\.js\?v=20261007-doctor-card-click-v1/);
});
