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

function sourceBetween(startMarker, endMarker, label) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `Не найден ${label}`);
  return appSource.slice(start, end);
}

// Клиент с двумя услугами за один день: ВУ и 071у — это две строки журнала.
// Обращения приходят с сервера новыми сверху, а дата у них одна, поэтому
// «последним» всегда оказывается 071у.
function createVisitsContext({ selectedEncounterId = null, activeVisitId = null } = {}) {
  const driverVisit = {
    id: "encounter-100",
    backendId: 100,
    clientId: 7,
    createdAt: "2026-09-21",
    serviceNames: ["Медицинская комиссия"],
  };
  const tractorVisit = {
    id: "encounter-101",
    backendId: 101,
    clientId: 7,
    createdAt: "2026-09-21",
    serviceNames: ["071У"],
  };
  const context = vm.createContext({
    data: { visits: [tractorVisit, driverVisit] },
    appState: { selectedEncounterId, activeVisitId },
    ensureVisitsStore() {},
  });
  vm.runInContext(
    [
      extractDeclaration("getVisitsForClient"),
      extractDeclaration("getCurrentVisitForClient"),
      extractDeclaration("activateClientEncounter"),
      extractDeclaration("getSelectedJournalVisitForClient"),
    ].join("\n"),
    context,
  );
  return { context, driverVisit, tractorVisit };
}

test("без выбранной строки текущим обращением остаётся 071у", () => {
  const { context, tractorVisit } = createVisitsContext();
  assert.equal(context.getCurrentVisitForClient(7), tractorVisit);
});

test("печать берёт обращение выбранной строки журнала, а не последнее", () => {
  const { context, driverVisit } = createVisitsContext({ selectedEncounterId: 100 });
  assert.equal(context.getSelectedJournalVisitForClient(7), driverVisit);
  assert.equal(context.appState.activeVisitId, "encounter-100");
});

test("строка 071у печатает своё обращение", () => {
  const { context, tractorVisit } = createVisitsContext({ selectedEncounterId: 101 });
  assert.equal(context.getSelectedJournalVisitForClient(7), tractorVisit);
});

test("чужая строка журнала не уводит печать к другому клиенту", () => {
  const { context, tractorVisit } = createVisitsContext({ selectedEncounterId: 999 });
  assert.equal(context.getSelectedJournalVisitForClient(7), tractorVisit);
});

test("окно печати принимает обращение от вызывающей карточки", () => {
  const openerSource = sourceBetween(
    "async function openDriverPrintFlow(options = {})",
    "if (!data.documentTemplatesLoaded)",
    "начало окна печати",
  );
  assert.match(openerSource, /options\.visit\s*\|\|/);
  assert.match(openerSource, /getSelectedJournalVisitForClient\(client\.id\)/);
  assert.doesNotMatch(openerSource, /getCurrentVisitForClient\(client\.id\)/);
});

test("карточка председателя передаёт в печать своё обращение", () => {
  const printSource = sourceBetween(
    "const runChairmanPrint = async",
    '    printButton.addEventListener("click"',
    "печать из карточки председателя",
  );
  assert.equal(/openDriverPrintFlow\?\.\(\s*\)/.test(printSource), false);
  assert.match(printSource, /openDriverPrintFlow\?\.\(\{ client, visit \}\)/);
  assert.match(printSource, /getSelectedJournalVisitForClient\(client\.id\)/);
});

test("перезагрузка обращений не переводит работу на другую строку", () => {
  const loaderSource = extractDeclaration("loadEncountersForClient");
  assert.match(loaderSource, /appState\.selectedEncounterId/);
  assert.doesNotMatch(loaderSource, /appState\.activeVisitId = mappedVisits\[0\]/);
});
