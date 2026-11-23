import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

const OPENERS = { "(": ")", "[": "]", "{": "}" };
const CLOSERS = new Set([")", "]", "}"]);

// Вырезает функцию верхнего уровня целиком, считая скобки.
function extractDeclaration(name) {
  const start = appSource.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Не найдено объявление ${name}`);

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

const DECLARATIONS = [
  "escapeHtml",
  "isWordDocumentFile",
  "isExcelDocumentFile",
  "buildWordProtocolUrl",
  "buildExcelProtocolUrl",
  "getOfficeDocumentTarget",
  "renderDocumentTargetWindow",
  "openDocumentFileUrl",
];

// page — заглушка окна вкладки: туда уходит ссылка, когда отдельного окна документа нет.
function loadDocumentFunctions(page) {
  return new Function(
    "window",
    `${DECLARATIONS.map(extractDeclaration).join("\n\n")}
return {
  escapeHtml,
  isWordDocumentFile,
  isExcelDocumentFile,
  buildWordProtocolUrl,
  buildExcelProtocolUrl,
  getOfficeDocumentTarget,
  renderDocumentTargetWindow,
  openDocumentFileUrl,
};`,
  )(page);
}

function makePage() {
  return { closed: false, location: { href: "" } };
}

// Окно документа: сохраняем HTML, который в него записан, чтобы проверить кнопки и текст.
function makeTargetWindow() {
  const target = { closed: false, html: "", location: { href: "" } };
  target.document = {
    open() {},
    write(html) {
      target.html = html;
    },
    close() {},
  };
  return target;
}

const EXCEL_URL = "https://vova-medcenter.ravil.space/api/v1/documents/print-ticket/abc123/Бланк ВУ.xls";
const WORD_URL = "https://vova-medcenter.ravil.space/api/v1/documents/print-ticket/abc123/Справка.docx";
const PDF_URL = "https://vova-medcenter.ravil.space/api/v1/documents/print-ticket/abc123/Выписка.pdf";

test("xls и xlsx распознаются как файлы Excel, остальные нет", () => {
  const { isExcelDocumentFile } = loadDocumentFunctions(makePage());
  assert.equal(isExcelDocumentFile("Бланк ВУ.xls"), true);
  assert.equal(isExcelDocumentFile("ЛМК.XLSX"), true);
  assert.equal(isExcelDocumentFile("Справка.docx"), false);
  assert.equal(isExcelDocumentFile("Выписка.pdf"), false);
  assert.equal(isExcelDocumentFile(""), false);
  assert.equal(isExcelDocumentFile(undefined), false);
});

test("ссылка для Excel открывает файл по протоколу ms-excel в режиме просмотра", () => {
  const { buildExcelProtocolUrl } = loadDocumentFunctions(makePage());
  assert.equal(buildExcelProtocolUrl(EXCEL_URL), `ms-excel:ofv|u|${encodeURI(EXCEL_URL)}`);
});

test("без окна документа бланк xls уходит в Excel, а не в загрузку файла", () => {
  const page = makePage();
  const { openDocumentFileUrl } = loadDocumentFunctions(page);
  openDocumentFileUrl(EXCEL_URL, { fileName: "Бланк ВУ.xls" });
  assert.equal(page.location.href, `ms-excel:ofv|u|${encodeURI(EXCEL_URL)}`);
});

test("Word по-прежнему открывается в Word", () => {
  const page = makePage();
  const { openDocumentFileUrl } = loadDocumentFunctions(page);
  openDocumentFileUrl(WORD_URL, { file_name: "Справка.docx" });
  assert.equal(page.location.href, `ms-word:ofv|u|${encodeURI(WORD_URL)}`);
});

test("прочие файлы открываются по обычной ссылке", () => {
  const page = makePage();
  const { openDocumentFileUrl } = loadDocumentFunctions(page);
  openDocumentFileUrl(PDF_URL, { fileName: "Выписка.pdf" });
  assert.equal(page.location.href, PDF_URL);
});

test("окно документа для Excel ведёт в Excel и даёт ссылку на скачивание", () => {
  const { openDocumentFileUrl } = loadDocumentFunctions(makePage());
  const target = makeTargetWindow();
  openDocumentFileUrl(EXCEL_URL, { fileName: "Бланк ВУ.xls" }, target);

  const excelUrl = `ms-excel:ofv|u|${encodeURI(EXCEL_URL)}`;
  assert.equal(target.location.href, excelUrl);
  assert.match(target.html, /Открываем документ в Microsoft Excel\./);
  assert.ok(target.html.includes(`href="${excelUrl}"`));
  assert.match(target.html, />Открыть в Microsoft Excel</);
  assert.ok(target.html.includes(`href="${EXCEL_URL}"`));
  assert.match(target.html, />Скачать документ</);
  assert.match(target.html, /Если Excel не открылся автоматически/);
  assert.doesNotMatch(target.html, /Word/);
});

test("окно документа для Word показывает прежний текст и кнопку Word", () => {
  const { openDocumentFileUrl } = loadDocumentFunctions(makePage());
  const target = makeTargetWindow();
  openDocumentFileUrl(WORD_URL, { fileName: "Справка.docx" }, target);

  assert.equal(target.location.href, `ms-word:ofv|u|${encodeURI(WORD_URL)}`);
  assert.match(target.html, /Открываем справку в Microsoft Word\./);
  assert.match(target.html, />Открыть в Microsoft Word</);
  assert.match(target.html, /Если Word не открылся автоматически/);
  assert.doesNotMatch(target.html, /Excel/);
});

test("окно ошибки выводится без кнопок открытия", () => {
  const { renderDocumentTargetWindow } = loadDocumentFunctions(makePage());
  const target = makeTargetWindow();
  renderDocumentTargetWindow(target, {
    title: "Не удалось открыть документ",
    message: "Повторите печать.",
    error: true,
  });

  assert.match(target.html, /Повторите печать\./);
  assert.doesNotMatch(target.html, /class="actions"/);
});
