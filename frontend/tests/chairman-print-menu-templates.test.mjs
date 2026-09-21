// Каждая кнопка окна «Печать результатов» должна находить шаблон среди тех,
// что приложение действительно поставляет. Кнопка «Справка СЭМД-196» искала
// файл, которого никогда не было, и печать падала с «Не найден подходящий
// шаблон документа».
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const catalogSource = readFileSync(
  resolve(testDir, "../../backend/app/services/template_catalog.py"),
  "utf8",
);
const templatesDir = resolve(testDir, "../../assets/templates/Templates");

function sourceBetween(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return source.slice(start, end);
}

// Шаблоны в том виде, в каком их отдаёт /documents/templates: строки каталога,
// файлы которых лежат в папке шаблонов.
function bundledTemplates() {
  const catalog = sourceBetween(catalogSource, "SERVICE_LIST_TEMPLATE_ORDER", "TEMPLATE_DISPLAY_NAMES");
  return [...catalog.matchAll(/\("([^"]+)",\s*"([^"]+)"\),/g)]
    .map(([, fileName, name], index) => ({
      id: index + 1,
      name,
      code: `${fileName.replace(/\.[^.]+$/, "").toLowerCase()}-${index + 1}`,
      file_name: fileName,
      template_type: fileName.split(".").pop().toLowerCase(),
    }))
    .filter((template) => existsSync(resolve(templatesDir, template.file_name)));
}

function createTemplatePicker(templates) {
  const pickerSource = sourceBetween(appSource, "function pickDocumentTemplate", "function getChairmanTemplatePrintType");
  const context = vm.createContext({
    data: { documentTemplates: templates },
    repairDemoText: (value) => value,
  });
  vm.runInContext(`${pickerSource}; this.pickTemplate = pickDocumentTemplate;`, context);
  return context.pickTemplate;
}

function printMenuTypes() {
  const groups = sourceBetween(
    appSource,
    "const CHAIRMAN_CERTIFICATE_PRINT_GROUPS",
    "function getChairmanCertificatePrintSeries",
  );
  return [...new Set([...groups.matchAll(/\["([^"]+)", "[^"]+"\]/g)].map(([, type]) => type))];
}

const CLIENTS = {
  male: { fullName: "Иванов Иван Иванович", sex: "М" },
  female: { fullName: "Иванова Мария Петровна", sex: "Ж" },
};

test("у каждой кнопки окна «Печать результатов» есть поставляемый шаблон", () => {
  const pickTemplate = createTemplatePicker(bundledTemplates());
  const types = printMenuTypes();
  assert.ok(types.includes("semt196"), "в меню нет кнопки СЭМД-196");

  for (const type of types) {
    for (const [sex, client] of Object.entries(CLIENTS)) {
      assert.ok(pickTemplate(type, null, client), `нет шаблона для кнопки ${type} (${sex})`);
    }
  }
});

test("СЭМД-196 печатается своим бланком, выбранным по полу клиента", () => {
  const pickTemplate = createTemplatePicker(bundledTemplates());

  assert.equal(pickTemplate("semt196", null, CLIENTS.male)?.file_name, "СЭМД-196.муж_шаблон.docx");
  assert.equal(pickTemplate("semt196", null, CLIENTS.female)?.file_name, "СЭМД-196.жен_шаблон.docx");
  assert.equal(pickTemplate("semt196", null, { fullName: "Тест 234 234" })?.file_name, "СЭМД-196.муж_шаблон.docx");
  // У 086у свой бланк: иначе повторная печать и дубликат путали бы справки.
  assert.equal(pickTemplate("086", null, CLIENTS.male)?.file_name, "086у.муж_шаблон_2.docx");
  assert.equal(pickTemplate("086", null, CLIENTS.female)?.file_name, "086у.жен_шаблон.docx");
});
