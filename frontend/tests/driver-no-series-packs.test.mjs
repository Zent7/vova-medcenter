import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../public/demo/app.js", import.meta.url), "utf8");
const between = (start, end) => source.slice(source.indexOf(start), source.indexOf(end, source.indexOf(start)));
const normalize = (value) => String(value || "").trim();
function harness() {
  const calls = [], messages = [], nodes = new Map();
  let html = "";
  const batch = { id: 74, series: null, number_width: 6, parts: [
    { id: 1, part_no: 1, number_from: 1, number_to: 5, free_count: 5 },
    { id: 2, part_no: 2, number_from: 6, number_to: 10, free_count: 5 },
  ] };
  const context = vm.createContext({
    URLSearchParams, console,
    window: { localStorage: { getItem: () => null, setItem() {}, removeItem() {} } },
    document: { getElementById: (id) => nodes.get(id), querySelectorAll: () => [] },
    appState: { auth: { userId: 5 } },
    data: { documentTemplatesLoaded: true },
    BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE: "driver_medical_certificate",
    BLANK_TYPE_LMK_MEDICAL_CERTIFICATE: "lmk_medical_certificate",
    BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE: "gims_medical_certificate",
    CERTIFICATE_PRINT_SERIES_OPTIONS: [], CERTIFICATE_PRINT_SERIES_OPTION_SET: new Set(),
    ensureVisitsStore() {}, syncVisitToBackend: async () => {},
    getSelectedClient: () => ({ id: 10, fullName: "Тестовый пациент" }),
    getSelectedJournalVisitForClient: () => ({ backendId: 100, centerId: 3 }),
    normalizeBlankSeries: normalize, getBlankSeriesMatchKey: (v) => normalize(v).toLowerCase(),
    getDriverPrintCertificateType: () => "", pickDocumentTemplate: () => ({ id: 1 }),
    resolveCenterIdForVisit: async () => 3, getCenterNameForContext: () => "ПЕРВАЯ ЗДРАВНИЦА",
    resolveDriverPrintBlankType: () => "driver_medical_certificate",
    getStoredDriverPrintSeries: () => "00", setStoredDriverPrintSeries() {},
    isCertificatePrintSeries: () => false, isNumberedCertificatePrintType: () => false,
    isPreenteredBlankSeries: () => false, isPreenteredBlankFlow: () => false,
    canAutoCreateChairmanBlankSeries: () => false,
    resolveNumberedCertificateLookupSeries: normalize,
    escapeHtml: (v) => String(v ?? ""),
    formatApiDate: (v) => String(v || ""),
    renderPrintCenterContext: (name) => `<strong>${name}</strong>`,
    humanizeApiError: (error) => error.message,
    showToast: (message) => messages.push(message),
    apiRequest: async (path) => {
      calls.push(path);
      if (path.startsWith("/blanks/series?")) return [{ series: null, free_count: 10 }];
      if (path.startsWith("/blanks/batches?")) return [batch];
      if (path.startsWith("/blanks/forms/next?")) return { id: 6727, series: null, full_number: "000006" };
      throw new Error(`Unexpected request ${path}`);
    },
    openActionModal(_title, content) {
      html = content;
      nodes.clear();
      for (const [, id] of content.matchAll(/id="([^"]+)"/g)) {
        nodes.set(id, { value: "", handlers: {}, addEventListener(event, handler) { this.handlers[event] = handler; } });
      }
    },
  });
  vm.runInContext([
    between("function isStrictDriverBlankSeries(", "function buildServiceSeriesAbbreviation("),
    between("function getDriverPrintSeriesPickerOptions(", "function closeDriverPrintSeriesPicker("),
    between("function getDriverPrintBlankParts(", "function renderDriverPrintResultPrompt("),
    between("function getBlankBatchPartStorageKey(", "function renderDocumentHistory("),
  ].join("\n"), context);
  return { context, calls, messages, nodes, html: () => html };
}

test("реальное окно печати открывается с пустой серией и двумя пачками Здравницы", async () => {
  const h = harness();
  await h.context.openDriverPrintFlow();
  assert.deepEqual(h.messages, []);
  assert.match(h.html(), /ПЕРВАЯ ЗДРАВНИЦА/);
  assert.match(h.html(), /id="driverBlankSeries"[^>]*value=""/);
  assert.match(h.html(), /id="driverBatchPart"/);
  assert.match(h.html(), /000001–000005/);
  assert.match(h.html(), /000006–000010/);
  assert.match(h.html(), /без серии/);
  assert.ok(h.calls.every((url) => new URL(url, "http://test").searchParams.get("center_id") === "3"));

  h.nodes.get("driverBatchPart").handlers.change({ target: { value: "2" } });
  assert.match(h.html(), /Пачка 2: 000006–000010/);
  await h.nodes.get("driverFindBlank").handlers.click();
  const request = new URL(h.calls.find((url) => url.startsWith("/blanks/forms/next?")), "http://test");
  assert.equal(request.searchParams.get("batch_part_id"), "2");
  assert.equal(request.searchParams.get("series"), "");
  assert.equal(request.searchParams.get("strict_only"), "true");
  assert.equal(request.searchParams.has("auto_create"), false);
  assert.match(h.html(), /id="driverBlankNumber"[^>]*value="000006"/);
});

test("центр обращения и рабочий центр подписаны раздельно при несовпадении", () => {
  const context = vm.createContext({
    getWorkspaceCenterName: () => "ПЕРВАЯ ЗДРАВНИЦА",
    normalizeCenterLookupValue: (value) => value.toLowerCase(),
    escapeHtml: (value) => value,
  });
  vm.runInContext(between("function renderPrintCenterContext(", "async function ensureCentersLoaded("), context);
  assert.match(context.renderPrintCenterContext("Мед-Авто"), /Медцентр обращения:.*Мед-Авто/);
  assert.match(context.renderPrintCenterContext("Мед-Авто"), /Рабочий медцентр: ПЕРВАЯ ЗДРАВНИЦА/);
  assert.doesNotMatch(context.renderPrintCenterContext("ПЕРВАЯ ЗДРАВНИЦА"), /другого медцентра/);
});
