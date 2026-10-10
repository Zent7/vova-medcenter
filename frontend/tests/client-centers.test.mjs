import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// У каждого медцентра своя клиентская база. Сотрудник с несколькими центрами видит
// базы всех своих центров, заводит клиента сразу в оба и печатает договор каждого
// центра отдельной кнопкой («Договор Мед-Авто», «Договор Медилэнд»).

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const modalSource = readFileSync(resolve(testDir, "../public/demo/client-modal.js"), "utf8");
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

const CENTERS = ["Центр А", "Центр Б", "Центр В"];

function emptyAuth() {
  return { accessToken: "", userName: "", roleCode: "", roleName: "", centerName: "", centerNames: [], allCenters: false };
}

function scope(auth, { centerFilter = CENTERS[0], centers = [] } = {}) {
  const appFunctions = [
    "normalizeCenterLookupValue",
    "getAllowedCenterNames",
    "getWorkspaceCenterName",
    "getClientBaseCenterNames",
    "getClientBaseCenterIds",
    "getClientCenterChoiceNames",
    "getContractCenterNames",
    "matchesClientBase",
    "renderPrintContractButtons",
    "renderGenerateContractButtons",
    "normalizeClientCenterIds",
  ]
    .map((name) => extractFrom(appSource, name))
    .join("\n");
  return new Function(
    "appState",
    "data",
    "WORKSPACE_CENTER_NAMES",
    "escapeHtml",
    `${appFunctions}
return {
  base: getClientBaseCenterNames,
  baseIds: getClientBaseCenterIds,
  choice: getClientCenterChoiceNames,
  contract: getContractCenterNames,
  matches: matchesClientBase,
  printButtons: renderPrintContractButtons,
  generateButtons: renderGenerateContractButtons,
  centerIds: normalizeClientCenterIds,
};`,
  )(
    { auth: { ...emptyAuth(), ...auth }, centerFilter },
    { centers },
    CENTERS,
    (value) => String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;"),
  );
}

const SINGLE = { accessToken: "t", roleCode: "operator", centerName: CENTERS[1], centerNames: [CENTERS[1]] };
const MULTI = { accessToken: "t", roleCode: "operator", centerName: CENTERS[0], centerNames: [CENTERS[0], CENTERS[1]] };
const ADMIN = { accessToken: "t", roleCode: "admin", allCenters: true };

test("база клиентов сотрудника с несколькими центрами — базы всех его центров", () => {
  assert.deepEqual(scope(MULTI, { centerFilter: CENTERS[1] }).base(), [CENTERS[0], CENTERS[1]]);
  assert.deepEqual(scope(MULTI, { centerFilter: CENTERS[0] }).base(), [CENTERS[0], CENTERS[1]]);
});

test("сотрудник с одним центром видит базу этого центра", () => {
  assert.deepEqual(scope(SINGLE, { centerFilter: CENTERS[0] }).base(), [CENTERS[1]]);
});

test("админ и гость видят базу центра, выбранного в переключателе", () => {
  assert.deepEqual(scope(ADMIN, { centerFilter: CENTERS[2] }).base(), [CENTERS[2]]);
  assert.deepEqual(scope({}, { centerFilter: CENTERS[1] }).base(), [CENTERS[1]]);
});

test("серверу уходят номера центров базы, а неизвестные названия пропускаются", () => {
  const centers = [
    { id: 1, name: CENTERS[0] },
    { id: 2, name: CENTERS[1] },
    { id: 7, name: "Чужой центр" },
  ];
  assert.deepEqual(scope(MULTI, { centers }).baseIds(), [1, 2]);
  assert.deepEqual(scope(SINGLE, { centers }).baseIds(), [2]);
  assert.deepEqual(scope(MULTI, { centers: [] }).baseIds(), []);
});

test("строка журнала видна, если её обращение сделано в центре из базы; без обращения — всегда", () => {
  const multi = scope(MULTI);
  assert.equal(multi.matches(CENTERS[0]), true);
  assert.equal(multi.matches(CENTERS[1]), true);
  assert.equal(multi.matches(CENTERS[2]), false);
  assert.equal(multi.matches(""), true);

  const single = scope(SINGLE);
  assert.equal(single.matches(CENTERS[0]), false);
  assert.equal(single.matches(CENTERS[1]), true);
});

test("раскладывать клиента по центрам могут сотрудник с несколькими центрами и админ", () => {
  assert.deepEqual(scope(MULTI).choice(), [CENTERS[0], CENTERS[1]]);
  assert.deepEqual(scope(ADMIN).choice(), CENTERS);
  assert.deepEqual(scope(SINGLE).choice(), []);
  assert.deepEqual(scope({}).choice(), []);
});

test("договор каждого центра печатают отдельной кнопкой только у сотрудника с несколькими центрами", () => {
  assert.deepEqual(scope(MULTI).contract(), [CENTERS[0], CENTERS[1]]);
  assert.deepEqual(scope(SINGLE).contract(), []);
  assert.deepEqual(scope(ADMIN).contract(), []);
  assert.deepEqual(scope({}).contract(), []);
});

test("у сотрудника с одним центром остаётся одна кнопка договора, как была", () => {
  const single = scope(SINGLE);
  const printButton = single.printButtons({ id: "printVisitContractButton" });
  assert.match(printButton, /id="printVisitContractButton"/);
  assert.match(printButton, />Печать договора</);
  assert.doesNotMatch(printButton, /data-print-contract-center/);

  const generateButton = single.generateButtons();
  assert.match(generateButton, /data-generate-document="contract"/);
  assert.doesNotMatch(generateButton, /data-contract-center/);
});

