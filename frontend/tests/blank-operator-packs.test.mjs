import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const source = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");
const helperSource = source.slice(source.indexOf("function getBlankBatchPartStorageKey("), source.indexOf("async function openDriverPrintFlow("));
const DRIVER = "driver_medical_certificate";
const LMK = "lmk_medical_certificate";
const normalize = (value) => String(value || "").trim();

function harness(request = async () => []) {
  const appState = { auth: { userId: 10 } };
  const storage = new Map();
  const window = { localStorage: { getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) } };
  const helpers = new Function("appState", "window", "apiRequest", "resolveNumberedCertificateLookupSeries", "getBlankSeriesMatchKey", "normalizeBlankSeries", "normalizeDriverPrintBlank", "isStrictDriverBlankSeries", "escapeHtml", "BLANK_TYPE_LMK_MEDICAL_CERTIFICATE", `${helperSource}\nreturn { getBlankBatchPartStorageKey, storeBlankBatchPart, getDriverFlowBatchPartId, applyDriverFlowBatchPart, loadDriverFlowBatchParts, pickManualDriverBlank, renderDriverFlowBatchControls };`)(
    appState, window, request, (series) => normalize(series), (series) => normalize(series).toLowerCase(), normalize, (form) => form, () => false, (value) => value, LMK,
  );
  return { ...helpers, appState, storage };
}

function state(extra = {}) {
  return { selectedSeries: "41", selectedCertificateType: "", seriesOptions: [], centerId: 1, blankType: DRIVER, batchParts: [], batchPartId: null, ...extra };
}

function batches() {
  return [{ id: 1, series: "41", parts: [
    { id: 11, part_no: 1, number_from: 1, number_to: 500, free_count: 0 },
    { id: 12, part_no: 2, number_from: 501, number_to: 1000, free_count: 499 },
  ] }];
}

test("пачка запоминается отдельно для сотрудника, центра, типа и серии", () => {
  const h = harness();
  const original = state({ batchPartId: 11 });
  h.storeBlankBatchPart(original);
  const key = h.getBlankBatchPartStorageKey(original);
  assert.equal(h.storage.get(key), "11");
  for (const changed of [state({ centerId: 2 }), state({ blankType: LMK }), state({ selectedSeries: "77" })]) {
    assert.notEqual(h.getBlankBatchPartStorageKey(changed), key);
    assert.equal(h.storage.get(h.getBlankBatchPartStorageKey(changed)), undefined);
  }
  h.appState.auth.userId = 20;
  assert.notEqual(h.getBlankBatchPartStorageKey(original), key);
});

test("исчерпанная пачка остаётся выбранной после повторного открытия", async () => {
  const h = harness(async () => batches());
  h.storeBlankBatchPart(state({ batchPartId: 11 }));
  const reopened = state();
  await h.loadDriverFlowBatchParts(reopened);
  assert.equal(h.getDriverFlowBatchPartId(reopened), 11);
  const query = new URLSearchParams({ auto_create: "true" });
  h.applyDriverFlowBatchPart(query, reopened);
  assert.equal(query.get("batch_part_id"), "11");
  assert.equal(query.has("auto_create"), false);
});

test("без выбора и после удаления старой пачки нельзя перейти в чужую автоматически", async () => {
  const h = harness(async () => batches());
  for (const previousPart of [null, 99]) {
    h.storeBlankBatchPart(state({ batchPartId: previousPart }));
    const reopened = state();
    await h.loadDriverFlowBatchParts(reopened);
    assert.equal(h.getDriverFlowBatchPartId(reopened), null);
    assert.throws(() => h.applyDriverFlowBatchPart(new URLSearchParams(), reopened), /Выберите свою пачку/);
  }
});

test("для ЛМК доступны пачки партий без серии и с произвольной серией", async () => {
  const h = harness(async () => [
    { id: 1, series: null, parts: [{ id: 11 }] },
    { id: 2, series: "77", parts: [{ id: 22 }] },
  ]);
  const lmk = state({ selectedSeries: "ЛМК", blankType: LMK });
  await h.loadDriverFlowBatchParts(lmk);
  assert.deepEqual(lmk.batchParts.map((part) => part.id), [11, 22]);
});

