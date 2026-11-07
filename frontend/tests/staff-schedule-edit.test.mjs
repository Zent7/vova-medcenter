import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// График работы ведется по медцентрам: у каждого медцентра свои смена и время, а ставка одна на сотрудника.
// Создание: блок медцентра открыт, только если медцентр отмечен в форме. Изменение: блоки всех медцентров сотрудника.
// Сохранение шлет PUT /staff/{id}/schedules со списком графиков и ставкой: пустой блок медцентра значит «без графика».

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

const CENTER_A = { id: 1, name: "Мед-Авто" };
const CENTER_B = { id: 2, name: "Медилэнд" };
const CENTER_C = { id: 3, name: "ПЕРВАЯ ЗДРАВНИЦА" };

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

// Собирает вырезанные из app.js функции в одну область видимости. context — то, что они берут снаружи (data и т.п.).
function load(names, returned, context = {}) {
  const keys = Object.keys(context);
  const source = names.map((name) => extractFunction(name)).join("\n");
  return new Function(...keys, `${source}\nreturn ${returned};`)(...keys.map((key) => context[key]));
}

// Форма создания или изменения: только то, что читают функции графика.
function fakeForm({ role = "doctor", checked = [], values = {} } = {}) {
  const elements = { role_code: { value: role } };
  for (const [name, value] of Object.entries(values)) elements[name] = { value };
  return {
    elements,
    querySelectorAll(selector) {
      if (selector === 'input[name="center_ids"]:checked') return checked.map((id) => ({ value: String(id) }));
      throw new Error(`Неожиданный селектор: ${selector}`);
    },
  };
}

// Открывающие теги блоков медцентров: по ним видно, какой блок выключен.
function scheduleBlocks(html) {
  return html.match(/<fieldset class="employee-schedule__center"[^>]*>/g) || [];
}

function workspaceContext() {
  const constant = appSource.match(/const WORKSPACE_CENTER_NAMES = (\[[^\]]*\]);/);
  assert.ok(constant, "Не найден список рабочих медцентров");
  return {
    data: { centers: [CENTER_A, CENTER_B, CENTER_C, { id: 9, name: "Чужой" }] },
    WORKSPACE_CENTER_NAMES: new Function(`return ${constant[1]};`)(),
  };
}

const RENDER_FIELDS = [
  "formatStaffTime",
  "escapeHtml",
  "staffScheduleNames",
  "renderStaffCenterScheduleBlock",
  "renderStaffScheduleFields",
];
const RENDER_EDIT_FORM = [...RENDER_FIELDS, "renderStaffScheduleEditForm"];
const SCHEDULE_READERS = [
  "staffScheduleNames",
  "collectStaffScheduleValues",
  "readStaffSchedulesFromValues",
  "describeStaffScheduleValues",
  "getAssignableCenters",
  "checkedStaffCenters",
  "describeStaffScheduleDraft",
  "readStaffScheduleFromForm",
];

test("создание и изменение рисуют блоки графика одной функцией", () => {
  assert.match(extractFunction("renderEmployeePage"), /\$\{renderStaffScheduleFields\(getAssignableCenters\(\), \[\], null, \[\]\)\}/);
  assert.match(
    extractFunction("renderStaffScheduleEditForm"),
    /\$\{renderStaffScheduleFields\(user\.centers \|\| \[\], user\.schedules \|\| \[\], user\.hourly_rate\)\}/,
  );
});

test("у каждого сотрудника в списке есть кнопка «График», панель открывается по ней", () => {
  const page = extractFunction("renderEmployeePage");
  assert.match(page, /<button class="ghost-button" type="button" data-edit-staff-schedule="\$\{escapeHtml\(user\.id\)\}">График<\/button>/);
  assert.match(page, /Number\(data\.editingStaffScheduleId\) === Number\(user\.id\)\s*\?\s*renderStaffScheduleEditForm\(user\)/);
});

test("у каждого медцентра свой блок графика, ставка одна на сотрудника", () => {
  const html = load(RENDER_FIELDS, "renderStaffScheduleFields")([CENTER_A, CENTER_B], [], null, null);
  assert.equal(scheduleBlocks(html).length, 2);
  assert.match(html, /<legend>Мед-Авто<\/legend>/);
  assert.match(html, /<legend>Медилэнд<\/legend>/);
  assert.match(html, /name="schedule_pattern_1"/);
  assert.match(html, /name="schedule_start_2" value=""/);
  assert.match(html, /name="schedule_end_2" value=""/);
  assert.equal(html.match(/name="hourly_rate"/g).length, 1);
});

