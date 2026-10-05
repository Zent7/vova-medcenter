import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

// Сотрудник работает в своих медцентрах, админ видит все. Центры выбирают при
// создании учётной записи и меняют потом, вход возвращает их, а интерфейс
// оставляет в переключателе только их: единственный центр запирает переключатель.

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
const SCOPE_FUNCTIONS = ["getAllowedCenterNames", "getPinnedCenterName", "getWorkspaceCenterName"];

function emptyAuth() {
  return { accessToken: "", userName: "", roleCode: "", roleName: "", centerName: "", centerNames: [], allCenters: false };
}

function centerScope(auth, centerFilter = CENTERS[0]) {
  return new Function(
    "appState",
    "WORKSPACE_CENTER_NAMES",
    SCOPE_FUNCTIONS.map(extractFunction).join("\n") +
      "\nreturn { allowed: getAllowedCenterNames(), pinned: getPinnedCenterName(), current: getWorkspaceCenterName() };",
  )({ auth: { ...emptyAuth(), ...auth }, centerFilter }, CENTERS);
}

test("сотрудник с одним центром работает в нём, что бы ни было выбрано раньше", () => {
  const scope = centerScope({ accessToken: "t", roleCode: "operator", centerName: CENTERS[1], centerNames: [CENTERS[1]] }, CENTERS[0]);
  assert.deepEqual(scope, { allowed: [CENTERS[1]], pinned: CENTERS[1], current: CENTERS[1] });
});

test("сотрудник без списка центров (ответ старого сервера) закреплён за основным", () => {
  const scope = centerScope({ accessToken: "t", roleCode: "operator", centerName: CENTERS[1] }, CENTERS[0]);
  assert.deepEqual(scope, { allowed: [CENTERS[1]], pinned: CENTERS[1], current: CENTERS[1] });
});

test("сотрудник с несколькими центрами переключается между ними и не заперт", () => {
  const auth = { accessToken: "t", roleCode: "doctor", centerName: CENTERS[1], centerNames: [CENTERS[1], CENTERS[2]] };

  assert.deepEqual(centerScope(auth, CENTERS[2]), {
    allowed: [CENTERS[1], CENTERS[2]],
    pinned: "",
    current: CENTERS[2],
  });
});

test("выбранный раньше чужой центр заменяется основным", () => {
  const auth = { accessToken: "t", roleCode: "doctor", centerName: CENTERS[1], centerNames: [CENTERS[1], CENTERS[2]] };

  assert.equal(centerScope(auth, CENTERS[0]).current, CENTERS[1]);
  assert.equal(centerScope(auth, "чужое название").current, CENTERS[1]);
});

test("повторы и неизвестные интерфейсу центры из списка отбрасываются", () => {
  const scope = centerScope({
    accessToken: "t",
    roleCode: "doctor",
    centerName: CENTERS[2],
    centerNames: [CENTERS[2], CENTERS[0], CENTERS[2], "Неизвестный центр"],
  });

  assert.deepEqual(scope.allowed, [CENTERS[2], CENTERS[0]]);
  assert.equal(scope.pinned, "");
});

test("админ не ограничен: выбор переключателя сохраняется", () => {
  const scope = centerScope({ accessToken: "t", roleCode: "admin", allCenters: true, centerName: CENTERS[0] }, CENTERS[2]);
  assert.deepEqual(scope, { allowed: [], pinned: "", current: CENTERS[2] });
});

