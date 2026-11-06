import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// График можно задать и поменять у уже созданного сотрудника. Кнопка «График» в его строке
// открывает ту же панель, что в форме создания, и сохраняет график через PUT /staff/{id}/schedule.
// Пустые поля снимают график: при создании это значит «без графика».

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

function extractFunction(name) {
  const start = appSource.search(new RegExp(`(async )?function ${name}\\(`));
  assert.ok(start >= 0, `Не найдена функция ${name}`);
  let depth = 0;
  for (let index = appSource.indexOf("{", appSource.indexOf(")", start)); index < appSource.length; index += 1) {
    if (appSource[index] === "{") depth += 1;
    if (appSource[index] === "}") {
      depth -= 1;
      if (depth === 0) return appSource.slice(start, index + 1);
    }
  }
  assert.fail(`Не удалось вырезать функцию ${name}`);
}

function buildRenderEditForm() {
  return new Function(
    [
      extractFunction("formatStaffTime"),
      extractFunction("escapeHtml"),
      extractFunction("renderStaffScheduleFields"),
      extractFunction("renderStaffScheduleEditForm"),
      "return renderStaffScheduleEditForm;",
    ].join("\n"),
  )();
}

function buildRenderFields() {
  return new Function(
    [
      extractFunction("formatStaffTime"),
      extractFunction("escapeHtml"),
      extractFunction("renderStaffScheduleFields"),
      "return renderStaffScheduleFields;",
    ].join("\n"),
  )();
}

test("создание и изменение графика рисуют одну и ту же панель", () => {
  assert.match(extractFunction("renderEmployeePage"), /\$\{renderStaffScheduleFields\(\)\}/);
  assert.match(extractFunction("renderStaffScheduleEditForm"), /\$\{renderStaffScheduleFields\(user\.schedule\)\}/);
});

test("у каждого сотрудника в списке есть кнопка «График», панель открывается по ней", () => {
  const page = extractFunction("renderEmployeePage");
  assert.match(page, /<button class="ghost-button" type="button" data-edit-staff-schedule="\$\{escapeHtml\(user\.id\)\}">График<\/button>/);
  assert.match(page, /Number\(data\.editingStaffScheduleId\) === Number\(user\.id\)\s*\?\s*renderStaffScheduleEditForm\(user\)/);
});

test("панель изменения содержит сохранение, очистку и отмену", () => {
  const html = buildRenderEditForm()({ id: 7, schedule: null });
  assert.match(html, /<form class="employee-schedule-edit" data-staff-schedule-form="7">/);
  assert.match(html, /type="submit">Сохранить график</);
  assert.match(html, /data-clear-staff-schedule>Очистить график</);
  assert.match(html, /data-cancel-staff-schedule>Отмена</);
  assert.match(html, /data-staff-schedule-error/);
});

test("панель заполняется текущим графиком сотрудника", () => {
  const renderFields = buildRenderFields();
  const html = renderFields({ pattern: "5/2", shift_start: "22:00:00", shift_end: "06:00:00", hourly_rate: "350.50" });
  assert.match(html, /value="5\/2" checked/);
  assert.doesNotMatch(html, /value="2\/2" checked/);
  assert.match(html, /name="schedule_start" value="22:00"/);
  assert.match(html, /name="schedule_end" value="06:00"/);
  assert.match(html, /name="hourly_rate"[^>]*value="350\.5"/);
});

test("у сотрудника без графика панель пустая", () => {
  const html = buildRenderFields()(null);
  assert.doesNotMatch(html, / checked/);
  assert.match(html, /name="schedule_start" value=""/);
  assert.match(html, /name="schedule_end" value=""/);
  assert.match(html, /name="hourly_rate"[^>]*value=""/);
});

function readSchedule(values) {
  const form = {
    elements: {
      schedule_pattern: { value: values.pattern ?? "" },
      schedule_start: { value: values.start ?? "" },
      schedule_end: { value: values.end ?? "" },
      hourly_rate: { value: values.rate ?? "" },
    },
  };
  return new Function(extractFunction("readStaffScheduleFromForm") + "\nreturn readStaffScheduleFromForm;")()(form);
}

test("пустая панель значит «без графика», неполная — подсказку, полная уходит на сервер", () => {
  assert.deepEqual(readSchedule({}), { schedule: null });
  assert.match(readSchedule({ pattern: "2/2" }).error, /со скольки и до скольки/);
  assert.match(readSchedule({ start: "08:00", end: "20:00" }).error, /Выберите смену/);
  assert.match(readSchedule({ pattern: "2/2", start: "08:00", end: "20:00", rate: "350,555" }).error, /не больше двух знаков/);
  assert.deepEqual(readSchedule({ pattern: "5/2", start: "20:00", end: "08:00", rate: "350,5" }), {
    schedule: { pattern: "5/2", shift_start: "20:00", shift_end: "08:00", hourly_rate: 350.5 },
  });
  assert.equal(readSchedule({ pattern: "6/1", start: "08:00", end: "20:00" }).schedule.hourly_rate, null);
});