test("у сотрудника с двумя центрами по кнопке договора на каждый центр", () => {
  const multi = scope(MULTI);
  const printButtons = multi.printButtons({ id: "printSelectedClientContractButton", enabled: false, title: "Выберите клиента" });
  assert.equal((printButtons.match(/<button/g) || []).length, 2);
  assert.match(printButtons, new RegExp(`data-print-contract-center="${CENTERS[0]}"[^>]*disabled`));
  assert.match(printButtons, new RegExp(`>Договор ${CENTERS[1]}<`));
  assert.doesNotMatch(printButtons, /id="printSelectedClientContractButton"/);

  const generateButtons = multi.generateButtons();
  assert.match(generateButtons, new RegExp(`data-contract-center="${CENTERS[0]}">Договор ${CENTERS[0]}<`));
  assert.match(generateButtons, new RegExp(`data-contract-center="${CENTERS[1]}">Договор ${CENTERS[1]}<`));
});

test("центры клиента приходят с сервера списком чисел; пока их нет, они неизвестны", () => {
  const { centerIds } = scope(SINGLE);
  assert.deepEqual(centerIds([1, "2", 0, "x"]), [1, 2]);
  assert.equal(centerIds(undefined), undefined);
  assert.equal(centerIds(null), undefined);
});

test("список клиентов просит у сервера только клиентов центров сотрудника", () => {
  const loader = extractFrom(appSource, "loadClientsFromBackend");
  assert.match(loader, /ensureCentersLoaded\(\)/);
  assert.match(loader, /params\.append\("center_ids"/);
});

test("при смене центра и входе список клиентов загружается заново", () => {
  assert.match(extractFrom(appSource, "switchWorkspaceCenter"), /loadClientsFromBackend\(/);
  assert.match(appSource, /Клиентская база зависит от центров сотрудника[\s\S]{0,80}loadClientsFromBackend\(/);
});

test("печать договора передаёт серверу центр, чей шаблон взять", () => {
  assert.match(extractFrom(appSource, "createDocumentForVisit"), /payload\.template_center_id = await resolveCenterIdByName\(options\.templateCenterName\)/);
  assert.match(extractFrom(appSource, "printContractForCurrentVisit"), /templateCenterName: centerName/);
  assert.match(extractFrom(appSource, "openDemoDocument"), /templateCenterName/);
});

test("форма клиента отправляет центры и печатает договор выбранного центра", () => {
  assert.match(modalSource, /centerIdsPayload = \{ center_ids:/);
  assert.match(modalSource, /\.\.\.centerIdsPayload,/);
  assert.match(modalSource, /templateCenterName: contractCenterName/);
  assert.match(modalSource, /Отметьте хотя бы один медцентр клиента/);
});

test("центры существующего клиента не перезаписываются наугад", () => {
  assert.match(modalSource, /!editingClient \|\| Array\.isArray\(knownClientCenterIds\)/);
  // Центры, которыми сотрудник управлять не вправе, остаются у клиента.
  assert.match(modalSource, /untouchedIds = knownIds\.filter/);
  // Центры для сохранения берутся с сервера, а не из карточки, которая могла устареть.
  assert.match(modalSource, /apiRequest\?\.\(`\/clients\/\$\{backendId\}`\)/);
  assert.match(modalSource, /knownIds = Array\.isArray\(serverClient\?\.center_ids\)/);
  // После сохранения свежие центры не затираются старыми из формы.
  assert.match(modalSource, /\.\.\.targetClient,\n\s+centerIds: savedMapped\.centerIds,/);
  // Карточка берёт центры из последнего списка с сервера, а не из кэша.
  assert.match(modalSource, /listedClient\?\.centerIds \?\? editingClient\.centerIds/);
});

test("кнопки «ОК + договор» по центрам и переключатель центров клиента", () => {
  const picker = extractFrom(modalSource, "renderClientCenterPicker");
  const html = new Function("escapeHtml", `${picker}\nreturn renderClientCenterPicker;`)((value) => String(value))(
    [CENTERS[0], CENTERS[1]],
    [CENTERS[1]],
  );
  assert.match(html, new RegExp(`value="${CENTERS[0]}"\\s*/>`));
  assert.match(html, new RegExp(`value="${CENTERS[1]}" checked`));

  const submitButtons = new Function(
    "getContractCenterNames",
    "escapeHtml",
    `${extractFrom(modalSource, "renderClientContractSubmitButtons")}\nreturn renderClientContractSubmitButtons;`,
  );
  const multi = submitButtons(() => [CENTERS[0], CENTERS[1]], (value) => String(value))(false);
  assert.match(multi, new RegExp(`data-contract-center="${CENTERS[0]}">ОК \\+ договор ${CENTERS[0]}<`));
  assert.match(multi, new RegExp(`data-contract-center="${CENTERS[1]}">ОК \\+ договор ${CENTERS[1]}<`));
  const plain = submitButtons(() => [], (value) => String(value))(true);
  assert.match(plain, />Сохранить \+ договор</);
  assert.doesNotMatch(plain, /data-contract-center/);
});

test("изменённые файлы подняли версию в index.html", () => {
  for (const file of ["styles.css", "app.js", "client-modal.js"]) {
    assert.match(indexHtml, new RegExp(`\\./${file.replace(".", "\\.")}\\?v=[\\w-]*client-centers-v1`));
  }
});
