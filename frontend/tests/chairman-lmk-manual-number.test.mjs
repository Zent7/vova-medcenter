import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../public/demo/app.js", import.meta.url), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return source.slice(start, end);
}

function createResolver({ number = "66483001", cachedBlank, pick } = {}) {
  const input = { value: number };
  const selectedPrintBlanks = new Map(cachedBlank ? [["ЛМК", cachedBlank]] : []);
  const picks = [];
  const client = { id: 7 };
  const visit = { id: "encounter-8", backendId: 8 };
  const context = vm.createContext({
    document: { getElementById: () => input },
    client,
    visit,
    selectedPrintBlanks,
    chairmanPrintBlankState: { blanks: selectedPrintBlanks, selectedSeries: "ЛМК" },
    chairmanBlankNumberEdited: true,
    normalizeBlankSeries: value => String(value || "").trim(),
    resolveDriverPrintBlankType: () => "lmk_medical_certificate",
    resolveCenterIdForVisit: async () => 3,
    async pickManualDriverBlank(flowState, requestedNumber) {
      picks.push({ flowState, number: requestedNumber });
      return pick ? await pick(flowState, requestedNumber) : {
        id: 202, series: "ЛМК", full_number: `ЛМК${requestedNumber}`, status: "free",
      };
    },
    formatApiDate: value => value,
  });
  vm.runInContext(sourceBetween("function getDriverPrintBlankParts(", "function normalizeDriverPrintBlank("), context);
  vm.runInContext(sourceBetween(
    "const resolveChairmanPrintBlank = async",
    "chairmanPrintBlankState.resolveBlank = resolveChairmanPrintBlank",
  ) + "\nthis.resolveBlank = resolveChairmanPrintBlank;", context);
  return { context, input, selectedPrintBlanks, picks };
}

test("the LMK typographic number field accepts keyboard input", () => {
  const field = source.match(/<input\b[^>]*\bid="chairmanPrintBlankNumber"[^>]*>/)?.[0];
  assert.ok(field, "LMK number input exists");
  assert.doesNotMatch(field, /\b(?:readonly|disabled)\b/);
});

test("typing another LMK number replaces the cached blank with the exact entered blank", async () => {
  const oldBlank = { id: 101, series: "ЛМК", full_number: "ЛМК66483000", status: "free" };
  const { context, selectedPrintBlanks, picks } = createResolver({ cachedBlank: oldBlank });
  const blank = await context.resolveBlank("ЛМК");
  assert.equal(blank.id, 202);
  assert.equal(selectedPrintBlanks.get("ЛМК"), blank);
  assert.equal(picks.length, 1);
  assert.equal(picks[0].number, "66483001");
  assert.equal(picks[0].flowState.blankType, "lmk_medical_certificate");
  assert.equal(picks[0].flowState.centerId, 3);
  assert.equal(picks[0].flowState.selectedSeries, "ЛМК");
});

test("manual LMK selection preserves leading zeroes", async () => {
  const { context, input, picks } = createResolver({ number: "  00012345  " });
  await context.resolveBlank("ЛМК");
  assert.equal(picks[0].number, "00012345");
  assert.equal(input.value, "00012345");
});

test("an unchanged issued LMK blank can be printed again without selecting it as free", async () => {
  const cachedBlank = { id: 101, series: "ЛМК", full_number: "ЛМК66483001", status: "issued" };
  const { context, picks } = createResolver({ cachedBlank });
  assert.equal(await context.resolveBlank("ЛМК"), cachedBlank);
  assert.equal(picks.length, 0);
});

test("clearing the number discards a previously selected blank", async () => {
  const cachedBlank = { id: 101, full_number: "ЛМК66483000", series: "ЛМК", status: "free" };
  const { context, selectedPrintBlanks, picks } = createResolver({ number: "", cachedBlank });
  assert.equal(await context.resolveBlank("ЛМК"), null);
  assert.equal(selectedPrintBlanks.has("ЛМК"), false);
  assert.equal(picks.length, 0);
});

test("non-numeric input cannot leave an old blank selected", async () => {
  const cachedBlank = { id: 101, full_number: "ЛМК66483000", series: "ЛМК", status: "free" };
  const { context, selectedPrintBlanks, picks } = createResolver({ number: "6648x001", cachedBlank });
  await assert.rejects(context.resolveBlank("ЛМК"));
  assert.equal(selectedPrintBlanks.has("ЛМК"), false);
  assert.equal(picks.length, 0);
});

