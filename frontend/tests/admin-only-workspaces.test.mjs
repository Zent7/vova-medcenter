import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Учетные записи сотрудников, отчеты и касса — только у админа. Председатель
// заходит в программу постоянно и не должен видеть эти разделы.

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");

function extractFunction(name) {
  const start = appSource.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Не найдена функция ${name}`);
  let depth = 0;
  for (let index = appSource.indexOf("{", start); index < appSource.length; index += 1) {
    if (appSource[index] === "{") depth += 1;
    if (appSource[index] === "}") {
      depth -= 1;
      if (depth === 0) return appSource.slice(start, index + 1);
    }
  }
  assert.fail(`Не удалось вырезать функцию ${name}`);
}

function sourceBetween(startMarker, endMarker, label) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `Не найден ${label}`);
  return appSource.slice(start, end);
}

function accessFor(roleCode) {
  return new Function(
    "appState",
    ["canManageEmployeeWorkspace", "canAccessReportsWorkspace", "canAccessCashWorkspace"]
      .map(extractFunction)
      .join("\n") +
      "\nreturn { staff: canManageEmployeeWorkspace(), reports: canAccessReportsWorkspace(), cash: canAccessCashWorkspace() };",
  )({ auth: { roleCode } });
}

test("сотрудники, отчеты и касса доступны только админу", () => {
  assert.deepEqual(accessFor("admin"), { staff: true, reports: true, cash: true });
  for (const roleCode of ["chairman", "doctor", "operator", ""]) {
    assert.deepEqual(accessFor(roleCode), { staff: false, reports: false, cash: false }, roleCode || "без роли");
  }
});

test("пункты меню «Касса» и «Отчеты» скрыты у тех, кому они не положены", () => {
  const filter = sourceBetween("const visibleNavItems = navItems.filter(", "navRoot.innerHTML", "фильтр меню");
  assert.match(filter, /item\.id === "reports"\) return canAccessReportsWorkspace\(\)/);
  assert.match(filter, /item\.id === "cash"\) return canAccessCashWorkspace\(\)/);
});

test("открытая или восстановленная страница кассы и отчетов не показывается без прав", () => {
  const guard = sourceBetween("function renderApp() {", "document.body.dataset.page", "начало renderApp");
  assert.match(guard, /appState\.page === "reports" && !canAccessReportsWorkspace\(\)/);
  assert.match(guard, /appState\.page === "cash" && !canAccessCashWorkspace\(\)/);
  // Председателю на странице «Сотрудник» больше нечего делать: уводим на главную.
  assert.match(guard, /appState\.auth\.accessToken \? "dashboard" : "start"/);
});

test("данные кассы, отчетов и сотрудников не запрашиваются без прав", () => {
  const loadPage = extractFunction("loadPageData");
  assert.match(loadPage, /page === "employee" && canManageEmployeeWorkspace\(\)/);
  assert.match(loadPage, /page === "reports" && canAccessReportsWorkspace\(\)/);
  assert.match(loadPage, /page === "cash" && canAccessCashWorkspace\(\)/);

  assert.match(extractFunction("loadCashReport"), /if \(!canAccessCashWorkspace\(\)\) \{/);
  assert.match(extractFunction("loadReportsSummary"), /if \(!canAccessReportsWorkspace\(\)\) \{/);
  assert.match(extractFunction("loadStaffWorkspace"), /if \(!canManageEmployeeWorkspace\(\)\) \{/);
});

test("страница «Сотрудник» не показывает на экране логин и пароль", () => {
  const page = extractFunction("renderEmployeePage");
  assert.doesNotMatch(page, /chairman123|admin123|chairman \//);
});

test("после входа на страницу «Сотрудник» попадает только админ", () => {
  const login = sourceBetween('getElementById("performLogin")', 'getElementById("closeLogin")', "обработчик входа");
  assert.match(login, /if \(canManageEmployeeWorkspace\(\)\) \{\s*appState\.page = "employee"/);
  assert.doesNotMatch(login, /"chairman"/);
});
