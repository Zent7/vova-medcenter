import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

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

const DECLARATIONS = [
  "normalizeBlankSeries",
  "CERTIFICATE_PRINT_SERIES_TO_TYPE",
  "getDriverPrintCertificateType",
  "PREENTERED_BLANK_SERIES",
  "PREENTERED_BLANK_SERIES_SET",
  "isPreenteredBlankSeries",
  "CHAIRMAN_AUTO_CREATE_BLANK_SERIES",
  "canAutoCreateChairmanBlankSeries",
  "PREENTERED_CERTIFICATE_PRINT_TYPES",
  "certificateRequiresPreenteredBlank",
  "isNumberedCertificatePrintType",
  "getNumberedCertificateLookupSeriesForType",
  "resolveNumberedCertificateLookupSeries",
];

const blankRules = new Function(
  DECLARATIONS.map(extractDeclaration).join("\n\n") +
    `
  return {
    certificateRequiresPreenteredBlank,
    canAutoCreateChairmanBlankSeries,
    isPreenteredBlankSeries,
    resolveNumberedCertificateLookupSeries,
  };`,
)();

function sourceBetween(startMarker, endMarker, label) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `Не найден ${label}`);
  return appSource.slice(start, end);
}

const printFlowSource = sourceBetween(
  "async function openDriverPrintFlow",
  "window.openDriverPrintFlow = openDriverPrintFlow",
  "поток печати справок",
);

const chairmanLookupSource = sourceBetween(
  "const findChairmanBlank = async (",
  "chairmanPrintBlankState.findBlank = findChairmanBlank",
  "подбор номера из карточки врача",
);

test("086у нумеруется автоматически и не требует заведённого диапазона", () => {
  assert.equal(blankRules.certificateRequiresPreenteredBlank("086"), false);
  assert.equal(blankRules.isPreenteredBlankSeries("086У"), false);

  // Из карточки печати серия приходит с пометкой пола — искать и создавать
  // номер нужно всё равно по общей серии 086У.
  for (const series of ["086У", "086у", "086у (М)", "086у (Ж)"]) {
    const lookupSeries = blankRules.resolveNumberedCertificateLookupSeries(series, "086", []);
    assert.equal(lookupSeries, "086У", `Серия поиска для ${series}`);
    assert.equal(blankRules.canAutoCreateChairmanBlankSeries(lookupSeries), true, `Автономер для ${series}`);
  }
});

test("095у по-прежнему берёт номер только из заведённого диапазона", () => {
  assert.equal(blankRules.certificateRequiresPreenteredBlank("095"), true);
  assert.equal(blankRules.resolveNumberedCertificateLookupSeries("095у", "095", []), "095У");
});

test("подбор номера справки опирается на признак заведённых бланков", () => {
  for (const source of [printFlowSource, chairmanLookupSource]) {
    assert.match(source, /certificateRequiresPreenteredBlank\(/);
    assert.doesNotMatch(source, /isNumberedCertificatePrintType\([^)]*\) \|\| !canAutoCreateChairmanBlankSeries/);
  }

  // Серия поиска, а не выбранная «086у (М)», решает, можно ли выдать автономер.
  assert.match(chairmanLookupSource, /!canAutoCreateChairmanBlankSeries\(lookupSeries\)/);
});
