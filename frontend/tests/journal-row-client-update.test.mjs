import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

const OPENERS = { "(": ")", "[": "]", "{": "}" };
const CLOSERS = new Set([")", "]", "}"]);

// Вырезает объявление верхнего уровня целиком, считая скобки.
function extractDeclaration(name) {
  const start = ["function " + name + "(", "const " + name + " ="]
    .map((marker) => appSource.indexOf(marker))
    .find((index) => index >= 0);
  assert.ok(typeof start === "number", `Не найдено объявление ${name}`);

  let depth = 0;
  for (let index = start; index < appSource.length; index += 1) {
    const char = appSource[index];
    if (OPENERS[char]) depth += 1;
    else if (CLOSERS.has(char)) {
      depth -= 1;
      if (depth === 0 && char === "}") return appSource.slice(start, index + 1);
    } else if (char === ";" && depth === 0) return appSource.slice(start, index + 1);
  }
  assert.fail(`Не удалось вырезать объявление ${name}`);
}

// Клиент с ВУ и 071у за один день — две строки журнала. 071у заведена второй,
// журнал идёт новыми сверху, поэтому её строка у клиента первая.
function createJournalRow(encounterId, services) {
  return {
    id: 7,
    backendId: 7,
    dashboardRowId: `encounter-${encounterId}`,
    encounterId,
    encounterStatus: "draft",
    centerId: 1,
    center: "Медцентр 1",
    fullName: "Тест 249",
    services: services.slice(),
    note: "",
    lastVisit: "24.09.2026, 08:02",
    encounterDate: "24.09.2026, 08:02",
    category: "",
    referenceNumber: "",
    rawApiClient: { id: 7, encounter_id: encounterId, services: services.slice() },
  };
}

// Ответ PUT /clients после карточки председателя ВУ: клиент без обращения,
// с категориями водительской справки и всеми услугами из карточки клиента.
function createSavedClient() {
  return {
    id: 7,
    backendId: 7,
    patientNumber: 249,
    dashboardRowId: "client-7",
    encounterId: null,
    encounterStatus: "",
    centerId: null,
    center: "",
    fullName: "Тест 249 Исправленный",
    services: [],
    note: "",
    lastVisit: "",
    encounterDate: "",
    category: "B, M, B1",
    referenceNumber: "",
    rawApiClient: {
      id: 7,
      services: [],
      admission_category: "B, M, B1",
      legacy_payload_json: { services: ["Медицинская комиссия", "071У"] },
    },
  };
}

function createUpsertContext(backendClients) {
  const context = vm.createContext({
    data: { clients: [], backendClients, fullClientsById: {} },
    invalidateClientPool() {},
  });
  vm.runInContext(
    [
      extractDeclaration("normalizeAdmissionServiceNames"),
      extractDeclaration("getClientAdmissionServiceNames"),
      extractDeclaration("mergeFullClientWithDashboardRow"),
      extractDeclaration("mergeClientIntoDashboardRow"),
      extractDeclaration("upsertClientInMemory"),
    ].join("\n"),
    context,
  );
  return context;
}

test("обновлённый клиент не отнимает у строки 071у её обращение", () => {
  const tractorRow = createJournalRow(101, ["071У"]);
  const driverRow = createJournalRow(100, ["Медицинская комиссия"]);
  const context = createUpsertContext([tractorRow, driverRow]);

  context.upsertClientInMemory(createSavedClient());

  const [nextTractorRow, nextDriverRow] = context.data.backendClients;
  assert.equal(context.data.backendClients.length, 2);
  assert.equal(nextTractorRow.encounterId, 101);
  assert.equal(nextTractorRow.dashboardRowId, "encounter-101");
  assert.deepEqual(Array.from(nextTractorRow.services), ["071У"]);
  assert.deepEqual(Array.from(nextTractorRow.rawApiClient.services), ["071У"]);
  assert.equal(nextTractorRow.centerId, 1);
  assert.equal(nextTractorRow.encounterDate, "24.09.2026, 08:02");
  assert.equal(nextDriverRow.encounterId, 100);
  assert.equal(nextDriverRow.dashboardRowId, "encounter-100");
  assert.deepEqual(Array.from(nextDriverRow.services), ["Медицинская комиссия"]);
});

