import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Статус «На работу / С работы» (work-status.js): большая кнопка, счетчик времени на работе,
// месячный график план-факт с отпуском на всю высоту. Функции берутся из файла как есть; общие
// помощники месяца и чисел — из work-schedule.js, который грузится раньше. Подключение и связка
// с app.js проверяются по исходникам, потому что модуль работает только вместе с ними.

const testDir = dirname(fileURLToPath(import.meta.url));
const demoDir = resolve(testDir, "../public/demo");
const read = (name) => readFileSync(resolve(demoDir, name), "utf8").replace(/\r\n/g, "\n");
const statusSource = read("work-status.js");
const scheduleSource = read("work-schedule.js");
const appSource = read("app.js");
const indexSource = read("index.html");
const stylesSource = read("styles.css");

function loadStatus() {
  return new Function(
    `${scheduleSource}\n${statusSource}\nreturn {
      wstState,
      wstFormatElapsed,
      wstFormatMark,
      wstElapsedSeconds,
      buildWstChart,
      renderWstChartSvg,
      renderStatusContent,
      resetWorkStatus,
    };`,
  )();
}

function payload(overrides = {}) {
  return {
    year: 2026,
    month: 11,
    days_in_month: 30,
    today: "2026-11-07",
    now: "2026-11-07T07:00:00Z",
    open: null,
    days: [],
    totals: { plan_hours: 0, fact_hours: 0, overtime_hours: 0 },
    ...overrides,
  };
}

test("счетчик показывает часы, минуты и секунды и не уходит ниже нуля", () => {
  const { wstFormatElapsed } = loadStatus();

  assert.equal(wstFormatElapsed(0), "00:00:00");
  assert.equal(wstFormatElapsed(3725), "01:02:05");
  assert.equal(wstFormatElapsed(90061), "25:01:01", "часы больше суток не сбрасываются");
  assert.equal(wstFormatElapsed(-5), "00:00:00");
  assert.equal(wstFormatElapsed("abc"), "00:00:00");
});

test("кнопка: «На работу» без отметки, «С работы» и зеленая, пока открыта отметка", () => {
  const { wstState, renderStatusContent } = loadStatus();
  wstState.data = payload();

  let html = renderStatusContent();
  assert.match(html, /data-wst-toggle/);
  assert.match(html, /<span class="wst__toggle-label">На работу<\/span>/);
  assert.doesNotMatch(html, /wst__toggle is-on/);
  assert.doesNotMatch(html, /data-wst-elapsed/);

  wstState.data = payload({ open: { started_at: "2026-11-07T07:00:00Z", elapsed_seconds: 120 } });
  html = renderStatusContent();
  assert.match(html, /wst__toggle is-on/);
  assert.match(html, /<span class="wst__toggle-label">С работы<\/span>/);
  assert.match(html, /data-wst-elapsed/);
  assert.match(html, /с 10:00/, "отметка показана по московскому времени");
});

test("кнопка заблокирована, пока нет данных или идет запрос", () => {
  const { wstState, renderStatusContent } = loadStatus();

  wstState.data = null;
  assert.match(renderStatusContent(), /data-wst-toggle[^>]*disabled/);

  wstState.data = payload();
  wstState.busy = true;
  assert.match(renderStatusContent(), /data-wst-toggle[^>]*disabled/);
});

test("счетчик идет от старта отметки по часам сервера", () => {
  const { wstState, wstElapsedSeconds } = loadStatus();
  wstState.offsetMs = 0;
  wstState.data = payload({ open: { started_at: new Date(Date.now() - 65000).toISOString(), elapsed_seconds: 0 } });

  const elapsed = wstElapsedSeconds();
  assert.ok(Math.abs(elapsed - 65) < 2, `ожидали около 65 с, получили ${elapsed}`);

  wstState.data = payload();
  assert.equal(wstElapsedSeconds(), 0);
});