test("гость и сотрудник с неизвестными интерфейсу центрами не ограничены", () => {
  assert.deepEqual(centerScope({}, CENTERS[1]), { allowed: [], pinned: "", current: CENTERS[1] });
  assert.deepEqual(
    centerScope({ accessToken: "t", roleCode: "doctor", centerName: "Неизвестный центр", centerNames: ["Неизвестный центр"] }, CENTERS[1]),
    { allowed: [], pinned: "", current: CENTERS[1] },
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
    [...SCOPE_FUNCTIONS, "loginDemoStaff"].map(extractFunction).join("\n") + "\nreturn loginDemoStaff;",
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

test("вход сотрудника с одним центром переводит программу в него без лишнего тоста", async () => {
  const { appState, switched, login } = loginWith({
    access_token: "t",
    user_name: "Оператор",
    role_code: "operator",
    role_name: "Оператор",
    center_id: 2,
    center_name: CENTERS[2],
    all_centers: false,
    centers: [{ id: 2, name: CENTERS[2] }],
  });
  await login();

  assert.equal(appState.auth.centerName, CENTERS[2]);
  assert.deepEqual(appState.auth.centerNames, [CENTERS[2]]);
  assert.equal(appState.auth.allCenters, false);
  assert.deepEqual(switched, [{ name: CENTERS[2], options: { announce: false } }]);
});

test("вход сотрудника в центре, где вкладка уже открыта, ничего не сбрасывает", async () => {
  const { switched, login } = loginWith({
    access_token: "t",
    role_code: "operator",
    center_name: CENTERS[0],
    all_centers: false,
    centers: [{ id: 1, name: CENTERS[0] }],
  });
  await login();

  assert.deepEqual(switched, []);
});

test("вход сотрудника с несколькими центрами оставляет открытый, если он доступен", async () => {
  const response = {
    access_token: "t",
    role_code: "doctor",
    center_name: CENTERS[1],
    all_centers: false,
    centers: [
      { id: 2, name: CENTERS[1] },
      { id: 3, name: CENTERS[2] },
    ],
  };
  const kept = loginWith(response, { centerFilter: CENTERS[2] });
  await kept.login();
  assert.deepEqual(kept.appState.auth.centerNames, [CENTERS[1], CENTERS[2]]);
  assert.deepEqual(kept.switched, []);

  const moved = loginWith(response, { centerFilter: CENTERS[0] });
  await moved.login();
  assert.deepEqual(moved.switched, [{ name: CENTERS[1], options: { announce: false } }]);
});

test("вход админа оставляет переключатель и выбранный центр", async () => {
  const { appState, switched, login } = loginWith(
    { access_token: "t", role_code: "admin", center_name: null, all_centers: true, centers: [] },
    { centerFilter: CENTERS[1] },
  );
  await login();

  assert.equal(appState.auth.allCenters, true);
  assert.deepEqual(switched, []);
});

test("переключатель запирается у сотрудника с одним центром", () => {
  const render = extractFunction("renderApp");
  assert.match(render, /centerSelect\.disabled = isCenterPinned/);
  assert.match(render, /syncCenterSelectOptions\(\)/);
});

test("переключатель не меняет центр на недоступный руками", () => {
  const handler = appSource.slice(appSource.indexOf("centerSelect.addEventListener"));
  assert.match(
    handler,
    /allowedCenterNames\.length && !allowedCenterNames\.includes\(event\.target\.value\)\) \{\s*renderApp\(\);\s*return;/,
  );
});

function centerSelectOptions(auth) {
  const centerSelect = {
    options: [],
    set innerHTML(html) {
      this.options = [...html.matchAll(/<option value="([^"]*)"/g)].map((match) => ({ value: match[1] }));
    },
  };
  centerSelect.innerHTML = CENTERS.map((name) => `<option value="${name}">${name}</option>`).join("");
  const syncOptions = new Function(
    "appState",
    "WORKSPACE_CENTER_NAMES",
    "centerSelect",
    "escapeHtml",
    [...SCOPE_FUNCTIONS, "syncCenterSelectOptions"].map(extractFunction).join("\n") + "\nreturn syncCenterSelectOptions;",
  )({ auth: { ...emptyAuth(), ...auth }, centerFilter: CENTERS[0] }, CENTERS, centerSelect, (value) => value);
  syncOptions();
  return centerSelect.options.map((option) => option.value);
}

test("в переключателе остаются центры сотрудника, в порядке списка интерфейса", () => {
  assert.deepEqual(
    centerSelectOptions({ accessToken: "t", centerName: CENTERS[2], centerNames: [CENTERS[2], CENTERS[0]] }),
    [CENTERS[0], CENTERS[2]],
  );
  assert.deepEqual(centerSelectOptions({ accessToken: "t", centerName: CENTERS[1], centerNames: [CENTERS[1]] }), [CENTERS[1]]);
});

test("админу, гостю и сотруднику с неизвестными центрами переключатель показывает все", () => {
  assert.deepEqual(centerSelectOptions({}), CENTERS);
  assert.deepEqual(centerSelectOptions({ accessToken: "t", allCenters: true }), CENTERS);
  assert.deepEqual(centerSelectOptions({ accessToken: "t", centerName: "Неизвестный центр" }), CENTERS);
});

test("центр журнала и справочников берётся из доступных, а не из сохранённого выбора", () => {
  assert.match(extractFunction("matchesCenter"), /centerName === getWorkspaceCenterName\(\)/);
  assert.doesNotMatch(extractFunction("resolveCenterIdForVisit"), /appState\.centerFilter/);
});

test("форма сотрудника спрашивает центры флажками и не требует их у админа", () => {
  const page = extractFunction("renderEmployeePage");
  assert.match(page, /id="employeeCenterField"/);
  assert.match(page, /renderStaffCenterCheckboxes\(\)/);
  assert.doesNotMatch(page, /name="center_id"/);
  assert.match(page, /formatStaffCenterLabel\(user\)/);

  const binding = extractFunction("bindContentEvents");
  assert.match(binding, /role_code\?\.value === "admin"/);
  assert.match(binding, /setCustomValidity\(isAdmin \|\| hasChecked \? "" : /);
  assert.match(binding, /center_ids: roleCode === "admin" \? \[\] : orderStaffCenterIds\(formData\.getAll\("center_ids"\)\)/);

  assert.match(extractFunction("loadStaffWorkspace"), /ensureCentersLoaded\(\)/);
});

test("у сотрудника в списке есть кнопка «Центры», у админа — нет", () => {
  const page = extractFunction("renderEmployeePage");
  assert.match(page, /user\.all_centers \? "" : `<button[^`]*data-edit-staff-centers/);
  assert.match(page, /data-staff-centers-form=/);
  assert.match(page, /data-staff-main-center=/);
});

function updateCenters({ apiRequest, data }) {
  const toasts = [];
  const run = new Function(
    "data",
    "apiRequest",
    "persistDemoState",
    "renderApp",
    "showToast",
    "humanizeApiError",
    extractFunction("updateDemoStaffCenters") + "\nreturn updateDemoStaffCenters;",
  )(
    data,
    apiRequest,
    () => {},
    () => {},
    (message) => toasts.push(message),
    (error, fallback) => `${fallback}: ${error.message}`,
  );
  return { run, toasts };
}

test("центры существующего сотрудника сохраняются на сервере и обновляют строку списка", async () => {
  const requests = [];
  const data = {
    staffUsers: [
      { id: 7, full_name: "Врач", login: "doc" },
      { id: 8, full_name: "Другой", login: "other" },
    ],
    editingStaffCentersId: 7,
    staffCentersError: "",
  };
  const { run, toasts } = updateCenters({
    data,
    apiRequest: async (path, options) => {
      requests.push({ path, method: options.method, body: options.body });
      return { id: 7, full_name: "Врач", login: "doc", centers: [{ id: 2 }, { id: 3 }] };
    },
  });
  await run(7, [2, 3]);

  assert.deepEqual(requests, [{ path: "/staff/7/centers", method: "PUT", body: JSON.stringify({ center_ids: [2, 3] }) }]);
  assert.equal(data.editingStaffCentersId, null);
  assert.deepEqual(data.staffUsers[0].centers, [{ id: 2 }, { id: 3 }]);
  assert.equal(data.staffUsers[1].login, "other");
  assert.deepEqual(toasts, ["Медцентры сотрудника Врач сохранены"]);
});

test("ошибка сервера остаётся в редакторе центров", async () => {
  const data = { staffUsers: [], editingStaffCentersId: 7, staffCentersError: "" };
  const { run } = updateCenters({
    data,
    apiRequest: async () => {
      throw new Error("Медцентр не найден");
    },
  });
  await run(7, [9]);

  assert.equal(data.editingStaffCentersId, 7);
  assert.equal(data.staffCentersError, "Не удалось сохранить медцентры: Медцентр не найден");
});

test("основной центр идёт первым и не меняется, пока его не сняли", () => {
  const order = new Function(extractFunction("orderStaffCenterIds") + "\nreturn orderStaffCenterIds;")();

  assert.deepEqual(order(["1", "2", "3"]), [1, 2, 3]);
  assert.deepEqual(order(["1", "2", "3"], "2"), [2, 1, 3]);
  assert.deepEqual(order(["1", "3"], "2"), [1, 3]);
  assert.deepEqual(order([], "2"), []);
});

test("флажки центров отмечают текущие и берут только центры интерфейса", () => {
  const render = new Function(
    "data",
    "WORKSPACE_CENTER_NAMES",
    "escapeHtml",
    ["getAssignableCenters", "renderStaffCenterCheckboxes"].map(extractFunction).join("\n") +
      "\nreturn renderStaffCenterCheckboxes;",
  )(
    {
      centers: [
        { id: 1, name: CENTERS[0] },
        { id: 2, name: CENTERS[1] },
        { id: 9, name: "Чужой центр" },
      ],
    },
    CENTERS,
    (value) => String(value),
  );

  const html = render([2]);
  assert.equal(html.match(/<input /g).length, 2);
  assert.match(html, /value="2" checked/);
  assert.doesNotMatch(html, /value="1" checked/);
  assert.doesNotMatch(html, /Чужой центр/);
  assert.doesNotMatch(render(), / checked/);
});

test("список сотрудников подписывает центры, у админа — все медцентры", () => {
  const label = new Function(extractFunction("formatStaffCenterLabel") + "\nreturn formatStaffCenterLabel;")();
  assert.equal(label({ all_centers: true, center_name: null, centers: [] }), "все медцентры");
  assert.equal(label({ all_centers: false, center_name: CENTERS[1], centers: [{ name: CENTERS[1] }] }), CENTERS[1]);
  assert.equal(
    label({ all_centers: false, center_name: CENTERS[1], centers: [{ name: CENTERS[1] }, { name: CENTERS[2] }] }),
    `${CENTERS[1]}, ${CENTERS[2]}`,
  );
  assert.equal(label({ all_centers: false, center_name: CENTERS[1] }), CENTERS[1]);
  assert.equal(label({ all_centers: false, center_name: null }), "медцентр не указан");
});

test("в переключателе три медцентра, как в списке интерфейса", () => {
  const names = appSource.match(/const WORKSPACE_CENTER_NAMES = \[(.*?)\];/s)[1].match(/"([^"]+)"/g);
  assert.equal(names.length, 3);

  const select = indexHtml.match(/<select[^>]*id="centerSelect".*?<\/select>/s)[0];
  assert.equal(select.match(/<option /g).length, 3);
});
