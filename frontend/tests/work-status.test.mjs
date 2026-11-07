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
      renderWstMarksBlock,
      wstFormatStamp,
      wstMarkFlag,
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

test("стили отметок: дата не рвется, красные строки и узкий экран с меньшим шрифтом", () => {
  assert.match(stylesSource, /\.wst-marks-block \{/);
  assert.match(stylesSource, /\.wst-marks__date \{/);
  assert.match(stylesSource, /\.wst-marks__row--open td,\n\.wst-marks__row--long td \{\n  color: var\(--danger\);/);
  assert.match(stylesSource, /@media \(max-width: 560px\) \{\n  table\.wst-marks__table \{\n    font-size: 13px;/);
});

test("время в отметках: по Москве с секундами; открытая и длиннее 12 часов — красным", () => {
  const { wstFormatStamp, wstMarkFlag } = loadStatus();

  assert.equal(wstFormatStamp("2026-11-07T04:45:17Z"), "07-11-2026 07:45:17", "дд-мм-гггг чч:мм:сс по московскому времени");
  assert.equal(wstFormatStamp("не дата"), "");
  assert.equal(wstMarkFlag({ started_at: "2026-11-07T04:45:17Z", ended_at: null, duration_seconds: 300 }), "open");
  assert.equal(wstMarkFlag({ ended_at: "2026-11-07T06:00:00Z", duration_seconds: 12 * 3600 }), "", "ровно 12 часов — обычная строка");
  assert.equal(wstMarkFlag({ ended_at: "2026-11-07T06:00:00Z", duration_seconds: 12 * 3600 + 1 }), "long");
  assert.equal(wstMarkFlag({ ended_at: "2026-11-07T06:00:00Z", duration_seconds: 900 }), "");
});

test("блок отметок: новые сверху, красные строки; открытая отметка тикает только в статусе", () => {
  const { renderWstMarksBlock } = loadStatus();
  const marks = [
    { started_at: "2026-11-07T04:45:17Z", ended_at: null, duration_seconds: 43548 },
    { started_at: "2026-11-06T04:43:44Z", ended_at: "2026-11-06T17:09:18Z", duration_seconds: 44734 },
    { started_at: "2026-11-03T14:21:59Z", ended_at: "2026-11-03T14:35:51Z", duration_seconds: 832 },
  ];

  const live = renderWstMarksBlock("Отметки за месяц", marks, { live: true });
  assert.match(live, /<h4>Отметки за месяц<\/h4>/);
  assert.match(live, /<tr class="wst-marks__row wst-marks__row--open"/);
  assert.match(live, /<tr class="wst-marks__row wst-marks__row--long"/);
  assert.equal((live.match(/wst-marks__row--/g) || []).length, 2, "красных строк две: открытая и длиннее 12 часов");
  assert.match(live, /<th>Длит\.<\/th>/);
  assert.match(live, /<td><span class="wst-marks__date">07-11-2026<\/span> 07:45:17<\/td><td>на работе<\/td><td><span data-wst-mark-elapsed>12:05:48<\/span><\/td>/);
  assert.match(live, /<td><span class="wst-marks__date">06-11-2026<\/span> 07:43:44<\/td><td><span class="wst-marks__date">06-11-2026<\/span> 20:09:18<\/td><td>12:25:34<\/td>/);
  assert.match(live, /<td><span class="wst-marks__date">03-11-2026<\/span> 17:21:59<\/td><td><span class="wst-marks__date">03-11-2026<\/span> 17:35:51<\/td><td>00:13:52<\/td>/);
  assert.ok(live.indexOf("07-11-2026") < live.indexOf("06-11-2026") && live.indexOf("06-11-2026") < live.indexOf("03-11-2026"), "новые сверху");

  const plain = renderWstMarksBlock("Отметки «На работу»", [marks[0]]);
  assert.doesNotMatch(plain, /data-wst-mark-elapsed/, "в статистике админа открытая строка не тикает");
  assert.match(plain, /<td>12:05:48<\/td>/);
  assert.match(renderWstMarksBlock("Отметки", []), /За этот месяц отметок нет\./);
});

test("статус: под графиком блок «Отметки за месяц» из ответа сервера; счетчик обновляет открытую строку", () => {
  const { wstState, renderStatusContent } = loadStatus();
  wstState.data = payload({
    open: { started_at: "2026-11-07T04:45:17Z", elapsed_seconds: 300 },
    marks: [{ started_at: "2026-11-07T04:45:17Z", ended_at: null, duration_seconds: 300 }],
  });

  const html = renderStatusContent();
  assert.match(html, /<h4>Отметки за месяц<\/h4>/);
  assert.match(html, /wst-marks__row--open/);
  assert.match(html, /data-wst-mark-elapsed/);
  assert.match(statusSource, /document\.querySelectorAll\("\[data-wst-mark-elapsed\]"\)/);

  wstState.data = payload();
  assert.match(renderStatusContent(), /За этот месяц отметок нет\./);
});
