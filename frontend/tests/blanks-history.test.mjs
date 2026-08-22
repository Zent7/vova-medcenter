import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(resolve(import.meta.dirname, "../public/demo/blanks-page.js"), "utf8");

function renderHistory({ search = "", forms = [] } = {}) {
  const window = {
    appState: {
      page: "blanks",
      blanksTab: "history",
      blanksHistorySearch: search,
    },
    data: {
      blanksTypes: [
        { code: "driver", name: "Водительская" },
        { code: "gims", name: "ГИМС" },
      ],
      blanksForms: forms,
      blanksStats: [],
      blanksBatches: [],
      blanksLoaded: true,
    },
    escapeHtml(value) {
      return String(value ?? "");
    },
    getWorkspaceCenterName() {
      return "Медцентр 1";
    },
  };

  vm.runInNewContext(source, { window, URLSearchParams, Date });
  return window.renderBlanksPage();
}

test("issued blank history is split into service groups", () => {
  const html = renderHistory({
    forms: [
      {
        id: 1,
        blank_type: "driver",
        full_number: "АА000123",
        status: "issued",
        client_full_name: "Иванов Иван",
        document_label: "Справка водителя",
        issued_at: "2026-08-14T10:00:00Z",
        issued_by_name: "Регистратор",
      },
      {
        id: 2,
        blank_type: "gims",
        full_number: "ГИМС0009",
        status: "issued",
        client_full_name: "Петров Пётр",
        document_label: "Справка ГИМС",
        issued_at: "2026-08-15T10:00:00Z",
      },
      {
        id: 3,
        blank_type: "driver",
        full_number: "АА000124",
        status: "free",
      },
    ],
  });

  assert.match(html, /История выданных документов/);
  assert.match(html, /Водительская/);
  assert.match(html, /ГИМС/);
  assert.match(html, /АА000123/);
  assert.match(html, /ГИМС0009/);
  assert.doesNotMatch(html, /АА000124/);
  assert.match(html, /Найдено: 2/);
});

test("issued blank history search only matches the blank number", () => {
  const html = renderHistory({
    search: "0012",
    forms: [
      {
        id: 1,
        blank_type: "driver",
        full_number: "АА001234",
        status: "issued",
        client_full_name: "Иванов Иван",
      },
      {
        id: 2,
        blank_type: "gims",
        full_number: "ГИМС9999",
        status: "issued",
        client_full_name: "Пациент 0012",
      },
    ],
  });

  assert.match(html, /АА001234/);
  assert.doesNotMatch(html, /ГИМС9999/);
  assert.match(html, /Найдено: 1/);
  assert.doesNotMatch(html, /Документы с таким номером не найдены/);
});

test("issued blank history shows one empty search result", () => {
  const html = renderHistory({
    search: "нет-такого-номера",
    forms: [
      { id: 1, blank_type: "driver", full_number: "АА001234", status: "issued" },
    ],
  });

  assert.match(html, /Найдено: 0/);
  assert.match(html, /Документ с таким номером не найден/);
  assert.doesNotMatch(html, /data-blank-history-group/);
});
