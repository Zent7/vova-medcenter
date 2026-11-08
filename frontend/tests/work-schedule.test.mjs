import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// График работы (work-schedule.js): таблица месяца, правка дня, отпуск и больничный, первая смена,
// статистика план-факт и печать. Чистые функции берутся из файла как есть; права и подключение
// проверяются по app.js и index.html, потому что модуль работает только вместе с ними.

const testDir = dirname(fileURLToPath(import.meta.url));
const demoDir = resolve(testDir, "../public/demo");
const scheduleSource = readFileSync(resolve(demoDir, "work-schedule.js"), "utf8");
// Список отметок рисует вместе с модулем статуса: даты, время и длительность берутся оттуда.
const statusSource = readFileSync(resolve(demoDir, "work-status.js"), "utf8");
const appSource = readFileSync(resolve(demoDir, "app.js"), "utf8");
const indexSource = readFileSync(resolve(demoDir, "index.html"), "utf8");
const stylesSource = readFileSync(resolve(demoDir, "styles.css"), "utf8");

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

// Модуль с настоящим canViewWorkSchedule из app.js: права в тестах те же, что в программе.
function loadSchedule(roleCode = "admin", userId = null) {
  const appState = { auth: { roleCode, userId } };
  const canViewWorkSchedule = new Function(
    "appState",
    `${extractFunction("canViewWorkSchedule")}\nreturn canViewWorkSchedule;`,
  )(appState);
  return new Function(
    "appState",
    "canViewWorkSchedule",
    `${scheduleSource}
${statusSource}
return {
  appState, wsState, wsCanEdit, wsCanOpen, wsDayValuesToRequest, wsAbsenceRequest, wsFactItemsFromValues,
  wsResolveCreateTarget, wsShiftMonth, wsFormatDateLabel, wsIsWeekend, buildWsHoursChart, wsCellContent,
  wsEscape, renderWorkScheduleContent, wsRenderCenterTabs, wsWithCenter, wsCenterQuery, wsConflictText, wsStatsKey,
  wsStatsReady, wsCanSeeMoney, wsMonthReportHtml, wsRenderMarksTable, wsStatsListing,
};`,
  )(appState, canViewWorkSchedule);
}

function currentMonth() {
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1 };
}

test("«Создать график» строит следующий месяц; открытый будущий месяц строится как есть", () => {
  const { wsResolveCreateTarget } = loadSchedule();
  const today = { year: 2026, month: 11, day: 6 };
  assert.deepEqual(wsResolveCreateTarget(today, { year: 2026, month: 11 }), { year: 2026, month: 12 });
  assert.deepEqual(wsResolveCreateTarget(today, { year: 2026, month: 10 }), { year: 2026, month: 12 });
  assert.deepEqual(wsResolveCreateTarget(today, { year: 2027, month: 1 }), { year: 2027, month: 1 });
  assert.deepEqual(
    wsResolveCreateTarget({ year: 2026, month: 12, day: 3 }, { year: 2026, month: 12 }),
    { year: 2027, month: 1 },
  );
});

test("переход между месяцами через год не ломается", () => {
  const { wsShiftMonth } = loadSchedule();
  assert.deepEqual(wsShiftMonth(2026, 12, 1), { year: 2027, month: 1 });
  assert.deepEqual(wsShiftMonth(2027, 1, -1), { year: 2026, month: 12 });
});

test("даты в тексте — в родительном падеже: «6 ноября 2026»", () => {
  const { wsFormatDateLabel } = loadSchedule();
  assert.equal(wsFormatDateLabel("2026-11-06"), "6 ноября 2026");
  assert.equal(wsFormatDateLabel("2026-03-01"), "1 марта 2026");
  assert.equal(wsFormatDateLabel("2026-05-09"), "9 мая 2026");
  assert.equal(wsFormatDateLabel("2026-08-15"), "15 августа 2026");
});

test("выходные — суббота и воскресенье", () => {
  const { wsIsWeekend } = loadSchedule();
  assert.equal(wsIsWeekend(2026, 11, 1), true);
  assert.equal(wsIsWeekend(2026, 11, 2), false);
  assert.equal(wsIsWeekend(2026, 11, 7), true);
});

