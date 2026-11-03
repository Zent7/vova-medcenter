import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolve } from "node:path";

// Сервер без входа отвечает 401 на все разделы. Клиенты, услуги и шаблоны поэтому
// грузятся только с токеном: при старте, если вход уже был, и сразу после входа.
const appSource = readFileSync(resolve(import.meta.dirname, "../public/demo/app.js"), "utf8");

test("при старте без входа клиенты, услуги и шаблоны не запрашиваются", () => {
  assert.match(appSource, /if \(appState\.auth\?\.accessToken\) loadBackendWorkspaceData\(\);/);
});

test("после входа грузятся те же данные, что и при старте", () => {
  const loginStart = appSource.indexOf('document.getElementById("performLogin")');
  const loginEnd = appSource.indexOf('document.getElementById("closeLogin")', loginStart);
  assert.ok(loginStart > 0 && loginEnd > loginStart, "нет обработчика входа");
  assert.match(appSource.slice(loginStart, loginEnd), /void loadBackendWorkspaceData\(\);/);
});

test("поиск клиентов на дашборде отправляет токен и обрабатывает отказ сеанса", () => {
  assert.match(appSource, /fetch\(url, \{ headers: getDemoAuthHeaders\(\), signal: abortController\.signal \}\);/);
  assert.match(appSource, /if \(response\.status === 401\) window\.setTimeout\(handleSessionEndedByServer, 0\);/);
});
