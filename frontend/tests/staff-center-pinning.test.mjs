import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Сотрудник закреплён за одним медцентром, админ видит все. Центр выбирают при
// создании учётной записи, вход возвращает его, а интерфейс запирает переключатель.

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const indexHtml = readFileSync(resolve(testDir, "../public/demo/index.html"), "utf8");

function extractFunction(name) {
  const start = appSource.search(new RegExp(`(async )?function ${name}\\(`));
  assert.ok(start >= 0, `Не найдена функция ${name}`);
  let depth = 0;
  for (let index = appSource.indexOf("{", appSource.indexOf(")", start)); index < appSource.length; index += 1) {
    if (appSource[index] === "{") depth += 1;
    if (appSource[index] === "}") {
      depth -= 1;
      if (depth === 0) return appSource.slice(start, index + 1);
    }
  }
  assert.fail(`Не удалось вырезать функцию ${name}`);
}

const CENTERS = ["Центр А", "Центр Б", "Центр В"];

function emptyAuth() {
  return { accessToken: "", userName: "", roleCode: "", roleName: "", centerName: "", allCenters: false };
}

function centerScope(auth, centerFilter = CENTERS[0]) {
  return new Function(
    "appState",
    "WORKSPACE_CENTER_NAMES",
    ["getPinnedCenterName", "getWorkspaceCenterName"].map(extractFunction).join("\n") +
      "\nreturn { pinned: getPinnedCenterName(), current: getWorkspaceCenterName() };",
  )({ auth: { ...emptyAuth(), ...auth }, centerFilter }, CENTERS);
}

test("сотрудник работает в закреплённом центре, что бы ни было выбрано раньше", () => {
  const scope = centerScope({ accessToken: "t", roleCode: "operator", centerName: CENTERS[1] }, CENTERS[0]);
  assert.deepEqual(scope, { pinned: CENTERS[1], current: CENTERS[1] });
});

test("админ не закреплён: выбор переключателя сохраняется", () => {
  const scope = centerScope({ accessToken: "t", roleCode: "admin", allCenters: true, centerName: CENTERS[0] }, CENTERS[2]);
  assert.deepEqual(scope, { pinned: "", current: CENTERS[2] });
});

test("гость и сотрудник с неизвестным интерфейсу центром не закреплены", () => {
  assert.deepEqual(centerScope({}, CENTERS[1]), { pinned: "", current: CENTERS[1] });
  assert.deepEqual(
    centerScope({ accessToken: "t", roleCode: "doctor", centerName: "Неизвестный центр" }, CENTERS[1]),
    { pinned: "", current: CENTERS[1] },
  );
  assert.equal(centerScope({}, "чужое название").current, CENTERS[0]);
});

function loginWith(response, { centerFilter = CENTERS[0] } = {}) {
  const switched = [];
  const appState = { auth: emptyAuth(), centerFilter };
  const run = new Function(
    "appState",
    "WORKSPACE_CENTER_NAMES",
    "apiRequest",
    "persistDemoState",
    "switchWorkspaceCenter",
    "OFFLINE_CHAIRMAN_SESSION",
    "isBackendUnreachableError",
    ["getPinnedCenterName", "getWorkspaceCenterName", "loginDemoStaff"].map(extractFunction).join("\n") +
      "\nreturn loginDemoStaff;",
  )(
    appState,
    CENTERS,
    async () => response,
    () => {},
    (name, options) => {
      switched.push({ name, options });
      appState.centerFilter = name;
    },
    {},
    () => false,
  );
  return { appState, switched, login: () => run("login", "password") };
}

test("вход закреплённого сотрудника переводит программу в его центр без лишнего тоста", async () => {
  const { appState, switched, login } = loginWith({
    access_token: "t",
    user_name: "Оператор",
    role_code: "operator",
    role_name: "Оператор",
    center_id: 2,
    center_name: CENTERS[2],
    all_centers: false,
  });
  await login();

  assert.equal(appState.auth.centerName, CENTERS[2]);
  assert.equal(appState.auth.allCenters, false);
  assert.deepEqual(switched, [{ name: CENTERS[2], options: { announce: false } }]);
});

test("вход сотрудника в центре, где вкладка уже открыта, ничего не сбрасывает", async () => {
  const { switched, login } = loginWith({
    access_token: "t",
    role_code: "operator",
    center_name: CENTERS[0],
    all_centers: false,
  });
  await login();

  assert.deepEqual(switched, []);
});

test("вход админа оставляет переключатель и выбранный центр", async () => {
  const { appState, switched, login } = loginWith(
    { access_token: "t", role_code: "admin", center_name: null, all_centers: true },
    { centerFilter: CENTERS[1] },
  );
  await login();

  assert.equal(appState.auth.allCenters, true);
  assert.deepEqual(switched, []);
});

test("переключатель запирается у закреплённого и не меняет центр руками", () => {
  const render = extractFunction("renderApp");
  assert.match(render, /centerSelect\.disabled = isCenterPinned/);

  const handler = appSource.slice(appSource.indexOf("centerSelect.addEventListener"));
  assert.match(handler, /if \(getPinnedCenterName\(\)\) \{\s*renderApp\(\);\s*return;/);
});

test("центр журнала и справочников берётся из закреплённого, а не из сохранённого выбора", () => {
  assert.match(extractFunction("matchesCenter"), /centerName === getWorkspaceCenterName\(\)/);
  assert.doesNotMatch(extractFunction("resolveCenterIdForVisit"), /appState\.centerFilter/);
});

test("форма сотрудника спрашивает центр и не требует его у админа", () => {
  const page = extractFunction("renderEmployeePage");
  assert.match(page, /<select name="center_id" required>/);
  assert.match(page, /formatStaffCenterLabel\(user\)/);

  const binding = extractFunction("bindContentEvents");
  assert.match(binding, /role_code\?\.value === "admin"/);
  assert.match(binding, /center_id: roleCode === "admin" \? null : Number\(formData\.get\("center_id"\)\) \|\| null/);

  assert.match(extractFunction("loadStaffWorkspace"), /ensureCentersLoaded\(\)/);
});

test("список сотрудников подписывает центр, у админа — все медцентры", () => {
  const label = new Function(extractFunction("formatStaffCenterLabel") + "\nreturn formatStaffCenterLabel;")();
  assert.equal(label({ all_centers: true, center_name: null }), "все медцентры");
  assert.equal(label({ all_centers: false, center_name: CENTERS[1] }), CENTERS[1]);
  assert.equal(label({ all_centers: false, center_name: null }), "медцентр не указан");
});

test("в переключателе три медцентра, как в списке интерфейса", () => {
  const names = appSource.match(/const WORKSPACE_CENTER_NAMES = \[(.*?)\];/s)[1].match(/"([^"]+)"/g);
  assert.equal(names.length, 3);

  const select = indexHtml.match(/<select[^>]*id="centerSelect".*?<\/select>/s)[0];
  assert.equal(select.match(/<option /g).length, 3);
});
