import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Журнал изменений графика (audit-journal.js): подписи записей, время по Москве, фильтры,
// экранирование и доступ только админу. Функции берутся из файла как есть; wsEscape — из
// work-schedule.js, который грузится раньше. Связка со страницей проверяется по app.js и index.html.

const testDir = dirname(fileURLToPath(import.meta.url));
const demoDir = resolve(testDir, "../public/demo");
const read = (name) => readFileSync(resolve(demoDir, name), "utf8").replace(/\r\n/g, "\n");
const journalSource = read("audit-journal.js");
const scheduleSource = read("work-schedule.js");
const appSource = read("app.js");
const indexSource = read("index.html");
const stylesSource = read("styles.css");

function loadJournal(roleCode = "admin") {
  return new Function(
    `const appState = { auth: { roleCode: ${JSON.stringify(roleCode)} } };\n${scheduleSource}\n${journalSource}\nreturn {
      ajState,
      ajFormatWhen,
      ajDescribe,
      ajStaffLabel,
      ajFilteredEntries,
      renderJournalContent,
      resetAuditJournal,
      canViewAuditJournal,
    };`,
  )();
}

function entry(overrides = {}) {
  return {
    id: 1,
    user_id: 10,
    user_name: "Евгений",
    entity_type: "staff_schedule",
    entity_id: 5,
    entity_name: "Борис Врачов",
    action: "rate_update",
    center_id: 1,
    payload_json: { staff: "Борис Врачов", before: 300, after: 320 },
    created_at: "2026-11-06T20:57:54+00:00",
    ...overrides,
  };
}

test("время записи показывается по Москве, и без пояса тоже", () => {
  const { ajFormatWhen } = loadJournal();
  assert.equal(ajFormatWhen("2026-11-06T20:57:54+00:00"), "06.11.2026 23:57");
  assert.equal(ajFormatWhen("2026-11-06T20:57:54"), "06.11.2026 23:57");
  assert.equal(ajFormatWhen("2026-11-06T20:57:54.123456+00:00"), "06.11.2026 23:57");
  assert.equal(ajFormatWhen("2026-11-06T21:05:00+03:00"), "06.11.2026 21:05");
});

test("каждое действие описывается по-русски из своих полей", () => {
  const { ajDescribe } = loadJournal();
  const describe = (action, payload) => ajDescribe(entry({ action, payload_json: payload }));
  assert.equal(
    describe("schedule_update", { before: "2/2, 09:00-20:00", after: "3/3, 08:00-20:00" }),
    "2/2, 09:00-20:00 → 3/3, 08:00-20:00",
  );
  assert.equal(describe("rate_update", { before: null, after: 320 }), "не задана → 320 ₽/ч");
  assert.equal(
    describe("day_update", {
      date: "2026-11-05",
      before: { kind: "shift", start: "09:00", end: "20:00" },
      after: { kind: "dayoff", start: null, end: null },
    }),
    "05.11.2026: смена 09:00-20:00 → отгул",
  );
  assert.equal(
    describe("day_clear", { date: "2026-11-06", before: { kind: "vacation", start: null, end: null } }),
    "06.11.2026: был отпуск, стало пусто",
  );
  assert.equal(
    describe("absence_add", { kind: "vacation", from: "2026-11-10", to: "2026-11-12", days: 3 }),
    "отпуск с 10.11.2026 по 12.11.2026, дней изменено: 3",
  );
  assert.equal(
    describe("first_shift", { work_date: "2026-11-03", anchor_before: "2026-11-01", created: 12 }),
    "03.11.2026, было 01.11.2026, создано смен: 12",
  );
  assert.equal(describe("month_generate", { year: 2026, month: 11, created: 27 }), "за 11.2026, создано смен: 27");
  assert.equal(
    describe("facts_update", { items: [{ date: "2026-11-04", before: null, after: "09:00-21:00" }] }),
    "04.11.2026: по отметкам → 09:00-21:00",
  );
  assert.equal(
    describe("staff_delete", { schedule: "2/2, 09:00-20:00", hourly_rate: 300 }),
    "был график 2/2, 09:00-20:00, ставка 300 ₽/ч",
  );
  assert.equal(
    describe("schedule_create", { schedule: "2/2, 09:00-20:00", hourly_rate: null }),
    "2/2, 09:00-20:00, ставка не задана",
  );
});

