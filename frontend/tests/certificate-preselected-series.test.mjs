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

const DECLARATIONS = ["normalizeBlankSeries", "getBlankSeriesMatchKey"];

const seriesRules = new Function(
  DECLARATIONS.map(extractDeclaration).join("\n\n") +
    `
  return { getBlankSeriesMatchKey };`,
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

test("серия 086у с пометкой пола совпадает с серией бланков 086У", () => {
  const blankSeriesKey = seriesRules.getBlankSeriesMatchKey("086У");
  for (const series of ["086У", "086у", "086у (М)", "086у (Ж)"]) {
    assert.equal(seriesRules.getBlankSeriesMatchKey(series), blankSeriesKey, `Ключ серии ${series}`);
  }
  assert.notEqual(seriesRules.getBlankSeriesMatchKey("095у"), blankSeriesKey);
});

test("серии сравниваются по общему ключу, а не по точному написанию", () => {
  assert.match(printFlowSource, /isPreselectedSeriesAvailable = availableSeriesOptions\.some\(\s*\(item\) => getBlankSeriesMatchKey/);
  assert.match(printFlowSource, /isStoredSeriesAvailable = availableSeriesOptions\.some\(\s*\(item\) => getBlankSeriesMatchKey/);
});

test("явно выбранная справка 086у/095у важнее последней использованной серии", () => {
  // Без этого окно печати откатывалось на сохранённую или первую свободную
  // серию: у 086у типографских партий нет, поэтому вместо неё бралась 095у.
  assert.match(printFlowSource, /keepsPreselectedSeries =[\s\S]*?isNumberedCertificatePrintType\(requestedCertificateType\)/);
  assert.match(printFlowSource, /selectedSeries:\s*\n?\s*\(keepsPreselectedSeries \? preselectedSeries : ""\) \|\|/);
});