test("ошибка загрузки пачек блокирует подбор номера без ограничения диапазона", async () => {
  const h = harness(async () => { throw new Error("network unavailable"); });
  const flow = state();
  await h.loadDriverFlowBatchParts(flow);
  assert.throws(() => h.applyDriverFlowBatchPart(new URLSearchParams(), flow), /Не удалось загрузить пачки/);
  assert.throws(() => h.applyDriverFlowBatchPart(new URLSearchParams(), state({ batchPartsLoading: true })), /Дождитесь/);
});

test("ответ старого запроса серий не заменяет пачки новой выбранной серии", async () => {
  let completeOld;
  let calls = 0;
  const h = harness(async () => ++calls === 1 ? new Promise((resolve) => { completeOld = resolve; }) : [{ id: 2, series: "77", parts: [{ id: 22 }] }]);
  const flow = state();
  const oldLoad = h.loadDriverFlowBatchParts(flow);
  flow.selectedSeries = "77";
  await h.loadDriverFlowBatchParts(flow);
  completeOld(batches());
  await oldLoad;
  assert.deepEqual(flow.batchParts.map((part) => part.id), [22]);
  assert.equal(flow.batchPartsLoading, false);
});

test("ручной номер проверяется в выбранной пачке перед записью в историю", async () => {
  const calls = [];
  const h = harness(async (url, options) => {
    calls.push({ url, options });
    return { id: 42, full_number: "41000502", batch_part_id: 12 };
  });
  const flow = state({ batchParts: batches()[0].parts, batchPartId: 12 });
  const blank = await h.pickManualDriverBlank(flow, "000502");
  const exact = new URL(calls[0].url, "http://test");
  assert.equal(exact.pathname, "/blanks/forms/exact");
  assert.equal(exact.searchParams.get("batch_part_id"), "12");
  assert.equal(exact.searchParams.get("number"), "000502");
  assert.equal(calls[1].url, "/blanks/forms/42/manual-pick");
  assert.equal(calls[1].options.method, "POST");
  assert.equal(blank.batch_part_id, 12);
});

test("при неверном номере история успешного ручного выбора не записывается", async () => {
  const calls = [];
  const h = harness(async (url) => { calls.push(url); throw new Error("Номер не найден в выбранной пачке"); });
  await assert.rejects(h.pickManualDriverBlank(state({ batchParts: batches()[0].parts, batchPartId: 12 }), "999999"), /не найден/);
  assert.equal(calls.length, 1);
});

test("пачки без серии загружаются для выбранного центра и не смешиваются с другими сериями", async () => {
  const requests = [];
  const h = harness(async (url) => {
    requests.push(url);
    return [{ id: 74, series: null, parts: [{ id: 2, part_no: 2, number_from: 6, number_to: 10, free_count: 5 }] }, ...batches()];
  });
  const flow = state({ centerId: 3, selectedSeries: "" });
  await h.loadDriverFlowBatchParts(flow);
  assert.equal(new URL(requests[0], "http://test").searchParams.get("center_id"), "3");
  assert.deepEqual(flow.batchParts.map((part) => part.id), [2]);
  flow.batchPartId = 2;
  h.storeBlankBatchPart(flow);
  const reopened = state({ centerId: 3, selectedSeries: "" });
  await h.loadDriverFlowBatchParts(reopened);
  assert.equal(h.getDriverFlowBatchPartId(reopened), 2);
  const html = h.renderDriverFlowBatchControls(reopened);
  assert.match(html, /Пачка оператора/);
  assert.match(html, /без серии/);
  assert.match(html, /000006–000010/);
  assert.match(html, /Свободно: 5/);
});

test("пустой список пачек виден с пояснением, а не исчезает из окна печати", () => {
  const html = harness().renderDriverFlowBatchControls(state());
  assert.match(html, /aria-label="Пачка оператора"[^>]*disabled/);
  assert.match(html, /Пачек для этой серии нет/);
  assert.match(html, /Бланки.*Пачки/);
});