test("имя берется из ответа сервера, а без имени — по номеру учетки", () => {
  const { ajStaffLabel } = loadJournal();
  assert.equal(ajStaffLabel(entry()), "Борис Врачов");
  assert.equal(ajStaffLabel(entry({ entity_name: null })), "Сотрудник #5");
});

test("фильтры по сотруднику и действию сужают список", () => {
  const { ajState, ajFilteredEntries } = loadJournal();
  ajState.entries = [
    entry({ id: 1, action: "rate_update" }),
    entry({ id: 2, action: "day_update", payload_json: { date: "2026-11-05", before: null, after: { kind: "dayoff" } } }),
    entry({ id: 3, entity_name: "Анна Операторова", entity_id: 7, action: "rate_update" }),
  ];
  ajState.staffFilter = "Борис Врачов";
  assert.deepEqual(ajFilteredEntries().map((item) => item.id), [1, 2]);
  ajState.actionFilter = "rate_update";
  assert.deepEqual(ajFilteredEntries().map((item) => item.id), [1]);
  ajState.staffFilter = "";
  assert.deepEqual(ajFilteredEntries().map((item) => item.id), [1, 3]);
});

test("страница экранирует имена и говорит, когда записей нет или фильтр ничего не нашел", () => {
  const { ajState, renderJournalContent } = loadJournal();

  ajState.entries = null;
  assert.match(renderJournalContent(), /Журнал пока не загружен\./);
  ajState.loading = true;
  assert.match(renderJournalContent(), /Загружаем журнал\.\.\./);
  ajState.loading = false;

  ajState.entries = [];
  assert.match(renderJournalContent(), /Записей пока нет\./);

  ajState.entries = [entry({ entity_name: "<img src=x onerror=alert(1)>" })];
  const html = renderJournalContent();
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /06\.11\.2026 23:57/);
  assert.match(html, /Ставка изменена/);

  ajState.staffFilter = "Нет такого";
  assert.match(renderJournalContent(), /По выбранным фильтрам записей нет\./);
});

test("журнал открыт только админу", () => {
  assert.equal(loadJournal("admin").canViewAuditJournal(), true);
  for (const role of ["chairman", "doctor", "operator"]) {
    assert.equal(loadJournal(role).canViewAuditJournal(), false, role);
  }
});

test("выход из программы очищает журнал и отбрасывает ответы прошлого сеанса", () => {
  const { ajState, resetAuditJournal } = loadJournal();
  ajState.entries = [entry()];
  ajState.staffFilter = "Борис Врачов";
  const requestId = ajState.requestId;
  resetAuditJournal();
  assert.equal(ajState.entries, null);
  assert.equal(ajState.staffFilter, "");
  assert.equal(ajState.requestId, requestId + 1);
});

test("index.html: журнал грузится после графика и до app.js, токены app.js и стилей обновлены", () => {
  assert.match(indexSource, /<script src="\.\/audit-journal\.js\?v=[\w-]*fact-from-marks-v1"><\/script>/);
  assert.match(indexSource, /<script src="\.\/app\.js\?v=[\w-]*audit-journal-v1"><\/script>/);
  assert.match(indexSource, /styles\.css\?v=[\w-]*audit-journal-v1/);
  assert.ok(indexSource.indexOf("work-schedule.js?v=") < indexSource.indexOf("audit-journal.js?v="), "график раньше журнала");
  assert.ok(indexSource.indexOf("audit-journal.js?v=") < indexSource.indexOf("app.js?v="), "журнал раньше app.js");
});

test("app.js: пункт «Журнал» только админу, страница, загрузка и сброс подключены", () => {
  assert.match(appSource, /\{ id: "journal", label: "Журнал"/);
  assert.match(appSource, /if \(item\.id === "journal"\) return canViewAuditJournal\(\);/);
  assert.match(appSource, /\(appState\.page === "journal" && !canViewAuditJournal\(\)\) \|\|/);
  assert.match(appSource, /if \(page === "journal" && canViewAuditJournal\(\) && !ajState\.loading\) \{\n    loadAuditJournal\(\);/);
  assert.match(appSource, /if \(appState\.page === "journal"\) return renderJournalContent\(\);/);
  assert.match(appSource, /bindAuditJournalEvents\(\);/);
  assert.match(appSource, /resetAuditJournal\(\);/);
});

test("стили журнала на месте", () => {
  assert.match(stylesSource, /\.aj__head \{/);
  assert.match(stylesSource, /\.aj__table table \{\n  min-width: 720px;/);
});