test("unavailable manual number fails without falling back to the old blank", async () => {
  const cachedBlank = { id: 101, full_number: "ЛМК66483000", series: "ЛМК", status: "free" };
  const { context, selectedPrintBlanks } = createResolver({
    cachedBlank,
    pick: async () => { throw new Error("Бланк уже выдан"); },
  });
  await assert.rejects(context.resolveBlank("ЛМК"), /Бланк уже выдан/);
  assert.equal(selectedPrintBlanks.has("ЛМК"), false);
});

for (const change of ["number", "series", "menu"]) {
  test(`a pending exact lookup cannot overwrite a changed ${change}`, async () => {
    let finish;
    const pending = new Promise(resolve => { finish = resolve; });
    const { context, input, selectedPrintBlanks, picks } = createResolver({ pick: () => pending });
    const resolution = context.resolveBlank("ЛМК");
    // resolveCenterIdForVisit and the lookup each cross a promise boundary.
    for (let i = 0; picks.length === 0 && i < 5; i += 1) await Promise.resolve();
    assert.equal(picks.length, 1);
    if (change === "number") input.value = "66483002";
    if (change === "series") context.chairmanPrintBlankState.selectedSeries = "ДРУГАЯ";
    if (change === "menu") context.chairmanPrintBlankState.blanks = new Map();
    finish({ id: 202, series: "ЛМК", full_number: "ЛМК66483001", status: "free" });
    await assert.rejects(resolution);
    assert.equal(selectedPrintBlanks.has("ЛМК"), false);
    if (change === "number") assert.equal(input.value, "66483002");
  });
}

function prepareAutoLookup(context, request) {
  const requests = [];
  const messages = [];
  Object.assign(context, {
    URLSearchParams,
    certificateTemplateMenu: false,
    getDriverPrintCertificateType: () => "lmk",
    isNumberedCertificatePrintType: () => false,
    isPreenteredBlankSeries: () => true,
    isStrictDriverBlankSeries: () => false,
    canAutoCreateChairmanBlankSeries: () => false,
    normalizeDriverPrintBlank: value => value,
    splitExistingBlankNumber: () => "",
    showToast: message => messages.push(message),
    humanizeApiError: error => error.message,
    async apiRequest(url) {
      requests.push(url);
      return await request(url);
    },
  });
  vm.runInContext(sourceBetween(
    "const findChairmanBlank = async",
    "chairmanPrintBlankState.findBlank = findChairmanBlank",
  ) + "\nthis.findBlank = findChairmanBlank;", context);
  return { requests, messages };
}

for (const outcome of ["success", "failure"]) {
  test(`a late automatic lookup ${outcome} preserves a newer manual selection`, async () => {
    let finish;
    let fail;
    const pending = new Promise((resolve, reject) => { finish = resolve; fail = reject; });
    const { context, input, selectedPrintBlanks } = createResolver();
    const { requests, messages } = prepareAutoLookup(context, () => pending);
    const lookup = context.findBlank("ЛМК");
    for (let i = 0; requests.length === 0 && i < 5; i += 1) await Promise.resolve();
    assert.equal(requests.length, 1);

    // The value remains identical: replacing the selected blank alone must invalidate
    // the outstanding automatic lookup, including its error handler.
    const manualBlank = await context.resolveBlank("ЛМК");
    if (outcome === "success") {
      finish({ id: 303, series: "ЛМК", full_number: "ЛМК66483002", status: "free" });
    } else {
      fail(new Error("Свободные бланки не найдены"));
    }
    assert.equal(await lookup, null);
    assert.equal(selectedPrintBlanks.get("ЛМК"), manualBlank);
    assert.equal(input.value, "66483001");
    assert.deepEqual(messages, []);
  });
}

test("a late automatic result cannot overwrite an unconfirmed keyboard edit", async () => {
  let finish;
  const pending = new Promise(resolve => { finish = resolve; });
  const { context, input, selectedPrintBlanks } = createResolver();
  const { requests, messages } = prepareAutoLookup(context, () => pending);
  const lookup = context.findBlank("ЛМК");
  for (let i = 0; requests.length === 0 && i < 5; i += 1) await Promise.resolve();
  assert.equal(requests.length, 1);
  input.value = "00012345";
  finish({ id: 303, series: "ЛМК", full_number: "ЛМК66483002", status: "free" });
  assert.equal(await lookup, null);
  assert.equal(input.value, "00012345");
  assert.equal(selectedPrintBlanks.has("ЛМК"), false);
  assert.deepEqual(messages, []);
});

