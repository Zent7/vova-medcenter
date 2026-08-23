import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(resolve(import.meta.dirname, "../public/demo/blanks-page.js"), "utf8");

function createWindow({ page = "blanks", blanksLoaded = false, blanksTypes = [] } = {}) {
  const requested = [];
  return {
    requested,
    window: {
      appState: { page, blanksTab: "batches", blanksFormOpen: true },
      data: {
        blanksTypes,
        blanksBatches: [],
        blanksForms: [],
        blanksStats: [],
        blanksLoaded,
      },
      escapeHtml: (value) => String(value ?? ""),
      getWorkspaceCenterName: () => "Медцентр 1",
      resolveWorkspaceCenterId: async () => 1,
      apiRequest: async (path) => {
        requested.push(path);
        return path === "/blanks/types" ? blanksTypes : [];
      },
    },
  };
}

test("blanks module starts its own load when app.js was too early to call it", async () => {
  const { window, requested } = createWindow();

  vm.runInNewContext(source, { window, URLSearchParams, Date });
  await new Promise((done) => setTimeout(done, 0));

  assert.ok(requested.includes("/blanks/types"), "тип бланков должен запрашиваться самим модулем");
});

test("a second loader call does not duplicate the requests of the first one", async () => {
  const { window, requested } = createWindow();

  vm.runInNewContext(source, { window, URLSearchParams, Date });
  // Так делает app.js: loadPageData("blanks") вызывается уже после того, как модуль
  // сам начал загрузку, но пока первый запрос ещё не вернулся.
  await window.loadBlanksData();
  await new Promise((done) => setTimeout(done, 0));

  // Типы, остатки, партии, страница номеров, история и нумерация справок ЛМК.
  assert.equal(requested.length, 6, `лишние запросы: ${requested.join(", ")}`);
});

test("blanks module does not reload data that is already in memory", async () => {
  const { window, requested } = createWindow({ blanksLoaded: true });

  vm.runInNewContext(source, { window, URLSearchParams, Date });
  await new Promise((done) => setTimeout(done, 0));

  assert.deepEqual(requested, []);
});

test("batch form explains an empty blank type list instead of showing a blank select", () => {
  const { window } = createWindow({ blanksLoaded: true });

  vm.runInNewContext(source, { window, URLSearchParams, Date });
  const html = window.renderBlanksPage();

  assert.match(html, /Список типов не загрузился/);
  assert.match(html, /<button type="submit" class="primary-button" disabled>/);
});

test("batch form keeps the real blank types when they are loaded", () => {
  const { window } = createWindow({
    blanksLoaded: true,
    blanksTypes: [{ code: "lmk_medical_certificate", name: "ЛМК" }],
  });

  vm.runInNewContext(source, { window, URLSearchParams, Date });
  const html = window.renderBlanksPage();

  assert.match(html, /<option value="lmk_medical_certificate">ЛМК<\/option>/);
  assert.doesNotMatch(html, /Список типов не загрузился/);
});

test("section reports loading instead of pretending the center has no batches", () => {
  const { window } = createWindow();

  vm.runInNewContext(source, { window, URLSearchParams, Date });
  const html = window.renderBlanksPage();

  assert.match(html, /Загрузка данных по бланкам/);
  assert.doesNotMatch(html, /Партий пока нет/);
});