test("день: смена со временем (в том числе ночная), отгул, очистка; без времени смена не сохраняется", () => {
  const { wsDayValuesToRequest } = loadSchedule();
  assert.deepEqual(
    wsDayValuesToRequest({ kind: "shift", start: "08:00", end: "20:00" }),
    { body: { kind: "shift", start_time: "08:00", end_time: "20:00" } },
  );
  assert.deepEqual(
    wsDayValuesToRequest({ kind: "shift", start: "22:00", end: "06:00" }),
    { body: { kind: "shift", start_time: "22:00", end_time: "06:00" } },
  );
  assert.deepEqual(wsDayValuesToRequest({ kind: "dayoff" }), { body: { kind: "dayoff" } });
  assert.deepEqual(wsDayValuesToRequest({ kind: "none" }), { clear: true });
  assert.match(wsDayValuesToRequest({ kind: "shift", start: "08:00", end: "" }).error, /со скольки и до скольки/);
  assert.match(wsDayValuesToRequest({ kind: "shift", start: "08:00", end: "08:00" }).error, /не должны совпадать/);
  assert.match(wsDayValuesToRequest({ kind: "" }).error, /Выберите/);
});

test("отпуск и больничный: период с датами, порядок дат, не больше 366 дней", () => {
  const { wsAbsenceRequest } = loadSchedule();
  assert.deepEqual(
    wsAbsenceRequest({ kind: "vacation", from: "2026-11-01", to: "2026-11-14" }),
    { body: { kind: "vacation", date_from: "2026-11-01", date_to: "2026-11-14" } },
  );
  assert.ok(wsAbsenceRequest({ kind: "sick", from: "2026-01-01", to: "2027-01-01" }).body, "366 дней — можно");
  assert.match(wsAbsenceRequest({ kind: "vacation", from: "2026-01-01", to: "2027-01-02" }).error, /длиннее года/);
  assert.match(wsAbsenceRequest({ kind: "sick", from: "2026-11-10", to: "2026-11-01" }).error, /не может быть раньше/);
  assert.match(wsAbsenceRequest({ kind: "sick", from: "", to: "2026-11-01" }).error, /Укажите даты/);
});

test("факт: оба времени или ни одного; пустые значит «из отметок»", () => {
  const { wsFactItemsFromValues } = loadSchedule();
  assert.deepEqual(
    wsFactItemsFromValues([{ date: "2026-11-06", start: "", end: "" }]),
    { items: [{ work_date: "2026-11-06", start_time: null, end_time: null }] },
  );
  assert.deepEqual(
    wsFactItemsFromValues([{ date: "2026-11-06", start: "09:00", end: "21:00" }]),
    { items: [{ work_date: "2026-11-06", start_time: "09:00", end_time: "21:00" }] },
  );
  assert.match(wsFactItemsFromValues([{ date: "2026-11-06", start: "09:00", end: "" }]).error, /6 ноября 2026/);
  assert.match(wsFactItemsFromValues([{ date: "2026-11-06", start: "09:00", end: "09:00" }]).error, /не должны совпадать/);
});

test("график часов: план и факт столбиками, шкала выше пика, пустой месяц не ломает шкалу", () => {
  const { buildWsHoursChart } = loadSchedule();
  const chart = buildWsHoursChart([
    { work_date: "2026-11-01", plan_hours: 12, fact_hours: 13 },
    { work_date: "2026-11-02", plan_hours: 0, fact_hours: 0 },
  ]);
  assert.equal(chart.bars.length, 2);
  assert.ok(chart.yMax >= 13);
  assert.equal(chart.yMax % 4, 0);
  assert.ok(chart.bars[0].fact.height > chart.bars[0].plan.height, "факт выше плана");
  assert.equal(chart.bars[1].plan.height, 0);

  const empty = buildWsHoursChart([]);
  assert.deepEqual(empty.bars, []);
  assert.equal(empty.yMax, 12);
});

test("ячейка дня: смена показывает время и номер смены, отгул, больничный и отпуск — код", () => {
  const { wsCellContent } = loadSchedule();
  const shift = wsCellContent({ kind: "shift", start_time: "08:00:00", end_time: "20:00:00", shift_no: 3 });
  assert.match(shift, /08:00/);
  assert.match(shift, /20:00/);
  assert.match(shift, /08:00-20:00/, "время смены одной строкой: 08:00-20:00");
  assert.match(shift, /смена 3/);
  assert.match(wsCellContent({ kind: "dayoff" }), /Отг/);
  assert.match(wsCellContent({ kind: "sick" }), /Бол/);
  assert.match(wsCellContent({ kind: "vacation" }), /Отп/);
  assert.equal(wsCellContent(null), "");
});

