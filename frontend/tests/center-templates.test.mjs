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
  const start = ["async function " + name + "(", "function " + name + "(", "const " + name + " ="]
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

// Грузит функции шаблонов в песочницу: центр, запросы к API и состояние подменены.
function loadTemplateApi({ workspaceCenters, requests, centerName }) {
  const context = vm.createContext({
    API_BASE_URL: "http://api.test/api/v1",
    data: { documentTemplates: [], documentTemplatesLoaded: false, templateOperationStatus: "" },
    renderApp() {},
    console,
    FormData,
    encodeURIComponent,
    URLSearchParams,
    getWorkspaceCenterName: () => centerName.current,
    resolveWorkspaceCenterId: async () => workspaceCenters[centerName.current] ?? null,
    async apiRequest(path, options = {}) {
      requests.push({ path, method: options.method || "GET", centerAtCall: centerName.current });
      if (typeof context.respond === "function") return context.respond(path);
      return [];
    },
  });
  vm.runInContext(
    `${extractDeclaration("buildQuery")}
${extractDeclaration("buildTemplateFileUrl")}
${extractDeclaration("loadDocumentTemplatesFromBackend")}
${extractDeclaration("refreshDocumentTemplatesFromBackend")}
${extractDeclaration("replaceDocumentTemplateFile")}
${extractDeclaration("resetDocumentTemplateFile")}
Object.assign(this, {
  buildTemplateFileUrl,
  loadDocumentTemplatesFromBackend,
  refreshDocumentTemplatesFromBackend,
  replaceDocumentTemplateFile,
  resetDocumentTemplateFile,
});`,
    context,
  );
  return context;
}

const CENTERS = { "Мед-Авто": 1, Медилэнд: 2, "ПЕРВАЯ ЗДРАВНИЦА": 3 };

test("список шаблонов просят для рабочего центра", async () => {
  const requests = [];
  const api = loadTemplateApi({ workspaceCenters: CENTERS, requests, centerName: { current: "Медилэнд" } });

  await api.loadDocumentTemplatesFromBackend();

  assert.equal(requests[0].path, "/documents/templates?center_id=2");
});

test("ответ для прежнего центра не затирает список нового", async () => {
  const requests = [];
  const centerName = { current: "Мед-Авто" };
  const api = loadTemplateApi({ workspaceCenters: CENTERS, requests, centerName });
  api.data.documentTemplates = [{ id: 1, has_override: true }];
  api.respond = () => {
    // Пока запрос шёл, оператор переключил центр.
    centerName.current = "Медилэнд";
    return [{ id: 1, has_override: false }];
  };

  await api.loadDocumentTemplatesFromBackend();

  assert.deepEqual(api.data.documentTemplates, [{ id: 1, has_override: true }]);
});

test("загрузка, возврат исходного и перечитывание идут с центром", async () => {
  const requests = [];
  const api = loadTemplateApi({ workspaceCenters: CENTERS, requests, centerName: { current: "ПЕРВАЯ ЗДРАВНИЦА" } });
  api.respond = () => ({ id: 7, name: "082у", file_name: "082у_шаблон.docx", has_override: true });

  await api.replaceDocumentTemplateFile(7, new Blob(["x"]));
  await api.resetDocumentTemplateFile(7);
  api.respond = () => [];
  await api.refreshDocumentTemplatesFromBackend();

  assert.deepEqual(
    requests.map(({ path, method }) => `${method} ${path}`),
    [
      "POST /documents/templates/7/replace?center_id=3",
      "POST /documents/templates/7/reset?center_id=3",
      "POST /documents/templates/refresh?center_id=3",
    ],
  );
  assert.match(api.data.templateOperationStatus, /Список шаблонов перечитан/);
});

test("сообщения о загрузке и возврате называют центр", async () => {
  const requests = [];
  const api = loadTemplateApi({ workspaceCenters: CENTERS, requests, centerName: { current: "Медилэнд" } });
  api.respond = () => ({ id: 7, name: "082у", file_name: "082у_шаблон.docx", has_override: true });

  await api.replaceDocumentTemplateFile(7, new Blob(["x"]));
  assert.match(api.data.templateOperationStatus, /«Медилэнд»/);

  await api.resetDocumentTemplateFile(7);
  assert.match(api.data.templateOperationStatus, /«Медилэнд»/);
});

test("ссылка на файл шаблона несёт центр", () => {
  const api = loadTemplateApi({ workspaceCenters: CENTERS, requests: [], centerName: { current: "Мед-Авто" } });

  assert.equal(api.buildTemplateFileUrl(5, 2), "http://api.test/api/v1/documents/templates/5/file?center_id=2");
  assert.equal(api.buildTemplateFileUrl(5), "http://api.test/api/v1/documents/templates/5/file");
});

test("переключение центра заново грузит шаблоны нового центра", () => {
  const switchSource = extractDeclaration("switchWorkspaceCenter");

  assert.match(switchSource, /loadDocumentTemplatesFromBackend\(\)/);
});

test("страница «Шаблоны» называет центр, чьи файлы показаны", () => {
  const pageSource = extractDeclaration("renderTemplatesPage");

  assert.match(pageSource, /Шаблоны медцентра «\$\{escapeHtml\(templateCenterName\)\}»/);
});

test("скачивание и открытие файла шаблона берут файл рабочего центра", () => {
  assert.match(appSource, /buildTemplateFileUrl\(info\.templateId, await resolveWorkspaceCenterId\(\)\)/);
  assert.match(appSource, /buildTemplateFileUrl\(templateId, await resolveWorkspaceCenterId\(\)\)/);
});
