import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(resolve(import.meta.dirname, "../public/demo/blanks-page.js"), "utf8");

// Форма читается через new FormData(form), а настоящий FormData принимает только
// элемент формы — в тестах его заменяет заглушка с готовыми значениями.
class FakeFormData {
  constructor(form) {
    this.values = form?.values || {};
  }

  get(name) {
    return this.values[name] ?? null;
  }
}

function fakeForm(values) {
  return { values };
}

function createWindow({ numbering = null, centerId = 1, saved = null } = {}) {
  const calls = [];
  const listeners = new Map();
  const window = {
    appState: { page: "blanks", blanksTab: "batches", blanksFormOpen: false },
    data: {
      blanksTypes: [],
      blanksBatches: [],
      blanksForms: [],
      blanksStats: [],
      blanksLoaded: true,
      blanksCenterId: centerId,
      blanksLmkNumbering: numbering,
    },
    calls,
    listeners,
    escapeHtml: (value) => String(value ?? ""),
    getWorkspaceCenterName: () => "Медцентр 1",
    resolveWorkspaceCenterId: async () => centerId,
    renderApp: () => {},
    showToast: () => {},
    apiRequest: async (path, options) => {
      calls.push({ path, options });
      return options?.method === "PATCH" ? saved : {};
    },
  };
  return { window, calls, listeners };
}

function runModule(window, listeners) {
  const document = {
    querySelector: () => null,
    querySelectorAll: () => [],
    getElementById: (id) =>
      id === "blanksLmkNumberForm"
        ? { addEventListener: (name, handler) => listeners.set(name, handler) }
        : null,
  };
  vm.runInNewContext(source, {
    window,
    document,
    URLSearchParams,
    Date,
    FormData: FakeFormData,
    Number,
    setTimeout,
  });
}

test("страница бланков показывает последний бумажный и следующий номер", () => {
  const { window, listeners } = createWindow({
    numbering: {
      center_id: 1,
      lmk_certificate_last_number: 391,
      lmk_certificate_next_number: 392,
    },
  });
  runModule(window, listeners);

  const html = window.renderBlanksPage();
  assert.match(html, /Последний выданный номер/);
  assert.match(html, /value="391"/);
  assert.match(html, /Следующая справка получит номер <strong>392<\/strong>/);
});

test("следующий номер берётся с бэкенда, а не считается как бумажный + 1", () => {
  // Бумажный журнал закончился на 391, но справка 392 уже напечатана.
  const { window, listeners } = createWindow({
    numbering: {
      center_id: 1,
      lmk_certificate_last_number: 391,
      lmk_certificate_next_number: 393,
    },
  });
  runModule(window, listeners);

  const html = window.renderBlanksPage();
  assert.match(html, /Следующая справка получит номер <strong>393<\/strong>/);
  assert.doesNotMatch(html, /номер <strong>392<\/strong>/);
});

test("без заданного номера видно, что счёт пойдёт с единицы", () => {
  const { window, listeners } = createWindow({
    numbering: {
      center_id: 1,
      lmk_certificate_last_number: null,
      lmk_certificate_next_number: 1,
    },
  });
  runModule(window, listeners);

  const html = window.renderBlanksPage();
  assert.match(html, /не задан/i);
  assert.match(html, /Следующая справка получит номер <strong>1<\/strong>/);
});

test("сохранение отправляет номер в свой медцентр", async () => {
  const { window, calls, listeners } = createWindow({
    numbering: { center_id: 2, lmk_certificate_last_number: null, lmk_certificate_next_number: 1 },
    centerId: 2,
    saved: { center_id: 2, lmk_certificate_last_number: 391, lmk_certificate_next_number: 392 },
  });
  runModule(window, listeners);
  window.renderBlanksPage();
  window.bindBlanksHandlers();

  const submit = listeners.get("submit");
  assert.ok(submit, "форма нумерации должна слушать отправку");

  await submit({
    preventDefault: () => {},
    currentTarget: fakeForm({ lmk_certificate_last_number: "391" }),
  });

  const saved = calls.find((item) => item.options?.method === "PATCH");
  assert.ok(saved, `PATCH не ушёл: ${JSON.stringify(calls)}`);
  assert.equal(saved.path, "/centers/2/numbering");
  assert.deepEqual(JSON.parse(saved.options.body), { lmk_certificate_last_number: 391 });
  assert.equal(window.data.blanksLmkNumbering.lmk_certificate_next_number, 392);
});

test("пустое поле сбрасывает нумерацию, а мусор в поле не сохраняется", async () => {
  const { window, calls, listeners } = createWindow({
    numbering: { center_id: 1, lmk_certificate_last_number: 391, lmk_certificate_next_number: 392 },
    saved: { center_id: 1, lmk_certificate_last_number: null, lmk_certificate_next_number: 1 },
  });
  runModule(window, listeners);
  window.renderBlanksPage();
  window.bindBlanksHandlers();
  const submit = listeners.get("submit");

  await submit({
    preventDefault: () => {},
    currentTarget: fakeForm({ lmk_certificate_last_number: "" }),
  });
  const reset = calls.find((item) => item.options?.method === "PATCH");
  assert.deepEqual(JSON.parse(reset.options.body), { lmk_certificate_last_number: null });

  calls.length = 0;
  await submit({
    preventDefault: () => {},
    currentTarget: fakeForm({ lmk_certificate_last_number: "39-1" }),
  });
  assert.deepEqual(calls, []);
  assert.match(window.data.blanksLmkNumberError, /целым числом/);
});