test("текст из базы экранируется", () => {
  const { wsEscape } = loadSchedule();
  assert.equal(wsEscape('<img src=x onerror="a">'), "&lt;img src=x onerror=&quot;a&quot;&gt;");
});

test("править день может только админ в режиме «Редактировать» и только в текущем месяце", () => {
  const { year, month } = currentMonth();
  const admin = loadSchedule("admin");
  admin.wsState.mode = "edit";
  admin.wsState.year = year;
  admin.wsState.month = month;
  assert.equal(admin.wsCanEdit(), true);

  admin.wsState.month = month === 12 ? 1 : month + 1;
  assert.equal(admin.wsCanEdit(), false, "в другом месяце правки нет");

  admin.wsState.mode = "view";
  admin.wsState.month = month;
  assert.equal(admin.wsCanEdit(), false, "без режима «Редактировать» правки нет");

  for (const roleCode of ["operator", "doctor"]) {
    const other = loadSchedule(roleCode);
    other.wsState.mode = "edit";
    other.wsState.year = year;
    other.wsState.month = month;
    assert.equal(other.wsCanEdit(), false, roleCode);
  }
});

test("график видят админ, врач и оператор; председатель и без роли — нет", () => {
  for (const roleCode of ["admin", "operator", "doctor"]) {
    assert.equal(loadSchedule(roleCode).wsCanOpen(), true, roleCode);
  }
  for (const roleCode of ["chairman", ""]) {
    assert.equal(loadSchedule(roleCode).wsCanOpen(), false, roleCode || "без роли");
  }
});

function sampleGrid({ year, month }) {
  const center = { id: 1, name: "Медцентр А", color: "#2F6FB3" };
  const day = {
    work_date: `${year}-${String(month).padStart(2, "0")}-01`,
    kind: "shift",
    start_time: "08:00",
    end_time: "20:00",
    fact_start_time: null,
    fact_end_time: null,
    source: "pattern",
    shift_no: 1,
  };
  return {
    year,
    month,
    days_in_month: 30,
    can_edit: true,
    center,
    centers: [center],
    rows: [
      {
        user_id: 1, full_name: "Анна", role_code: "operator", role_name: "Оператор", is_active: true,
        pattern: "4/4", shift_start: "08:00", shift_end: "20:00", days: [day],
      },
      {
        user_id: 2, full_name: "Борис", role_code: "doctor", role_name: "Врач", is_active: true,
        pattern: null, shift_start: null, shift_end: null, days: [],
      },
    ],
  };
}

test("таблица: врач и оператор видят график без правки и без денег; у них есть статистика и отчет", () => {
  const { wsState, renderWorkScheduleContent } = loadSchedule("doctor", 2);
  wsState.grid = sampleGrid(currentMonth());
  const html = renderWorkScheduleContent();
  assert.ok(html.indexOf("Анна") > 0 && html.indexOf("Борис") > html.indexOf("Анна"), "порядок строк сохранен");
  assert.doesNotMatch(html, /data-ws-cell/);
  assert.doesNotMatch(html, /data-ws-name/);
  assert.doesNotMatch(html, /Создать график|Редактировать/);
  assert.match(html, /data-ws-stats-toggle>Статистика<\/button>/, "статистика открывается по своим часам");
  assert.match(html, /data-ws-report>Сформировать месяц<\/button>/, "отчет открыт");
  assert.doesNotMatch(html, /₽|ставк/i);
  assert.match(html, /data-ws-month="-1"/);
  assert.match(html, /data-ws-month="1"/);
});

function sampleStats({ year, month, rows }) {
  return { year, month, days_in_month: 30, center: { id: 1, name: "Медцентр А", color: "#2F6FB3" }, rows };
}

// Строка статистики как ее отдает сервер: ставка и суммы приходят только админу.
function statsRow({ year, month, userId, name, rate, planHours, factHours, marks = [] }) {
  const amount = (hours) => (rate == null ? null : hours * rate);
  return {
    user_id: userId,
    full_name: name,
    role_name: "Врач",
    center_name: "Медцентр А",
    pattern: null,
    shift_start: null,
    shift_end: null,
    hourly_rate: rate,
    days: [{ work_date: `${year}-${String(month).padStart(2, "0")}-01`, plan_hours: planHours, fact_hours: factHours }],
    marks,
    plan: { days: 1, hours: planHours, amount: amount(planHours) },
    fact: { days: 1, hours: factHours, amount: amount(factHours) },
  };
}