test("текущие графики показываются в блоке своего медцентра", () => {
  const html = load(RENDER_FIELDS, "renderStaffScheduleFields")(
    [CENTER_A, CENTER_B],
    [
      { center_id: 1, pattern: "5/2", shift_start: "22:00:00", shift_end: "06:00:00" },
      { center_id: 2, pattern: "2/2", shift_start: "08:00:00", shift_end: "20:00:00" },
    ],
    "350.50",
  );
  assert.match(html, /name="schedule_pattern_1" value="5\/2" checked/);
  assert.doesNotMatch(html, /name="schedule_pattern_1" value="2\/2" checked/);
  assert.match(html, /name="schedule_pattern_2" value="2\/2" checked/);
  assert.match(html, /name="schedule_start_1" value="22:00"/);
  assert.match(html, /name="schedule_end_1" value="06:00"/);
  assert.match(html, /name="schedule_start_2" value="08:00"/);
  assert.match(html, /name="hourly_rate"[^>]*value="350\.5"/);
});

test("на форме создания блоки выключены, пока медцентр не отмечен", () => {
  const render = load(RENDER_FIELDS, "renderStaffScheduleFields");
  const [blockA, blockB] = scheduleBlocks(render([CENTER_A, CENTER_B], [], null, [2]));
  assert.match(blockA, /disabled/);
  assert.doesNotMatch(blockB, /disabled/);
  assert.ok(scheduleBlocks(render([CENTER_A, CENTER_B], [], null, [])).every((tag) => tag.includes("disabled")));
});

test("без медцентров вместо блоков подсказка отметить медцентры", () => {
  const html = load(RENDER_FIELDS, "renderStaffScheduleFields")([], [], null, null);
  assert.equal(scheduleBlocks(html).length, 0);
  assert.match(html, /Сначала отметьте медцентры/);
});

test("панель изменения открывает блоки всех медцентров сотрудника и содержит сохранение, очистку и отмену", () => {
  const html = load(RENDER_EDIT_FORM, "renderStaffScheduleEditForm")({
    id: 7,
    centers: [CENTER_A, CENTER_B],
    schedules: [{ center_id: 2, pattern: "3/3", shift_start: "08:00:00", shift_end: "20:00:00" }],
    hourly_rate: "400",
  });
  assert.match(html, /<form class="employee-schedule-edit" data-staff-schedule-form="7">/);
  assert.equal(scheduleBlocks(html).length, 2);
  assert.ok(scheduleBlocks(html).every((tag) => !tag.includes("disabled")));
  assert.match(html, /name="schedule_pattern_2" value="3\/3" checked/);
  assert.doesNotMatch(html, /name="schedule_pattern_1" value="[^"]*" checked/);
  assert.match(html, /name="hourly_rate"[^>]*value="400"/);
  assert.match(html, /type="submit">Сохранить график</);
  assert.match(html, /data-clear-staff-schedule>Очистить график</);
  assert.match(html, /data-cancel-staff-schedule>Отмена</);
  assert.match(html, /data-staff-schedule-error/);
});

test("рабочими считаются только отмеченные медцентры; у админа медцентров нет", () => {
  const checked = load(["getAssignableCenters", "checkedStaffCenters"], "checkedStaffCenters", workspaceContext());
  assert.deepEqual(checked(fakeForm({ checked: [2, 3, 9] })), [CENTER_B, CENTER_C]);
  assert.deepEqual(checked(fakeForm({ role: "admin", checked: [1, 2] })), []);
});

function scheduleFunctions() {
  return load(SCHEDULE_READERS, "{ readStaffScheduleFromForm, describeStaffScheduleDraft }", workspaceContext());
}

test("пустые блоки значат «без графика», неполный блок называет свой медцентр", () => {
  const { readStaffScheduleFromForm } = scheduleFunctions();
  assert.deepEqual(readStaffScheduleFromForm(fakeForm(), [CENTER_A, CENTER_B]), { schedules: [], hourly_rate: null });
  assert.match(
    readStaffScheduleFromForm(fakeForm({ values: { schedule_pattern_1: "2/2" } }), [CENTER_A]).error,
    /Мед-Авто: укажите, со скольки и до скольки/,
  );
  assert.match(
    readStaffScheduleFromForm(fakeForm({ values: { schedule_start_2: "08:00", schedule_end_2: "20:00" } }), [CENTER_B]).error,
    /Медилэнд: выберите смену/,
  );
});

