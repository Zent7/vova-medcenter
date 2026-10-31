import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../public/demo/blanks-page.js", import.meta.url), "utf8");
function render(batches) {
  const window = {
    appState: { page: "blanks", blanksTab: "packs" },
    data: { blanksLoaded: true, blanksBatches: batches, blanksTypes: [{ code: "driver", name: "Водительская" }] },
    getWorkspaceCenterName: () => "ПЕРВАЯ ЗДРАВНИЦА",
    escapeHtml: (value) => String(value ?? "").replaceAll("<", "&lt;"),
  };
  vm.runInNewContext(source, { window, URLSearchParams, Date });
  return window.renderBlanksPage();
}
test("отдельная вкладка показывает пачки без серии, диапазоны и исчерпанные остатки", () => {
  const html = render([{ id: 74, blank_type: "driver", series: null, number_width: 6, comment: "<test>", parts: [
    { part_no: 1, number_from: 1, number_to: 5, free_count: 0, issued_count: 5 },
    { part_no: 2, number_from: 6, number_to: 10, free_count: 5, issued_count: 0 },
  ] }]);
  assert.match(html, /data-blanks-tab="packs">Пачки/);
  assert.match(html, /000001–000005/);
  assert.match(html, /000006–000010/);
  assert.match(html, /Свободно: <strong>0/);
  assert.match(html, /без серии/);
  assert.match(html, /&lt;test>/);
});
test("пустая вкладка объясняет, как создать пачки", () => {
  const html = render([]);
  assert.match(html, /В этом медцентре пачек пока нет/);
  assert.match(html, /Разбить на пачки/);
});
