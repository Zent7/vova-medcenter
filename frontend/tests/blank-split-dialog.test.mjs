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
  const select = element("1"), input = element("500"), preview = element(), error = element(), cancel = element(), submit = element();
  const launch = element(), rowLaunch = element();
  rowLaunch.dataset = { blankSplit: "1" };
  const form = element();
  form.elements = { batch_id: select, pack_size: input };
  form.querySelector = (selector) => ({ "[data-split-preview]": preview, "[data-split-error]": error, "[data-split-cancel]": cancel })[selector];
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
  return { window, launch, rowLaunch, form, select, input, preview, error, cancel, calls, messages, html: () => modalHtml, closes: () => closes };
}

test("toolbar and row open an in-page form with a partial final pack preview", () => {
  const h = harness();
  h.launch.handlers.click();
  assert.match(h.html(), /Выберите партию/);
  assert.match(h.html(), /name="pack_size"/);
  h.rowLaunch.handlers.click();
  assert.match(h.html(), /value="1" selected/);
  assert.equal(h.preview.textContent, "Количество пачек: 3\nПачка 1: АА0001–АА0500\nПачка 2: АА0501–АА1000\nПачка 3: АА1001–АА1200");
  assert.equal(h.calls.length, 0);
  h.cancel.handlers.click();
  assert.equal(h.closes(), 1);
});

test("invalid size cannot split; one submit sends the chosen party and pack size", async () => {
  let finish;
  const h = harness((_url, options) => options?.method === "POST" ? new Promise((resolve) => { finish = resolve; }) : []);
  h.launch.handlers.click();
  h.input.value = "2.5";
  await h.form.handlers.submit({ preventDefault() {} });
  assert.equal(h.calls.length, 0);
  assert.equal(h.error.hidden, false);
  h.input.value = "300";
  const pending = h.form.handlers.submit({ preventDefault() {} });
  await h.form.handlers.submit({ preventDefault() {} });
  assert.equal(h.calls.length, 1);
  assert.equal(h.calls[0].url, "/blanks/batches/1/parts");
  assert.deepEqual(JSON.parse(h.calls[0].options.body), { pack_size: 300 });
  assert.equal(h.input.disabled, true);
  finish([]);
  await pending;
  assert.equal(h.closes(), 1);
  assert.equal(h.input.disabled, false);
  assert.match(h.messages[0], /Пачка оператора/);
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
