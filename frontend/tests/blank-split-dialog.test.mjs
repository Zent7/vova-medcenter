import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../public/demo/blanks-page.js", import.meta.url), "utf8");

function harness(request = async () => []) {
  const elements = new Map();
  const element = (value = "") => ({
    value, disabled: false, hidden: true, textContent: "", handlers: {},
    addEventListener(event, handler) { this.handlers[event] = handler; },
    focus() {}, replaceChildren() { this.textContent = ""; },
  });
  const select = element("1"), input = element("3"), rangesHost = element(), preview = element(), error = element(), cancel = element(), submit = element();
  const launch = element(), rowLaunch = element();
  rowLaunch.dataset = { blankSplit: "1" };
  const form = element();
  form.elements = { batch_id: select, pack_count: input };
  form.querySelector = (selector) => ({ "[data-split-ranges]": rangesHost, "[data-split-preview]": preview, "[data-split-error]": error, "[data-split-cancel]": cancel })[selector];
  form.querySelectorAll = () => [select, input, cancel, submit];
  const document = {
    getElementById: (id) => elements.get(id),
    querySelector: (selector) => selector === "[data-blanks-open-split]" ? launch : null,
    querySelectorAll: (selector) => selector === "[data-blank-split]" ? [rowLaunch] : [],
  };
  const calls = [], messages = [];
  let modalHtml = "", closes = 0;
  const window = {
    appState: { page: "blanks", blanksTab: "batches" },
    data: { blanksLoaded: true, blanksBatches: [{ id: 1, blank_type: "driver", series: "АА", number_from: 1, number_to: 1200, number_width: 4 }] },
    apiRequest: async (url, options) => { calls.push({ url, options }); return request(url, options); },
    openActionModal: (_title, html) => { modalHtml = html; elements.set("blankBatchSplitForm", form); },
    closeActionModal: () => { closes++; },
    showToast: (text) => messages.push(text),
  };
  vm.runInNewContext(source, { window, document, URLSearchParams, Date });
  window.bindBlanksHandlers();
  const edit = (index, boundary, value) => rangesHost.handlers.input({ target: { dataset: { splitIndex: String(index), splitBoundary: boundary }, value: String(value) } });
  return { window, launch, rowLaunch, form, select, input, rangesHost, edit, preview, error, cancel, calls, messages, html: () => modalHtml, closes: () => closes };
}

test("toolbar and row open a form with the pack count and editable number ranges", () => {
  const h = harness();
  h.launch.handlers.click();
  assert.match(h.html(), /Выберите партию/);
  assert.match(h.html(), /name="pack_count"/);
  h.rowLaunch.handlers.click();
  assert.match(h.html(), /value="1" selected/);
  assert.equal(h.preview.textContent, "Количество пачек: 3\nПачка 1: АА0001–АА0400\nПачка 2: АА0401–АА0800\nПачка 3: АА0801–АА1200");
  assert.match(h.rangesHost.innerHTML, /Номер с/);
  assert.match(h.rangesHost.innerHTML, /Номер по/);
  assert.equal(h.calls.length, 0);
  h.cancel.handlers.click();
  assert.equal(h.closes(), 1);
});

test("invalid count cannot split; one submit sends exactly three edited ranges", async () => {
  let finish;
  const h = harness((_url, options) => options?.method === "POST" ? new Promise((resolve) => { finish = resolve; }) : []);
  h.launch.handlers.click();
  h.input.value = "2.5";
  await h.form.handlers.submit({ preventDefault() {} });
  assert.equal(h.calls.length, 0);
  assert.equal(h.error.hidden, false);
  h.input.value = "3";
  h.input.handlers.input();
  h.edit(0, "number_to", 200);
  h.edit(1, "number_from", 201);
  h.edit(1, "number_to", 700);
  h.edit(2, "number_from", 701);
  const pending = h.form.handlers.submit({ preventDefault() {} });
  await h.form.handlers.submit({ preventDefault() {} });
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].url, "/blanks/batches/1/parts");
  assert.deepEqual(JSON.parse(h.calls[0].options.body), { parts: [
    { number_from: 1, number_to: 200 },
    { number_from: 201, number_to: 700 },
    { number_from: 701, number_to: 1200 },
  ] });
  assert.equal(h.input.disabled, true);
  finish([]);
  await pending;
  assert.equal(h.closes(), 1);
  assert.equal(h.input.disabled, false);
  assert.match(h.messages[0], /Пачка оператора/);
});

test("overlaps, gaps, reversed ranges and numbers outside the party cannot be saved", async () => {
  for (const [index, boundary, value] of [[1, "number_from", 400], [1, "number_from", 402], [0, "number_to", 0], [2, "number_to", 1201], [0, "number_from", ""]]) {
    const h = harness();
    h.rowLaunch.handlers.click();
    h.edit(index, boundary, value);
    await h.form.handlers.submit({ preventDefault() {} });
    assert.equal(h.calls.length, 0);
    assert.equal(h.error.hidden, false);
  }
});

test("non-divisible parties are split into the requested number of packs", () => {
  const h = harness();
  h.window.data.blanksBatches[0].number_to = 10;
  h.rowLaunch.handlers.click();
  assert.equal(h.preview.textContent, "Количество пачек: 3\nПачка 1: АА0001–АА0004\nПачка 2: АА0005–АА0007\nПачка 3: АА0008–АА0010");
  h.input.value = "11";
  h.input.handlers.input();
  assert.equal(h.rangesHost.innerHTML, "");
});

test("API failure stays in the form and permits retry", async () => {
  const h = harness(async () => { throw new Error("Партия уже разбита на пачки"); });
  h.rowLaunch.handlers.click();
  await h.form.handlers.submit({ preventDefault() {} });
  assert.equal(h.closes(), 0);
  assert.equal(h.error.hidden, false);
  assert.match(h.error.textContent, /уже разбита/);
  assert.equal(h.input.disabled, false);
});
