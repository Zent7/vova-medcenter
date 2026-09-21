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
  "CHAIRMAN_NUMBERED_CERTIFICATE_SERIES",
  "getChairmanNumberedCertificateSeries",
  "opensNumberedCertificatePrintWindow",
  "isNumberedCertificatePrintType",
];

const printRules = new Function(
  DECLARATIONS.map(extractDeclaration).join("\n\n") +
    `
  return {
    opensNumberedCertificatePrintWindow,
    isNumberedCertificatePrintType,
  };`,
)();

function sourceBetween(startMarker, endMarker, label) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `Не найден ${label}`);
  return appSource.slice(start, end);
}

const printSource = sourceBetween(
  "const runChairmanPrint = async",
  "printButton.addEventListener",
  "печать из карточки председателя",
);

// Именная кнопка «Справка 086у» стоит в окне «Печать результатов», где серию
// и номер бланка уже выбрали. Второе такое же окно ей не нужно.
test("именная кнопка справки 086у/095у печатает без второго окна", () => {
  for (const printType of ["086", "095"]) {
    assert.equal(printRules.opensNumberedCertificatePrintWindow(printType, `${printType}_certificate`), false);
  }
});

// Общая кнопка «Печать» серию не спрашивает — для неё окно остаётся.
test("общая кнопка печати по-прежнему открывает окно печати справки", () => {
  for (const printType of ["086", "095"]) {
    assert.equal(printRules.opensNumberedCertificatePrintWindow(printType, "conclusion"), true);
  }
  assert.equal(printRules.opensNumberedCertificatePrintWindow("082", "conclusion"), false);
});

test("печать из карточки председателя спрашивает окно через общее правило", () => {
  assert.match(printSource, /opensNumberedCertificatePrintWindow\(printType, printKind\)/);
});

// Номер 086у и 095у сквозной, поэтому его присваивают прямо при печати:
// без заведённых бланков справку не заставляют сначала жать «Найти номер».
test("номер 086у и 095у присваивается при печати без «Найти номер»", () => {
  for (const type of ["086", "095"]) {
    assert.equal(printRules.isNumberedCertificatePrintType(type), true);
  }
  assert.match(
    printSource,
    /const autoNumberedCertificate =\s*Boolean\(certificateType\) && isNumberedCertificatePrintType\(certificateType\);/,
  );
  assert.match(printSource, /!autoNumberedDocument && autoNumberedCertificate && !selectedBlank\?\.id/);
});