// «Категории» строки берут и услуги клиента из его ответа сервера. Все услуги
// карточки дописали бы строке 071у серию водительской справки.
test("строке 071у не достаются услуги ВУ из карточки клиента", () => {
  const context = createUpsertContext([
    createJournalRow(101, ["071У"]),
    createJournalRow(100, ["Медицинская комиссия"]),
  ]);

  context.upsertClientInMemory(createSavedClient());

  const [nextTractorRow, nextDriverRow] = context.data.backendClients;
  assert.deepEqual(Array.from(context.getClientAdmissionServiceNames(nextTractorRow)), ["071У"]);
  assert.deepEqual(Array.from(context.getClientAdmissionServiceNames(nextDriverRow)), ["Медицинская комиссия"]);
});

test("данные клиента доходят до каждой его строки журнала", () => {
  const context = createUpsertContext([
    createJournalRow(101, ["071У"]),
    createJournalRow(100, ["Медицинская комиссия"]),
  ]);

  context.upsertClientInMemory(createSavedClient());

  context.data.backendClients.forEach((row) => {
    assert.equal(row.fullName, "Тест 249 Исправленный");
    assert.equal(row.rawApiClient.admission_category, "B, M, B1");
  });
});

test("клиент без строк в журнале добавляется одной строкой", () => {
  const context = createUpsertContext([]);

  context.upsertClientInMemory(createSavedClient());

  assert.equal(context.data.backendClients.length, 1);
  assert.equal(context.data.backendClients[0].dashboardRowId, "client-7");
});

function createBlankContext({ generatedDocuments = [], documents = [], visits = [] } = {}) {
  const context = vm.createContext({
    data: { generatedDocuments, documents, visits },
  });
  vm.runInContext(
    [
      extractDeclaration("getDocumentEncounterId"),
      extractDeclaration("getDashboardBlankNumber"),
      extractDeclaration("getDashboardCertificateNumber"),
    ].join("\n"),
    context,
  );
  return context;
}

const driverBlank = { clientId: 7, encounterId: 100, blankNumber: "410000058", createdAt: "2026-09-24T08:10:00" };

test("строка 071у не показывает номер бланка ВУ", () => {
  const context = createBlankContext({ generatedDocuments: [driverBlank] });
  const tractorRow = createJournalRow(101, ["071У"]);
  const status = { encounterId: 101, blankNumber: "" };

  assert.equal(context.getDashboardCertificateNumber(tractorRow, status, { rowEncounterId: 101 }), "");
});

test("строка ВУ показывает свой бланк", () => {
  const context = createBlankContext({ generatedDocuments: [driverBlank] });
  const driverRow = createJournalRow(100, ["Медицинская комиссия"]);
  const status = { encounterId: 100, blankNumber: "" };

  assert.equal(context.getDashboardCertificateNumber(driverRow, status, { rowEncounterId: 100 }), "410000058");
});

// Только что напечатанный документ знает лишь карточку обращения, а не его номер.
test("только что напечатанный бланк ВУ попадает в строку ВУ, а не 071у", () => {
  const context = createBlankContext({
    documents: [{ clientId: 7, visitId: "visit-1", blankNumber: "410000058", createdAt: "2026-09-24T08:10:00" }],
    visits: [
      { id: "visit-1", backendId: 100 },
      { id: "visit-2", backendId: 101 },
    ],
  });

  assert.equal(
    context.getDashboardCertificateNumber(createJournalRow(100, []), null, { rowEncounterId: 100 }),
    "410000058",
  );
  assert.equal(context.getDashboardCertificateNumber(createJournalRow(101, []), null, { rowEncounterId: 101 }), "");
});

test("без строки журнала номер справки — последний бланк клиента", () => {
  const context = createBlankContext({ generatedDocuments: [driverBlank] });

  assert.equal(context.getDashboardCertificateNumber(createJournalRow(101, ["071У"])), "410000058");
});

test("журнал передаёт в номер справки обращение своей строки", () => {
  assert.match(
    extractDeclaration("buildExcelRows"),
    /getDashboardCertificateNumber\(client, status, \{ rowEncounterId: client\.encounterId \}\)/,
  );
});