function saveSchedule({ apiRequest, data }) {
  const toasts = [];
  const run = new Function(
    "data",
    "apiRequest",
    "persistDemoState",
    "renderApp",
    "showToast",
    "humanizeApiError",
    extractFunction("updateDemoStaffSchedule") + "\nreturn updateDemoStaffSchedule;",
  )(
    data,
    apiRequest,
    () => {},
    () => {},
    (message) => toasts.push(message),
    (error, fallback) => `${fallback}: ${error.message}`,
  );
  return { run, toasts };
}

test("сохранение шлёт график на сервер и обновляет строку сотрудника", async () => {
  const requests = [];
  const data = {
    staffUsers: [
      { id: 7, full_name: "Врач", login: "doc", schedule: null },
      { id: 8, full_name: "Другой", login: "other", schedule: null },
    ],
    editingStaffScheduleId: 7,
  };
  const schedule = { pattern: "5/2", shift_start: "22:00", shift_end: "06:00", hourly_rate: 350.5 };
  const { run, toasts } = saveSchedule({
    data,
    apiRequest: async (path, options) => {
      requests.push({ path, method: options.method, body: options.body });
      return {
        id: 7,
        full_name: "Врач",
        login: "doc",
        schedule: { pattern: "5/2", shift_start: "22:00:00", shift_end: "06:00:00", hourly_rate: "350.50" },
      };
    },
  });
  const error = await run(7, schedule);

  assert.equal(error, "");
  assert.deepEqual(requests, [{ path: "/staff/7/schedule", method: "PUT", body: JSON.stringify({ schedule }) }]);
  assert.equal(data.editingStaffScheduleId, null);
  assert.equal(data.staffUsers[0].schedule.pattern, "5/2");
  assert.equal(data.staffUsers[1].login, "other");
  assert.deepEqual(toasts, ["График сотрудника Врач сохранен"]);
});

test("снятие графика отправляет schedule: null", async () => {
  const bodies = [];
  const data = {
    staffUsers: [{ id: 7, full_name: "Врач", login: "doc", schedule: { pattern: "2/2" } }],
    editingStaffScheduleId: 7,
  };
  const { run, toasts } = saveSchedule({
    data,
    apiRequest: async (path, options) => {
      bodies.push(options.body);
      return { id: 7, full_name: "Врач", login: "doc", schedule: null };
    },
  });
  const error = await run(7, null);

  assert.equal(error, "");
  assert.deepEqual(bodies, [JSON.stringify({ schedule: null })]);
  assert.equal(data.staffUsers[0].schedule, null);
  assert.deepEqual(toasts, ["График сотрудника Врач снят"]);
});

test("ошибка сервера возвращается форме, а редактор остаётся открытым", async () => {
  const data = { staffUsers: [], editingStaffScheduleId: 7 };
  const { run, toasts } = saveSchedule({
    data,
    apiRequest: async () => {
      throw new Error("Сотрудник не найден");
    },
  });
  const error = await run(7, { pattern: "2/2", shift_start: "08:00", shift_end: "20:00", hourly_rate: null });

  assert.equal(error, "Не удалось сохранить график: Сотрудник не найден");
  assert.equal(data.editingStaffScheduleId, 7);
  assert.deepEqual(toasts, []);
});

test("обработчики панели: открыть, отменить, очистить, сохранить и показать ошибку на месте", () => {
  const binding = extractFunction("bindContentEvents");
  assert.match(binding, /querySelectorAll\("\[data-edit-staff-schedule\]"\)/);
  assert.match(binding, /querySelectorAll\("\[data-cancel-staff-schedule\]"\)/);
  assert.match(binding, /querySelectorAll\("\[data-staff-schedule-form\]"\)/);
  assert.match(binding, /clearStaffScheduleFields\(form\)/);
  assert.match(binding, /const error = await updateDemoStaffSchedule\(userId, staffSchedule\.schedule\);/);
  assert.match(binding, /showStaffScheduleEditError\(form, error\)/);
  assert.match(binding, /clearStaffScheduleFields\(employeeCreateForm\)/);
});

test("выход из программы закрывает панель графика", () => {
  assert.match(extractFunction("signOutDemoStaff"), /data\.editingStaffScheduleId = null;/);
});
