import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

const menuSource = sourceBetween("const openChairmanPrintMenu = () =>", "const runChairmanPrint = async");
const printSource = sourceBetween("const runChairmanPrint = async", "printButton.addEventListener");

function declaredNames(source) {
  return new Set([...source.matchAll(/\b(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=/g)].map((match) => match[1]));
}

// Кнопки профосмотра живут в меню, а печатает их runChairmanPrint —
// другая функция. Обращение к переменной из меню там даёт
// "... is not defined" вместо документа.
test("chairman printing never reaches into the print-menu closure", () => {
  const menuOnly = declaredNames(menuSource);
  for (const name of declaredNames(printSource)) menuOnly.delete(name);
  const [, parameterList] = printSource.match(/^const runChairmanPrint = async \(([^)]*)\)/) || [];
  for (const parameter of String(parameterList || "").split(",")) {
    menuOnly.delete(parameter.trim().split(/[\s=]/)[0]);
  }

  const leaked = [...menuOnly].filter((name) => {
    const usage = new RegExp(`(?<![.\\w$])${name}\\b(?!\\s*:)`);
    return usage.test(printSource);
  });
  assert.deepEqual(leaked, [], `runChairmanPrint uses menu-local names: ${leaked.join(", ")}`);
});

test("the latest issued document is looked up through a shared helper", () => {
  assert.match(appSource, /^function findLatestCertificateDocumentForVisit\(certificateType, visit, client = null\) \{/m);
  assert.match(printSource, /findLatestCertificateDocumentForVisit\(directPrintType, visit, client\)/);
  assert.match(menuSource, /findLatestCertificateDocumentForVisit\(certificateType, visit, client\)/);
});

// Проф. осмотр, выписка из амб. карты и амб. карта 25У печатаются
// автонумерацией серии 29Н — все три идут одним и тем же путём.
test("all three profosmotr documents are auto-numbered from the menu", () => {
  const kinds = ["prof_conclusion", "prof_ambulatory_extract", "prof_ambulatory"];
  const autoNumbered = sourceBetween("const CHAIRMAN_AUTO_NUMBERED_PRINT_KINDS = new Set(", "function isChairmanAutoNumberedPrintKind");
  for (const kind of kinds) {
    assert.ok(menuSource.includes(`data-chairman-print-menu-kind="${kind}"`), `Нет кнопки для ${kind}`);
    assert.ok(autoNumbered.includes(`"${kind}"`), `${kind} не в списке автонумеруемых`);
    assert.match(appSource, new RegExp(`\\["${kind}", "29Н"\\]`));
  }
  assert.match(appSource, /prof_ambulatory_extract: "ambulatory_extract"/);
  assert.match(appSource, /prof_ambulatory: "prof_ambulatory"/);
});
