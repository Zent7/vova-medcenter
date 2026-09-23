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

function sourceBetween(startMarker, endMarker, label) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `Не найден ${label}`);
  return appSource.slice(start, end);
}

const { isTractorPrintVariant } = new Function(
  extractDeclaration("isTractorPrintVariant") + "\nreturn { isTractorPrintVariant };",
)();

const printVariantSource = sourceBetween(
  "const printVariant = async",
  "const printSelectedCertificate = async",
  "печать стороны справки в окне печати",
);

test("тракторные стороны отличаются от водительских", () => {
  assert.equal(isTractorPrintVariant("tractor_front"), true);
  assert.equal(isTractorPrintVariant("tractor_back"), true);
  assert.equal(isTractorPrintVariant("driver_front"), false);
  assert.equal(isTractorPrintVariant("driver_back"), false);
});

// Окно печати открывается с водительским шаблоном, поэтому запасной путь
// печатал 071у на водительском бланке, если тракторный не нашёлся по имени файла.
test("тракторная справка не печатается на водительском бланке", () => {
  assert.match(
    printVariantSource,
    /findDocumentTemplateByExactFileName\(variantTemplateFileName\) \|\| \(tractorVariant \? null : flowState\.template\)/,
  );
  assert.match(printVariantSource, /Не найден шаблон лицевой стороны тракторной справки/);
  assert.match(printVariantSource, /Не найден шаблон оборотной стороны тракторной справки/);
});

// XML в МИАЦ уходит только по водительской справке: у 071у своя нумерация
// бланков, и выгрузка на тракторный бланк отвечала ошибкой.
test("после тракторной справки водительский XML не собирается", () => {
  const xmlCalls = printVariantSource.match(/ensureXmlAfterDriverCertificate\(/g) || [];
  const guardedCalls = printVariantSource.match(/if \(!tractorVariant\) \{\s*await ensureXmlAfterDriverCertificate\(/g) || [];
  assert.equal(xmlCalls.length, guardedCalls.length);
  assert.ok(guardedCalls.length >= 1, "Не найден вызов выгрузки XML после печати");
  assert.match(printVariantSource, /handleStandardPrintResult\(result, printedDocument, \{ skipXmlExport: tractorVariant \}\)/);
  assert.match(appSource, /skipXmlExport = false/);
});
