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

const rules = new Function(
  [
    "normalizeBlankSeries",
    "CERTIFICATE_PRINT_SERIES_OPTIONS",
    "CERTIFICATE_PRINT_SERIES_OPTION_SET",
    "getDriverPrintSeriesPickerOptions",
    "PREENTERED_BLANK_SERIES",
    "PREENTERED_BLANK_SERIES_SET",
    "isPreenteredBlankSeries",
    "BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE",
    "BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE",
    "isPreenteredBlankFlow",
  ]
    .map(extractDeclaration)
    .join("\n\n") +
    `
  return {
    getDriverPrintSeriesPickerOptions,
    isPreenteredBlankFlow,
    gims: BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE,
    driver: BLANK_TYPE_DRIVER_MEDICAL_CERTIFICATE,
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

test("окно ГИМС предлагает серии заведённых бланков, а не утверждённый список", () => {
  const stock = [
    { series: "ГМ", free_count: 10, next_full_number: "ГМ000001" },
    { series: "40", free_count: 3, next_full_number: "40826006409" },
  ];

  assert.deepEqual(rules.getDriverPrintSeriesPickerOptions(stock, { includeSuggestedSeries: false }), ["ГМ", "40"]);
  // Остальные окна по-прежнему показывают только утверждённые серии.
  const approved = rules.getDriverPrintSeriesPickerOptions(stock);
  assert.ok(approved.includes("ГИМС") && !approved.includes("ГМ") && !approved.includes("40"));

  assert.match(printFlowSource, /const stockSeriesOnly = blankType === BLANK_TYPE_GIMS_MEDICAL_CERTIFICATE;/);
  assert.match(printFlowSource, /if \(!stockSeriesOnly\) \{\s*getDriverPrintSeriesPickerOptions\(seriesOptions/);
  assert.match(
    printFlowSource,
    /getDriverPrintSeriesPickerOptions\(flowState\.seriesOptions, \{\s*includeSuggestedSeries: !flowState\.stockSeriesOnly,\s*\}\)/,
  );
  assert.match(printFlowSource, /onlyListed: flowState\.stockSeriesOnly/);
});

test("номер ГИМС любой серии берётся из заведённого диапазона, а не выдаётся автоматически", () => {
  assert.equal(rules.isPreenteredBlankFlow("ГМ", rules.gims), true);
  assert.equal(rules.isPreenteredBlankFlow("40", rules.gims), true);
  assert.equal(rules.isPreenteredBlankFlow("ГМ", rules.driver), false);
  assert.equal(rules.isPreenteredBlankFlow("086У", rules.driver), false);
  assert.equal(rules.isPreenteredBlankFlow("ГИМС", rules.driver), true);

  assert.doesNotMatch(printFlowSource, /isPreenteredBlankSeries\((?:requestedSeries|flowState\.selectedSeries)\)/);
  assert.match(printFlowSource, /!isPreenteredBlankFlow\(requestedSeries, flowState\.blankType\) &&\s*!canAutoCreateChairmanBlankSeries/);
  assert.match(printFlowSource, /const autoCreate = !isPreenteredBlankFlow\(requestedSeries, flowState\.blankType\);/);
});

test("выбор серии ГИМС не снимает тип справки и не прячет «Освободить номер»", () => {
  assert.match(
    printFlowSource,
    /flowState\.compactCertificateFlow && flowState\.certificateTypes\.length === 1 \? flowState\.certificateTypes\[0\] : ""/,
  );
  assert.match(printFlowSource, /nextCertificateType \|\| \(flowState\.legacyCertificateFlow \? flowState\.selectedCertificateType : fixedCertificateType\)/);
});

test("выбор серии в окне ГИМС принимает только серию из списка", () => {
  const picker = sourceBetween(
    "function openDriverPrintSeriesPicker",
    "function buildBlankSeriesLabel",
    "окно выбора серии",
  );
  assert.match(picker, /onlyListed = false/);
  assert.match(picker, /if \(onlyListed && !listed\) \{/);
  assert.match(picker, /onSelect\(listed \?\? chosen\)/);
});