test("clearing the number and clicking Find selects the next free blank", async () => {
  const { context, input, selectedPrintBlanks, picks } = createResolver();
  const { requests } = prepareAutoLookup(context, async () => ({
    id: 303, series: "ЛМК", full_number: "ЛМК66483002", status: "free",
  }));
  const inputHandlers = {};
  const buttonHandlers = {};
  input.addEventListener = (event, handler) => { inputHandlers[event] = handler; };
  const button = {
    disabled: false,
    addEventListener(event, handler) { buttonHandlers[event] = handler; },
  };
  Object.assign(context, {
    selectedBlankSeries: "ЛМК",
    actionModalContent: {
      querySelector: () => input,
      querySelectorAll: () => [button],
    },
  });
  vm.runInContext(sourceBetween(
    "const pickChairmanManualBlank = async",
    "// Освобождение номера ЛМК:",
  ), context);
  input.value = "";
  inputHandlers.input();
  await buttonHandlers.click({ currentTarget: button });
  assert.equal(picks.length, 0);
  assert.equal(requests.length, 1);
  assert.match(requests[0], /^\/blanks\/forms\/next\?/);
  assert.equal(selectedPrintBlanks.get("ЛМК").id, 303);
  assert.equal(input.value, "66483002");
  assert.equal(button.disabled, false);
});

function preparePrint(context) {
  const printed = [];
  const errors = [];
  const exam = { id: "exam-123", clientId: 7, visitId: "encounter-8" };
  Object.assign(context, {
    chairmanForm: { dataset: { examId: exam.id } },
    findDoctorExamForDraft: () => exam,
    collectChairmanModalFormValues: () => ({}),
    window: { saveDoctorExam: async () => true, closeDoctorExamCard() {} },
    getClientPool: () => [context.client],
    data: { visits: [context.visit] },
    getChairmanTemplatePrintType: () => "lmk_title",
    getChairmanFormInfo: () => ({ printMode: "document" }),
    opensNumberedCertificatePrintWindow: () => false,
    getChairmanCertificatePrintFlowOptions: () => null,
    isChairmanAutoNumberedPrintKind: () => false,
    isChairmanUnnumberedPrintKind: () => false,
    getChairmanBlankSeriesForPrintKind: () => "ЛМК",
    isNumberedCertificatePrintType: () => false,
    async printDocumentForVisit(type, client, visit, options) {
      printed.push({ type, client, visit, options });
      return { blankNumber: "ЛМК66483001", title: "ЛМК" };
    },
    actionModal: { classList: { add() {} } },
    showToast() {},
    showDocumentTargetError: (_target, message) => errors.push(message),
    humanizeApiError: error => error.message,
    console: { error() {} },
  });
  context.chairmanPrintBlankState.resolveBlank = context.resolveBlank;
  vm.runInContext(sourceBetween("const runChairmanPrint = async", '    printButton.addEventListener("click"') +
    "\nthis.printLmk = runChairmanPrint;", context);
  return { printed, errors };
}

test("printing the LMK book uses the manually entered number's blank id", async () => {
  const { context } = createResolver({
    cachedBlank: { id: 101, series: "ЛМК", full_number: "ЛМК66483000", status: "free" },
  });
  const { printed, errors } = preparePrint(context);
  await context.printLmk("lmk_title", "ЛМК", { disabled: false });
  assert.equal(errors.length, 0);
  assert.equal(printed.length, 1);
  assert.equal(printed[0].options.blankFormId, 202);
});

test("an unavailable manually entered number prevents printing the previously selected blank", async () => {
  const { context } = createResolver({
    cachedBlank: { id: 101, series: "ЛМК", full_number: "ЛМК66483000", status: "free" },
    pick: async () => { throw new Error("Бланк с указанным номером не найден"); },
  });
  const { printed, errors } = preparePrint(context);
  const button = { disabled: false };
  await context.printLmk("lmk_title", "ЛМК", button);
  assert.equal(printed.length, 0);
  assert.ok(errors.some(message => message.includes("не найден")));
  assert.equal(button.disabled, false);
});
