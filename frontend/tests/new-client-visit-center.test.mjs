import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Обращение идёт в медцентр, в базе которого лежит клиент, а не в рабочий центр переключателя.
// Раньше клиент, отмеченный только в Медилэнд, вместе с первой услугой попадал в базу Мед-Авто:
// обращение добавляет клиента в свой центр, а бланки и шаблоны печати брались у рабочего центра.
// Рабочий центр остаётся, если клиент лежит и в нём; клиент без известных центров — как раньше.

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const indexHtml = readFileSync(resolve(testDir, "../public/demo/index.html"), "utf8");

function extractFrom(source, name) {
  const start = source.search(new RegExp(`(async )?function ${name}\\(`));
  assert.ok(start >= 0, `Не найдена функция ${name}`);
  let depth = 0;
  for (let index = source.indexOf("{", source.indexOf(")", start)); index < source.length; index += 1) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) return source.slice(start, index + 1);
    }
  }
  assert.fail(`Не удалось вырезать функцию ${name}`);
}

const WORKSPACE_CENTER_NAMES = ["Мед-Авто", "Медилэнд", "ПЕРВАЯ ЗДРАВНИЦА"];
const CENTERS = [
  { id: 1, name: "Мед-Авто" },
  { id: 2, name: "Медилэнд" },
  { id: 3, name: "ПЕРВАЯ ЗДРАВНИЦА" },
];

const FUNCTIONS = [
  "getLocalDateInputValue",
  "normalizeCenterLookupValue",
  "normalizeClientCenterIds",
  "getAllowedCenterNames",
  "getWorkspaceCenterName",
  "ensureCentersLoaded",
  "resolveClientVisitCenterId",
  "resolveCenterIdForVisit",
  "resolveWorkspaceCenterId",
  "getCenterNameForContext",
  "createVisitsForClientByServices",
];

// Собирает часть app.js с настоящими функциями центров. Сеть и создание обращения в памяти
// заменены: createVisitForClient в app.js тоже ставит centerId = null и центр = рабочий.
function scope({ requests = [] } = {}) {
  const apiRequest = async (path, options = {}) => {
    if (path === "/centers") return CENTERS;
    if (path === "/encounters/by-services") {
      const body = JSON.parse(options.body);
      requests.push(body);
      return body.services.map((service, index) => ({
        encounter: { id: 900 + index, center_id: body.center_id, status: "draft" },
        service: {},
        payment: {},
      }));
    }
    throw new Error(`Неожиданный запрос ${path}`);
  };
  const createVisitForClient = (clientId) => ({
    id: `visit-${clientId}`,
    clientId,
    centerId: null,
    center: "Мед-Авто",
  });
  const source = FUNCTIONS.map((name) => extractFrom(appSource, name)).join("\n");
  return new Function(
    "appState",
    "data",
    "WORKSPACE_CENTER_NAMES",
    "apiRequest",
    "createVisitForClient",
    "loadDoctorExamsForClient",
    "persistDemoState",
    `${source}
return {
  resolveClientVisitCenterId,
  resolveCenterIdForVisit,
  createVisitsForClientByServices,
};`,
  )(
    {
      auth: { accessToken: "t", allCenters: false, centerName: "Мед-Авто", centerNames: ["Мед-Авто", "Медилэнд"] },
      centerFilter: "Мед-Авто",
    },
    { centers: [], centersLoaded: false, centersLoadingPromise: null },
    WORKSPACE_CENTER_NAMES,
    apiRequest,
    createVisitForClient,
    async () => {},
    () => {},
  );
}

const DRAFTS = [
  { serviceId: 5, serviceName: "Осмотр", amount: 1000, paymentType: "cash", comment: "", detail: {}, clientSex: "M" },
];

test("центр обращения клиента — рабочий, если клиент лежит в нём, иначе один из его центров", async () => {
  const { resolveClientVisitCenterId } = scope();
  assert.equal(await resolveClientVisitCenterId({ centerIds: [2] }), 2);
  assert.equal(await resolveClientVisitCenterId({ centerIds: [1, 2] }), 1);
  assert.equal(await resolveClientVisitCenterId({ centerIds: [2, 3] }), 2);
  assert.equal(await resolveClientVisitCenterId({ centerIds: [] }), 1);
  assert.equal(await resolveClientVisitCenterId({}), 1);
  assert.equal(await resolveClientVisitCenterId({ centerIds: [7] }), 1, "центр вне списка не берём");
});

test("новый клиент, отмеченный в Медилэнд, при первой услуге попадает в Медилэнд и помнит свой центр", async () => {
  const requests = [];
  const { createVisitsForClientByServices } = scope({ requests });
  const [visit] = await createVisitsForClientByServices({ id: 77, backendId: 77, centerIds: [2] }, DRAFTS);

  assert.equal(requests[0].center_id, 2);
  assert.equal(visit.centerId, 2, "блоки бланков и шаблоны печати берут центр из обращения");
  assert.equal(visit.center, "Медилэнд");
});

test("существующий клиент, лежащий только в Медилэнд, получает обращение в Медилэнд", async () => {
  const requests = [];
  const { createVisitsForClientByServices } = scope({ requests });
  await createVisitsForClientByServices({ id: 77, backendId: 77, centerIds: [2] }, DRAFTS);
  assert.equal(requests[0].center_id, 2);
});

test("клиент, лежащий и в рабочем центре, и в другом, получает обращение в рабочем", async () => {
  const requests = [];
  const { createVisitsForClientByServices } = scope({ requests });
  await createVisitsForClientByServices({ id: 77, backendId: 77, centerIds: [1, 2] }, DRAFTS);
  assert.equal(requests[0].center_id, 1);
});

test("клиент без известных центров получает обращение в рабочем центре, как раньше", async () => {
  const requests = [];
  const { createVisitsForClientByServices } = scope({ requests });
  await createVisitsForClientByServices({ id: 77, backendId: 77 }, DRAFTS);
  assert.equal(requests[0].center_id, 1);
});

test("бланки и печать для обращения без сохранения берут центр клиента, а не рабочий", async () => {
  const { resolveCenterIdForVisit } = scope();
  assert.equal(await resolveCenterIdForVisit({ centerId: null, center: "Мед-Авто" }, { centerIds: [2] }), 2);
  assert.equal(await resolveCenterIdForVisit({ centerId: 1, center: "Медилэнд" }, { centerIds: [2] }), 1, "уже известный центр обращения главнее");
});

test("сохранённое обращение запоминает центр, который вернул сервер", () => {
  assert.match(extractFrom(appSource, "syncVisitToBackend"), /visit\.centerId = encounter\.center_id/);
  assert.match(extractFrom(appSource, "createVisitsForClientByServices"), /visit\.centerId = savedItem\?\.encounter\?\.center_id/);
});

test("изменённый app.js подняли версию в index.html", () => {
  assert.match(indexHtml, /\.\/app\.js\?v=[\w-]*visit-center-v1/);
});