test("заполненные блоки уходят графиками своих медцентров, ставка с запятой", () => {
  const { readStaffScheduleFromForm } = scheduleFunctions();
  const form = fakeForm({
    values: {
      schedule_pattern_1: "5/2",
      schedule_start_1: "20:00",
      schedule_end_1: "08:00",
      schedule_pattern_2: "2/2",
      schedule_start_2: "08:00",
      schedule_end_2: "20:00",
      hourly_rate: "350,5",
    },
  });
  assert.deepEqual(readStaffScheduleFromForm(form, [CENTER_A, CENTER_B]), {
    schedules: [
      { center_id: 1, pattern: "5/2", shift_start: "20:00", shift_end: "08:00" },
      { center_id: 2, pattern: "2/2", shift_start: "08:00", shift_end: "20:00" },
    ],
    hourly_rate: 350.5,
  });
});

test("блок медцентра, который не передан (не отмечен), в графики не попадает", () => {
  const { readStaffScheduleFromForm } = scheduleFunctions();
  const form = fakeForm({ values: { schedule_pattern_1: "2/2", schedule_start_1: "08:00", schedule_end_1: "20:00" } });
  assert.deepEqual(readStaffScheduleFromForm(form, [CENTER_B]), { schedules: [], hourly_rate: null });
});

test("ставка без графика сохраняется, неверная ставка — ошибка", () => {
  const { readStaffScheduleFromForm } = scheduleFunctions();
  assert.deepEqual(readStaffScheduleFromForm(fakeForm({ values: { hourly_rate: "300" } }), [CENTER_A]), {
    schedules: [],
    hourly_rate: 300,
  });
  assert.match(readStaffScheduleFromForm(fakeForm({ values: { hourly_rate: "350,555" } }), [CENTER_A]).error, /не больше двух знаков/);
});

test("сводка показывает строку на каждый заполненный медцентр и ставку", () => {
  const { describeStaffScheduleDraft } = scheduleFunctions();
  const form = fakeForm({
    checked: [1, 2],
    values: { schedule_pattern_1: "5/2", schedule_start_1: "20:00", schedule_end_1: "08:00", hourly_rate: "350" },
  });
  assert.equal(describeStaffScheduleDraft(form), "Мед-Авто: 5/2 · 20:00–08:00; 350 ₽/ч");
  assert.equal(describeStaffScheduleDraft(fakeForm({ checked: [1] })), "График не задан");
});

test("очистка сбрасывает смены и время во всех блоках и ставку", () => {
  const clear = load(["clearStaffScheduleFields"], "clearStaffScheduleFields");
  const radios = [{ checked: true }, { checked: true }];
  const times = [{ value: "08:00" }, { value: "20:00" }];
  const rate = [{ value: "350" }];
  clear({
    querySelectorAll(selector) {
      if (selector === 'input[type="radio"][name^="schedule_pattern_"]') return radios;
      if (selector === 'input[type="time"][name^="schedule_"]') return times;
      if (selector === 'input[name="hourly_rate"]') return rate;
      throw new Error(`Неожиданный селектор: ${selector}`);
    },
  });
  assert.ok(radios.every((radio) => radio.checked === false));
  assert.ok(times.every((input) => input.value === ""));
  assert.equal(rate[0].value, "");
});

function saveSchedules({ data, apiRequest }) {
  const toasts = [];
  const run = load(["updateDemoStaffSchedule"], "updateDemoStaffSchedule", {
    data,
    apiRequest,
    persistDemoState: () => {},
    renderApp: () => {},
    showToast: (message) => toasts.push(message),
    humanizeApiError: (error, fallback) => `${fallback}: ${error.message}`,
  });
  return { run, toasts };
}