test("статистика врача и оператора: только своя строка, без ставки и сумм, без правки факта", () => {
  const { year, month } = currentMonth();
  const doctor = loadSchedule("doctor", 2);
  doctor.wsState.grid = sampleGrid({ year, month });
  doctor.wsState.year = year;
  doctor.wsState.month = month;
  doctor.wsState.statsOpen = true;
  // Сервер врачу отдает только его строку; ставка и суммы в ней пустые.
  doctor.wsState.stats = sampleStats({
    year,
    month,
    rows: [statsRow({ year, month, userId: 2, name: "Борис", rate: null, planHours: 12, factHours: 0.97 })],
  });
  const html = doctor.renderWorkScheduleContent();
  const panel = html.match(/<div class="ws__stats"[\s\S]*?<\/table>/)?.[0] ?? "";
  assert.match(panel, /Статистика: Борис/);
  assert.match(panel, /План по графику/);
  assert.doesNotMatch(panel, /Анна/);
  assert.doesNotMatch(panel, /Сумма|₽|ставк|Редактировать факт/i);
  assert.doesNotMatch(html, /data-ws-fact-toggle/);
  assert.match(html, /data-ws-report>Сформировать месяц<\/button>/, "отчет доступен и при открытой статистике");
});

test("статистика админа: выбранный сотрудник, ставка и суммы на месте, правка факта доступна", () => {
  const { year, month } = currentMonth();
  const admin = loadSchedule("admin");
  admin.wsState.grid = sampleGrid({ year, month });
  admin.wsState.year = year;
  admin.wsState.month = month;
  admin.wsState.selectedUserId = 1;
  admin.wsState.statsOpen = true;
  admin.wsState.stats = sampleStats({
    year,
    month,
    rows: [
      statsRow({ year, month, userId: 1, name: "Анна", rate: 300, planHours: 12, factHours: 0.97 }),
      statsRow({ year, month, userId: 2, name: "Борис", rate: null, planHours: 4, factHours: 0 }),
    ],
  });
  const html = admin.renderWorkScheduleContent();
  const panel = html.match(/<div class="ws__stats"[\s\S]*?<\/table>/)?.[0] ?? "";
  assert.match(panel, /Статистика: Анна/);
  assert.match(panel, /ставка 300 ₽ в час/);
  assert.match(panel, /Сумма \(часы × ставка\)/);
  assert.match(panel, /3\s600 ₽/, "план 12 ч × 300 ₽ = 3 600 ₽");
  assert.doesNotMatch(panel, /Борис/);
  assert.match(html, /data-ws-fact-toggle/);
});

test("список отметок: таблица Сотрудник | Начало | Конец | Длит. из поля marks; открытая и длинная отметки красные", () => {
  const { year, month } = currentMonth();
  const mm = String(month).padStart(2, "0");
  const admin = loadSchedule("admin");
  admin.wsState.grid = sampleGrid({ year, month });
  admin.wsState.year = year;
  admin.wsState.month = month;
  admin.wsState.selectedUserId = 1;
  admin.wsState.statsOpen = true;
  admin.wsState.statsView = "list";
  admin.wsState.stats = sampleStats({
    year,
    month,
    rows: [
      statsRow({
        year,
        month,
        userId: 1,
        name: "Анна",
        rate: 300,
        planHours: 12,
        factHours: 25.08,
        // Как отдает сервер: новые сверху, время в UTC; в таблице время московское.
        marks: [
          { started_at: `${year}-${mm}-22T06:00:00Z`, ended_at: `${year}-${mm}-23T05:00:00Z`, duration_seconds: 82800 },
          { started_at: `${year}-${mm}-21T05:00:00Z`, ended_at: null, duration_seconds: 9000 },
          { started_at: `${year}-${mm}-02T06:05:00Z`, ended_at: `${year}-${mm}-02T14:40:00Z`, duration_seconds: 30900 },
        ],
      }),
      statsRow({
        year,
        month,
        userId: 2,
        name: "Борис",
        rate: null,
        planHours: 4,
        factHours: 1,
        marks: [{ started_at: `${year}-${mm}-03T07:00:00Z`, ended_at: `${year}-${mm}-03T08:00:00Z`, duration_seconds: 3600 }],
      }),
    ],
  });
  const html = admin.renderWorkScheduleContent();
  const table = html.match(/<table class="ws__summary wst-marks__table">[\s\S]*?<\/table>/)?.[0] ?? "";
  const stamp = (d, time) => `<span class="wst-marks__date">${String(d).padStart(2, "0")}-${mm}-${year}</span> ${time}`;
  assert.match(html, /data-ws-stats-view="list"/);
  assert.match(table, /<th>Сотрудник<\/th><th>Начало<\/th><th>Конец<\/th><th>Длит\.<\/th>/);
  assert.match(
    table,
    new RegExp(`<tr class="wst-marks__row wst-marks__row--long" title="[^"]*"><td>Анна</td><td>${stamp(22, "09:00:00")}</td><td>${stamp(23, "08:00:00")}</td><td>23:00:00</td></tr>`),
  );
  assert.match(
    table,
    new RegExp(`<tr class="wst-marks__row wst-marks__row--open" title="Нет отметки «С работы»"><td>Анна</td><td>${stamp(21, "08:00:00")}</td><td>на работе</td><td>02:30:00</td></tr>`),
  );
  assert.match(table, new RegExp(`<tr class="wst-marks__row"><td>Анна</td><td>${stamp(2, "09:05:00")}</td><td>${stamp(2, "17:40:00")}</td><td>08:35:00</td></tr>`));
  assert.doesNotMatch(table, /Борис/, "список показывает одного сотрудника — выбранного");
  assert.doesNotMatch(table, /Итого/, "итога нет: список как в статусе");
  assert.doesNotMatch(html, /class="ws-chart"|по факту, часов в день/, "вместо графика — список");
  assert.doesNotMatch(html, /wst-marks-block/, "блок отметок под статистикой убран: таблица вместо него");
  assert.match(html, /План по графику/, "итоги план-факт остаются под списком");
});