test("столбцы месяца: серым план, оранжевым факт в пределах плана, зеленым переработка", () => {
  const { buildWstChart, renderWstChartSvg } = loadStatus();
  const chart = buildWstChart([
    { work_date: "2026-11-03", kind: "shift", plan_hours: 11, fact_hours: 12.5 },
    { work_date: "2026-11-04", kind: "dayoff", plan_hours: 0, fact_hours: 0 },
    { work_date: "2026-11-05", kind: null, plan_hours: 0, fact_hours: 2 },
  ]);

  const [shift, dayoff, extra] = chart.bars;
  assert.equal(chart.yMax, 16);
  assert.equal(shift.inPlan.hours, 11, "оранжевый — до плана");
  assert.equal(shift.overtime.hours, 1.5, "зеленый — сверх плана");
  assert.equal(shift.overtime.height > 0, true);
  assert.equal(dayoff.overtime.hours, 0);
  assert.equal(extra.inPlan.hours, 0, "без плана весь факт — переработка");
  assert.equal(extra.overtime.hours, 2);

  const svg = renderWstChartSvg(chart);
  assert.equal((svg.match(/class="wst-chart__plan"/g) || []).length, 3);
  assert.equal((svg.match(/class="wst-chart__fact"/g) || []).length, 3);
  assert.equal((svg.match(/class="wst-chart__over"/g) || []).length, 2, "зеленый только там, где есть переработка");
});

test("отпуск: отдельная полоса на всю высоту графика в каждый день отпуска", () => {
  const { buildWstChart, renderWstChartSvg } = loadStatus();
  const chart = buildWstChart([
    { work_date: "2026-11-01", kind: "vacation", plan_hours: 0, fact_hours: 0 },
    { work_date: "2026-11-02", kind: "vacation", plan_hours: 0, fact_hours: 0 },
    { work_date: "2026-11-03", kind: "shift", plan_hours: 11, fact_hours: 11 },
  ]);

  const vacations = chart.bars.filter((bar) => bar.vacation);
  assert.equal(vacations.length, 2);
  const fullHeight = chart.height - chart.pad.top - chart.pad.bottom;
  for (const bar of vacations) {
    assert.equal(bar.vacation.height, fullHeight);
    assert.equal(bar.vacation.y, chart.pad.top);
  }
  const svg = renderWstChartSvg(chart);
  assert.equal((svg.match(/class="wst-chart__vacation"/g) || []).length, 2);
});

test("пустой месяц строится без столбцов и без переработки", () => {
  const { buildWstChart, renderWstChartSvg } = loadStatus();
  const chart = buildWstChart([]);

  assert.deepEqual(chart.bars, []);
  assert.equal(chart.yMax, 12);
  assert.doesNotMatch(renderWstChartSvg(chart), /wst-chart__over/);
});

test("сброс при выходе отбрасывает ответы прошлого сеанса и очищает данные", () => {
  const { wstState, resetWorkStatus } = loadStatus();
  wstState.data = payload({ open: { started_at: "2026-11-07T07:00:00Z", elapsed_seconds: 5 } });
  const before = wstState.requestId;

  resetWorkStatus();

  assert.equal(wstState.requestId, before + 1);
  assert.equal(wstState.data, null);
  assert.equal(wstState.timerId, null);
});

test("страница статуса подключена: модуль раньше app.js, токены совпадают, выход и вход обслужены", () => {
  assert.match(indexSource, /<script src="\.\/work-status\.js\?v=[\w-]*work-status-v1"><\/script>/);
  assert.ok(indexSource.indexOf("work-status.js?v=") < indexSource.indexOf("app.js?v="), "модуль раньше app.js");
  assert.ok(indexSource.indexOf("work-schedule.js?v=") < indexSource.indexOf("work-status.js?v="), "график раньше статуса");

  assert.doesNotMatch(appSource, /renderStatusPage/, "заглушка «Статус» убрана");
  assert.match(appSource, /if \(appState\.page === "status"\) return renderStatusContent\(\);/);
  assert.match(appSource, /if \(page === "status"\) \{\s*loadWorkStatus\(\);\s*\}/);
  assert.match(appSource, /bindWorkScheduleEvents\(\);\s*bindWorkStatusEvents\(\);/);
  assert.match(appSource, /data\.editingStaffScheduleId = null;\s*data\.editingStaffEmailId = null;\s*resetWorkSchedule\(\);\s*resetWorkStatus\(\);/);
});

test("стили: кнопка, график статуса и ячейки графика покрупнее", () => {
  assert.match(stylesSource, /\.wst__toggle \{/);
  assert.match(stylesSource, /\.wst__toggle\.is-on \{/);
  assert.match(stylesSource, /\.wst-chart__vacation \{/);
  assert.match(stylesSource, /\.ws__cell \{\n  width: 88px;\n  min-width: 88px;/);
});
