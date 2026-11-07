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
function loadSchedule(roleCode = "admin") {
  const appState = { auth: { roleCode } };
  const canViewWorkSchedule = new Function(
    "appState",
    `${extractFunction("canViewWorkSchedule")}\nreturn canViewWorkSchedule;`,
  )(appState);
  return new Function(
    "appState",
    "canViewWorkSchedule",
    `${scheduleSource}
return {
  appState, wsState, wsCanEdit, wsCanOpen, wsDayValuesToRequest, wsAbsenceRequest, wsFactItemsFromValues,
  wsResolveCreateTarget, wsShiftMonth, wsFormatDateLabel, wsIsWeekend, buildWsHoursChart, wsCellContent,
  wsEscape, renderWorkScheduleContent,
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
    centers: [center],
    rows: [
      {
        user_id: 1, full_name: "Анна", role_code: "operator", role_name: "Оператор", is_active: true,
        center, pattern: "4/4", shift_start: "08:00", shift_end: "20:00", days: [day],
      },
      {
        user_id: 2, full_name: "Борис", role_code: "doctor", role_name: "Врач", is_active: true,
        center, pattern: null, shift_start: null, shift_end: null, days: [],
      },
    ],
  };
}

test("таблица: оператор и врач видят график без правки, без статистики и без денег", () => {
  const { wsState, renderWorkScheduleContent } = loadSchedule("doctor");
  wsState.grid = sampleGrid(currentMonth());
  const html = renderWorkScheduleContent();
  assert.ok(html.indexOf("Анна") > 0 && html.indexOf("Борис") > html.indexOf("Анна"), "порядок строк сохранен");
  assert.doesNotMatch(html, /data-ws-cell/);
  assert.doesNotMatch(html, /data-ws-name/);
  assert.doesNotMatch(html, /Создать график|Сформировать месяц|Статистика|Редактировать/);
  assert.doesNotMatch(html, /₽|ставк/i);
  assert.match(html, /data-ws-month="-1"/);
  assert.match(html, /data-ws-month="1"/);
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
  assert.match(indexSource, /<script src="\.\/work-schedule\.js\?v=[\w-]*fact-from-marks-v1"><\/script>/);
  assert.match(indexSource, /<script src="\.\/app\.js\?v=[\w-]*audit-journal-v1"><\/script>/);
  assert.match(indexSource, /styles\.css\?v=[\w-]*audit-journal-v1/);
  assert.ok(indexSource.indexOf("work-schedule.js?v=") < indexSource.indexOf("app.js?v="), "модуль раньше app.js");
});

test("styles.css: стили таблицы, окна дня и статистики есть", () => {
  assert.match(stylesSource, /\.ws__table \{/);
  assert.match(stylesSource, /\.ws-chart__plan \{/);
  assert.match(stylesSource, /#actionModal\.modal--schedule-day \.modal__card \{/);
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