test("«Списки» переключают статистику: из графика открывают таблицу, из таблицы кнопка возвращает график", () => {
  const { year, month } = currentMonth();
  const label = (html) => html.match(/data-ws-list-toggle>([^<]+)<\/button>/)?.[1];
  const admin = loadSchedule("admin");
  admin.wsState.grid = sampleGrid({ year, month });
  admin.wsState.year = year;
  admin.wsState.month = month;
  admin.wsState.selectedUserId = 1;
  const oneMark = [{ started_at: `${year}-${String(month).padStart(2, "0")}-02T06:00:00Z`, ended_at: `${year}-${String(month).padStart(2, "0")}-02T07:00:00Z`, duration_seconds: 3600 }];
  admin.wsState.stats = sampleStats({
    year,
    month,
    rows: [statsRow({ year, month, userId: 1, name: "Анна", rate: 300, planHours: 12, factHours: 1, marks: oneMark })],
  });
  assert.equal(label(admin.renderWorkScheduleContent()), "Списки", "статистика закрыта: кнопка откроет таблицу");
  admin.wsState.statsOpen = true;
  admin.wsState.statsView = "chart";
  let html = admin.renderWorkScheduleContent();
  assert.equal(label(html), "Списки");
  assert.match(html, /class="ws-chart"/);
  admin.wsState.statsView = "list";
  html = admin.renderWorkScheduleContent();
  assert.equal(label(html), "График");
  assert.doesNotMatch(html, /class="ws-chart"/);
  assert.match(html, /<table class="ws__summary wst-marks__table">/);

  const doctor = loadSchedule("doctor", 2);
  doctor.wsState.grid = sampleGrid({ year, month });
  doctor.wsState.year = year;
  doctor.wsState.month = month;
  doctor.wsState.statsOpen = true;
  doctor.wsState.statsView = "list";
  doctor.wsState.stats = sampleStats({
    year,
    month,
    rows: [statsRow({ year, month, userId: 2, name: "Борис", rate: null, planHours: 12, factHours: 0.97 })],
  });
  const doctorHtml = doctor.renderWorkScheduleContent();
  // Таблица медцентра врачу видна вся, а статистика — только своя строка: проверяем панель статистики.
  const doctorPanel = doctorHtml.slice(doctorHtml.indexOf('<div class="ws__stats"'), doctorHtml.indexOf('<div class="ws__footer">'));
  assert.equal(label(doctorHtml), "График", "врач тоже переключает таблицу");
  assert.match(doctorPanel, /Статистика: Борис/);
  assert.doesNotMatch(doctorPanel, /Анна/);
  assert.doesNotMatch(doctorPanel, /ставк|₽/i, "список врачу без денег");
});