test("сохранение шлет графики и ставку на PUT /staff/{id}/schedules и обновляет строку сотрудника", async () => {
  const requests = [];
  const data = {
    staffUsers: [
      { id: 7, full_name: "Врач", login: "doc", centers: [CENTER_A], schedules: [], hourly_rate: null },
      { id: 8, full_name: "Другой", login: "other", centers: [], schedules: [], hourly_rate: null },
    ],
    editingStaffScheduleId: 7,
  };
  const payload = {
    schedules: [{ center_id: 1, pattern: "5/2", shift_start: "22:00", shift_end: "06:00" }],
    hourly_rate: 350.5,
  };
  const { run, toasts } = saveSchedules({
    data,
    apiRequest: async (path, options) => {
      requests.push({ path, method: options.method, body: options.body });
      return {
        id: 7,
        full_name: "Врач",
        login: "doc",
        centers: [CENTER_A],
        schedules: [{ center_id: 1, center_name: "Мед-Авто", pattern: "5/2", shift_start: "22:00:00", shift_end: "06:00:00" }],
        hourly_rate: "350.50",
      };
    },
  });
  const error = await run(7, payload);

  assert.equal(error, "");
  assert.deepEqual(requests, [{ path: "/staff/7/schedules", method: "PUT", body: JSON.stringify(payload) }]);
  assert.equal(data.editingStaffScheduleId, null);
  assert.equal(data.staffUsers[0].schedules[0].pattern, "5/2");
  assert.equal(data.staffUsers[1].login, "other");
  assert.deepEqual(toasts, ["График сотрудника Врач сохранен"]);
});

test("пустой список графиков снимает их все: тост «снят»", async () => {
  const bodies = [];
  const data = {
    staffUsers: [
      {
        id: 7,
        full_name: "Врач",
        login: "doc",
        centers: [CENTER_A],
        schedules: [{ center_id: 1, pattern: "2/2" }],
        hourly_rate: null,
      },
    ],
    editingStaffScheduleId: 7,
  };
  const { run, toasts } = saveSchedules({
    data,
    apiRequest: async (path, options) => {
      bodies.push(options.body);
      return { id: 7, full_name: "Врач", login: "doc", centers: [CENTER_A], schedules: [], hourly_rate: null };
    },
  });
  const error = await run(7, { schedules: [], hourly_rate: null });

  assert.equal(error, "");
  assert.deepEqual(bodies, [JSON.stringify({ schedules: [], hourly_rate: null })]);
  assert.deepEqual(data.staffUsers[0].schedules, []);
  assert.deepEqual(toasts, ["График сотрудника Врач снят"]);
});

test("ошибка сервера возвращается форме, а редактор остаётся открытым", async () => {
  const data = { staffUsers: [], editingStaffScheduleId: 7 };
  const { run, toasts } = saveSchedules({
    data,
    apiRequest: async () => {
      throw new Error("Сотрудник не найден");
    },
  });
  const error = await run(7, { schedules: [], hourly_rate: null });

  assert.equal(error, "Не удалось сохранить график: Сотрудник не найден");
  assert.equal(data.editingStaffScheduleId, 7);
  assert.deepEqual(toasts, []);
});

test("обработчики панели: открыть, отменить, очистить, сохранить по медцентрам и показать ошибку на месте", () => {
  const binding = extractFunction("bindContentEvents");
  assert.match(binding, /querySelectorAll\("\[data-edit-staff-schedule\]"\)/);
  assert.match(binding, /querySelectorAll\("\[data-cancel-staff-schedule\]"\)/);
  assert.match(binding, /querySelectorAll\("\[data-staff-schedule-form\]"\)/);
  assert.match(binding, /clearStaffScheduleFields\(form\)/);
  assert.match(binding, /readStaffScheduleFromForm\(form, user\?\.centers \|\| \[\]\)/);
  assert.match(
    binding,
    /const error = await updateDemoStaffSchedule\(userId, \{\s*schedules: staffSchedule\.schedules,\s*hourly_rate: staffSchedule\.hourly_rate,\s*\}\);/,
  );
  assert.match(binding, /showStaffScheduleEditError\(form, error\)/);
  assert.match(binding, /clearStaffScheduleFields\(employeeCreateForm\)/);
});

test("на форме создания блоки медцентров открываются по отметке медцентра, а сохранение берет графики по отмеченным", () => {
  const binding = extractFunction("bindContentEvents");
  assert.match(binding, /const enabled = new Set\(checkedStaffCenters\(employeeCreateForm\)\.map\(\(center\) => String\(center\.id\)\)\);/);
  assert.match(binding, /querySelectorAll\("\[data-schedule-center\]"\)/);
  assert.match(binding, /readStaffScheduleFromForm\(employeeCreateForm, checkedStaffCenters\(employeeCreateForm\)\)/);
  assert.match(binding, /schedules: staffSchedule\.schedules,\s*hourly_rate: staffSchedule\.hourly_rate,/);
});

test("выход из программы закрывает панель графика", () => {
  assert.match(extractFunction("signOutDemoStaff"), /data\.editingStaffScheduleId = null;/);
});
