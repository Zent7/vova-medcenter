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

// Вырезает объявление функции верхнего уровня целиком, считая скобки.
function extractFunction(name) {
  const start = ["async function " + name + "(", "function " + name + "("]
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
    }
  }
  assert.fail(`Не удалось вырезать объявление ${name}`);
}

// Тест254: ВУ и 071у за один день — две строки журнала и два обращения.
const DRIVER_ENCOUNTER_ID = 12385;
const TRACTOR_ENCOUNTER_ID = 12386;

function createJournalRow(encounterId) {
  return { id: 12420, backendId: 12420, encounterId, referenceNumber: "" };
}

// Копия, которую печать лицевой ВУ кладёт в data.documents: обращение она знает
// только по карточке, серверных отметок об отмене у неё нет.
function createPrintedCopy() {
  return {
    id: 928,
    backendId: 928,
    clientId: 12420,
    visitId: "visit-driver",
    blankFormId: 3796,
    blankNumber: "410000074",
    createdAt: "2026-09-25T06:05:34.000Z",
  };
}

// Та же лицевая в ответе /generated-documents после «Нет» в окне результата печати.
function createSpoiledServerDocument() {
  return {
    id: 928,
    client_id: 12420,
    encounter_id: DRIVER_ENCOUNTER_ID,
    template_id: 1,
    file_name: "водительская лицевая_12420_20260925_060531.xls",
    document_number: "410000074",
    blank_form_id: 3796,
    blank_number_snapshot: "410000074",
    generated_at: "2026-09-25T06:05:34.252514Z",
    cancelled_at: "2026-09-25T06:05:37.612215Z",
    cancelled_reason: "Испорчен при печати",
  };
}

function createJournalContext({ generatedDocuments = [] } = {}) {
  const serverDocuments = { list: generatedDocuments };
  const context = vm.createContext({
    console,
    data: {
      documents: [createPrintedCopy()],
      generatedDocuments: [],
      documentTemplates: [],
      visits: [
        { id: "visit-driver", backendId: DRIVER_ENCOUNTER_ID },
        { id: "visit-tractor", backendId: TRACTOR_ENCOUNTER_ID },
      ],
    },
    serverDocuments,
    async apiRequest(path) {
      return path.startsWith("/generated-documents") ? serverDocuments.list : [];
    },
    buildQuery: () => "",
    buildGeneratedDocumentUrl: (fileName) => fileName,
    getSelectedBackendClientId: () => null,
    getSelectedBackendEncounterId: () => null,
    humanizeApiError: (error) => String(error),
    renderApp() {},
    setTimeout() {},
  });
  vm.runInContext(
    [
      "mapGeneratedDocument",
      "syncLocalDocumentsWithServer",
      "releaseBlankInLoadedDocuments",
      "loadWorkflowData",
      "getDocumentEncounterId",
      "getDashboardBlankNumber",
      "getDashboardCertificateNumber",
    ]
      .map(extractFunction)
      .join("\n"),
    context,
  );
  return context;
}

// Номер справки в строке журнала. Отметки строки с сервера уже перечитаны и
// номера у обращения не знают: его дал бы только документ.
function getRowNumber(context, encounterId) {
  return context.getDashboardCertificateNumber(
    createJournalRow(encounterId),
    { encounterId, blankNumber: "" },
    { rowEncounterId: encounterId },
  );
}

test("напечатанная лицевая сразу даёт строке ВУ номер бланка", () => {
  const context = createJournalContext();

  assert.equal(getRowNumber(context, DRIVER_ENCOUNTER_ID), "410000074");
});

test("бланк, списанный кнопкой «Нет» после лицевой, пропадает из строки ВУ", async () => {
  const context = createJournalContext({ generatedDocuments: [createSpoiledServerDocument()] });

  await context.loadWorkflowData({ clientId: 12420, encounterId: DRIVER_ENCOUNTER_ID });

  assert.equal(context.data.documents[0].cancelledAt, "2026-09-25T06:05:37.612215Z");
  assert.equal(getRowNumber(context, DRIVER_ENCOUNTER_ID), "");
});

// После списания оператор печатает 071у, и во вкладку грузятся документы
// другого обращения — серверной версии лицевой ВУ среди них уже нет.
test("списанный бланк не возвращается в строку ВУ после печати 071у", async () => {
  const context = createJournalContext({ generatedDocuments: [createSpoiledServerDocument()] });

  await context.loadWorkflowData({ clientId: 12420, encounterId: DRIVER_ENCOUNTER_ID });
  context.serverDocuments.list = [];
  await context.loadWorkflowData({ clientId: 12420, encounterId: TRACTOR_ENCOUNTER_ID });

  assert.equal(getRowNumber(context, DRIVER_ENCOUNTER_ID), "");
});

test("номер, освобождённый в разделе «Бланки», пропадает из журнала", () => {
  const context = createJournalContext();
  context.data.generatedDocuments = [
    {
      backendId: 928,
      clientId: 12420,
      encounterId: DRIVER_ENCOUNTER_ID,
      blankFormId: 3796,
      blankNumber: "410000074",
      createdAt: "2026-09-25T06:05:34.252514Z",
    },
  ];

  context.releaseBlankInLoadedDocuments("3796");

  assert.equal(getRowNumber(context, DRIVER_ENCOUNTER_ID), "");
});

test("освобождение чужого номера не трогает бланк строки", () => {
  const context = createJournalContext();

  context.releaseBlankInLoadedDocuments("3797");

  assert.equal(getRowNumber(context, DRIVER_ENCOUNTER_ID), "410000074");
});

// Отметки строки с номером могли прийти между печатью и «Нет»: без повторного
// чтения строка держала бы номер уже списанного бланка.
test("после печати или списания бланка журнал перечитывает отметки строк", async () => {
  const calls = [];
  const visibleRows = [createJournalRow(DRIVER_ENCOUNTER_ID)];
  const context = vm.createContext({
    window: {
      async loadBlanksData(options) {
        calls.push(["blanks", options.force]);
      },
    },
    persistDemoState() {},
    async loadWorkflowData(options) {
      calls.push(["workflow", options.encounterId]);
    },
    async loadDashboardDoctorStatuses(rows) {
      calls.push(["statuses", rows]);
    },
    getVisibleDashboardClients: () => visibleRows,
  });
  vm.runInContext(extractFunction("refreshDocumentWorkflowState"), context);

  await context.refreshDocumentWorkflowState(12420, DRIVER_ENCOUNTER_ID);

  assert.deepEqual(calls, [
    ["workflow", DRIVER_ENCOUNTER_ID],
    ["blanks", true],
    ["statuses", visibleRows],
  ]);
});