test("список без отметок: пустое сообщение, таблицы нет", () => {
  const { year, month } = currentMonth();
  const admin = loadSchedule("admin");
  admin.wsState.grid = sampleGrid({ year, month });
  admin.wsState.year = year;
  admin.wsState.month = month;
  admin.wsState.selectedUserId = 1;
  admin.wsState.statsOpen = true;
  admin.wsState.statsView = "list";
  admin.wsState.stats = sampleStats({ year, month, rows: [statsRow({ year, month, userId: 1, name: "Анна", rate: 300, planHours: 12, factHours: 0 })] });
  const html = admin.renderWorkScheduleContent();
  assert.match(html, /В этом месяце отметок «На работу» пока нет\./);
  assert.doesNotMatch(html, /wst-marks__table/);
});

test("ручная правка факта в списке: строка помечена «вручную», красной не бывает даже длиннее 12 часов", () => {
  const { year, month } = currentMonth();
  const mm = String(month).padStart(2, "0");
  const admin = loadSchedule("admin");
  admin.wsState.grid = sampleGrid({ year, month });
  admin.wsState.year = year;
  admin.wsState.month = month;
  admin.wsState.selectedUserId = 1;
  admin.wsState.statsOpen = true;
  admin.wsState.statsView = "list";
  admin.wsState.stats = sampleStats({
    year,
    month,
    rows: [
      statsRow({
        year,
        month,
        userId: 1,
        name: "Анна",
        rate: 300,
        planHours: 24,
        factHours: 22,
        // Как отдает сервер: правка 2 числа без отметки (09:00–22:00, 13 часов) и отметка 1 числа; новые сверху.
        marks: [
          { started_at: `${year}-${mm}-02T06:00:00Z`, ended_at: `${year}-${mm}-02T19:00:00Z`, duration_seconds: 13 * 3600, manual: true },
          { started_at: `${year}-${mm}-01T05:50:00Z`, ended_at: `${year}-${mm}-01T10:00:00Z`, duration_seconds: 4 * 3600 + 600 },
        ],
      }),
    ],
  });
  const html = admin.renderWorkScheduleContent();
  const table = html.match(/<table class="ws__summary wst-marks__table">[\s\S]*?<\/table>/)?.[0] ?? "";
  const stamp = (d, time) => `<span class="wst-marks__date">${String(d).padStart(2, "0")}-${mm}-${year}</span> ${time}`;
  assert.match(
    table,
    new RegExp(
      `<tr class="wst-marks__row" title="Ручная правка факта: в статистике день считается по ней, а не по отметкам"><td>Анна<span class="wst-marks__manual">вручную</span></td><td>${stamp(2, "09:00:00")}</td><td>${stamp(2, "22:00:00")}</td><td>13:00:00</td></tr>`,
    ),
  );
  assert.match(table, new RegExp(`<tr class="wst-marks__row"><td>Анна</td><td>${stamp(1, "08:50:00")}</td><td>${stamp(1, "13:00:00")}</td><td>04:10:00</td></tr>`));
  assert.doesNotMatch(table, /wst-marks__row--long/, "правка длиннее 12 часов не красная: это не отметка");
  assert.equal((table.match(/вручную/g) || []).length, 1, "подпись только у правки");
  assert.match(stylesSource, /\.wst-marks__manual \{/);
});

test("статистику открывают врач и оператор сами; админу без выбранного сотрудника — нет", () => {
  const doctor = loadSchedule("doctor", 2);
  doctor.wsState.statsOpen = true;
  assert.equal(doctor.wsStatsReady(), true);
  const admin = loadSchedule("admin");
  admin.wsState.statsOpen = true;
  assert.equal(admin.wsStatsReady(), false, "админу нужен выбранный сотрудник");
  admin.wsState.selectedUserId = 1;
  assert.equal(admin.wsStatsReady(), true);
  admin.wsState.statsOpen = false;
  assert.equal(admin.wsStatsReady(), false, "закрытая статистика не грузится");
});

test("деньги: ставку и суммы видит только админ", () => {
  assert.equal(loadSchedule("admin").wsCanSeeMoney(), true);
  assert.equal(loadSchedule("doctor", 2).wsCanSeeMoney(), false);
  assert.equal(loadSchedule("operator", 3).wsCanSeeMoney(), false);
});

test("отчет «Сформировать месяц»: врачу и оператору без ставки и сумм, админу — с колонками денег", () => {
  const { year, month } = currentMonth();
  const stats = sampleStats({
    year,
    month,
    rows: [statsRow({ year, month, userId: 2, name: "Борис", rate: null, planHours: 12, factHours: 0.97 })],
  });
  const doctorReport = loadSchedule("doctor", 2).wsMonthReportHtml(stats);
  assert.match(doctorReport, /Борис/);
  assert.doesNotMatch(doctorReport, /Ставка|сумма|₽/i);
  assert.match(doctorReport, /<td colspan="5">Итого<\/td>/);

  const adminReport = loadSchedule("admin").wsMonthReportHtml(stats);
  assert.match(adminReport, /Ставка, ₽\/ч/);
  assert.match(adminReport, /Факт: сумма/);
  assert.match(adminReport, /<td colspan="6">Итого<\/td>/);
});

test("печать и статистика в коде: врачу и оператору открыты, правка и деньги — только админу", () => {
  assert.match(scheduleSource, /async function openWsMonthReport\(\) \{\s*if \(!wsCanOpen\(\)\) return;/);
  assert.match(scheduleSource, /async function loadWorkStats\(\) \{\s*if \(!wsCanOpen\(\)\) return null;/);
  assert.match(scheduleSource, /function wsToggleStats\(\) \{\s*if \(!wsCanOpen\(\)\) return;\s*if \(wsIsAdmin\(\) && !wsState\.selectedUserId\) \{/);
  assert.match(scheduleSource, /function wsToggleEdit\(\) \{\s*if \(!wsIsAdmin\(\)\) return;/);
  assert.match(scheduleSource, /async function wsCreateSchedule\(\) \{\s*if \(!wsIsAdmin\(\) \|\| wsState\.busy\) return;/);
});

test("таблица: админ в режиме «Редактировать» видит все кнопки и может нажать на день", () => {
  const { wsState, renderWorkScheduleContent } = loadSchedule("admin");
  const { year, month } = currentMonth();
  wsState.grid = sampleGrid({ year, month });
  wsState.mode = "edit";
  const html = renderWorkScheduleContent();
  assert.match(html, /data-ws-cell/);
  assert.match(html, /data-ws-name="1"/);
  assert.match(html, /Создать график/);
  assert.match(html, /Сформировать месяц/);
  assert.match(html, /Закрыть редактирование/);
});

test("вкладки медцентров: каждый медцентр своя вкладка, активный отмечен, пустой медцентр тоже вкладка", () => {
  const { wsRenderCenterTabs } = loadSchedule();
  const centers = [
    { id: 1, name: "Мед-Авто", color: "#2F6FB3" },
    { id: 2, name: "Медилэнд", color: "#2E9E6A" },
    { id: 3, name: "Здравница", color: "#D9822B" },
  ];
  const html = wsRenderCenterTabs(centers, 2);
  for (const center of centers) {
    assert.match(html, new RegExp(`data-ws-center="${center.id}"`), center.name);
  }
  assert.match(html, /class="ws__tab is-active" type="button" aria-pressed="true" data-ws-center="2"/);
  assert.equal((html.match(/is-active/g) || []).length, 1, "активна одна вкладка");
  assert.match(wsRenderCenterTabs([], 1), /Медцентры не назначены/);
});

test("пустой медцентр: вкладка есть, таблица говорит, что сотрудников пока нет, админу — куда добавить", () => {
  const { wsState, renderWorkScheduleContent } = loadSchedule("admin");
  const empty = { id: 3, name: "Здравница", color: "#D9822B" };
  const grid = sampleGrid(currentMonth());
  grid.center = empty;
  grid.centers = [{ id: 1, name: "Мед-Авто", color: "#2F6FB3" }, empty];
  grid.rows = [];
  wsState.grid = grid;
  wsState.centers = grid.centers;
  wsState.centerId = empty.id;
  const html = renderWorkScheduleContent();
  assert.match(html, /class="ws__tab is-active" type="button" aria-pressed="true" data-ws-center="3"/);
  assert.match(html, /В этом медцентре пока нет сотрудников/);
  assert.match(html, /Добавьте их в разделе «Сотрудники»/);
});

test("пересечение смен: день в двух медцентрах красный, в подсказке назван второй медцентр", () => {
  const { wsState, renderWorkScheduleContent, wsConflictText } = loadSchedule("admin");
  const grid = sampleGrid(currentMonth());
  grid.rows[0].days[0].conflicts = [{ center_id: 3, center_name: "Здравница", start_time: "09:00", end_time: "21:00" }];
  wsState.grid = grid;
  wsState.centers = grid.centers;
  wsState.centerId = grid.center.id;
  const html = renderWorkScheduleContent();
  assert.match(html, /<td class="ws__cell[^"]*is-conflict[^"]*"/, "клетка с пересечением красная");
  assert.equal((html.match(/is-conflict/g) || []).length, 1, "только одна клетка с пересечением");
  assert.match(html, /Здравница 09:00–21:00/, "подсказка называет второй медцентр");
  assert.match(html, /ws__key--conflict/, "в легенде есть ключ красного цвета");
  assert.equal(wsConflictText({ conflicts: [] }), "");
  assert.equal(wsConflictText({}), "");
});

test("запросы графика называют медцентр таблицы: правка, отпуск, первая смена, факт, месяц и статистика", () => {
  const { wsState, wsCenterQuery, wsWithCenter, wsStatsKey } = loadSchedule("admin");
  wsState.grid = { center: { id: 3, name: "Здравница" }, centers: [] };
  wsState.centerId = 3;
  assert.equal(wsCenterQuery(), "center_id=3");
  assert.equal(wsWithCenter("/work-schedule/7/days/2026-11-05"), "/work-schedule/7/days/2026-11-05?center_id=3");
  wsState.year = 2026;
  wsState.month = 11;
  assert.equal(wsStatsKey(), "2026-11-3", "статистика кэшируется по медцентру");
  wsState.centerId = null;
  wsState.grid = null;
  assert.equal(wsWithCenter("/work-schedule/7/facts"), "/work-schedule/7/facts", "без медцентра путь не меняется");

  for (const name of ["days", "absences", "first-shift", "facts"]) {
    assert.ok(scheduleSource.includes(`wsWithCenter(\`/work-schedule/\${encodeURIComponent(userId)}/${name}`), name);
  }
  assert.ok(scheduleSource.includes("center_id: wsCenterId()"), "«Создать график» — для медцентра таблицы");
  assert.ok(scheduleSource.includes('${query ? `&${query}` : ""}'), "месяц и статистика — с медцентром");
});

test("app.js: меню, загрузка и страница ведут на модуль графика, старой страницы нет", () => {
  assert.match(appSource, /if \(item\.id === "schedule"\) return canViewWorkSchedule\(\);/);
  assert.match(appSource, /\(appState\.page === "schedule" && !canViewWorkSchedule\(\)\) \|\|/);
  assert.match(
    extractFunction("loadPageData"),
    /if \(page === "schedule" && canViewWorkSchedule\(\) && !wsState\.loading\) \{\s*loadWorkSchedule\(\);\s*\}/,
  );
  assert.match(extractFunction("renderContent"), /if \(appState\.page === "schedule"\) return renderWorkScheduleContent\(\);/);
  assert.doesNotMatch(appSource, /renderSchedulePage/);
  assert.doesNotMatch(appSource, /function formatStaffRate\(/);
});

test("app.js: выход сбрасывает график, перерисовка заново вешает его обработчики", () => {
  assert.match(extractFunction("signOutDemoStaff"), /resetWorkSchedule\(\);/);
  assert.match(extractFunction("bindContentEvents"), /bindWorkScheduleEvents\(\);/);
});

test("index.html: модуль графика грузится до app.js, токен у app.js, модуля и стилей один", () => {
  assert.match(indexSource, /<script src="\.\/work-schedule\.js\?v=[\w-]*manual-marks-v1"><\/script>/);
  assert.match(indexSource, /<script src="\.\/app\.js\?v=[\w-]*audit-journal-v1"><\/script>/);
  assert.match(indexSource, /styles\.css\?v=[\w-]*audit-journal-v1/);
  assert.ok(indexSource.indexOf("work-schedule.js?v=") < indexSource.indexOf("app.js?v="), "модуль раньше app.js");
});

test("styles.css: стили таблицы, окна дня и статистики есть", () => {
  assert.match(stylesSource, /\.ws__table \{/);
  assert.match(stylesSource, /\.ws-chart__plan \{/);
  assert.match(stylesSource, /#actionModal\.modal--schedule-day \.modal__card \{/);
  assert.match(stylesSource, /\.ws__tab\.is-active \{/);
  assert.match(stylesSource, /\.ws__cell\.is-conflict \{/);
});

test("API графика: пути совпадают с маршрутами backend", () => {
  for (const path of [
    "/work-schedule/month?year=",
    "/work-schedule/stats?year=",
    "/work-schedule/month/generate",
    "/work-schedule/${encodeURIComponent(userId)}/days/${dateKey}",
    "/work-schedule/${encodeURIComponent(userId)}/absences",
    "/work-schedule/${encodeURIComponent(userId)}/first-shift",
    "/work-schedule/${encodeURIComponent(userId)}/facts",
  ]) {
    assert.ok(scheduleSource.includes(path), path);
  }
});
