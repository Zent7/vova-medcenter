// Врач, которого требует услуга, должен быть виден на дашборде: без своей
// колонки и кнопки карточку некому открыть, осмотр не заводится, и в бланк
// нечего подставлять. Ровно так пропадал психиатр-нарколог в ГС и гостайне.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const servicesSource = readFileSync(resolve(testDir, "../public/demo/services-data.js"), "utf8");
const stylesSource = readFileSync(resolve(testDir, "../public/demo/styles.css"), "utf8");

function sourceBetween(startMarker, endMarker) {
  const start = appSource.indexOf(startMarker);
  const end = appSource.indexOf(endMarker, start);
  assert.notEqual(start, -1, `Missing source marker: ${startMarker}`);
  assert.notEqual(end, -1, `Missing source marker: ${endMarker}`);
  return appSource.slice(start, end);
}

const servicesContext = vm.createContext({ window: {} });
vm.runInContext(servicesSource, servicesContext);
const servicesData = servicesContext.window.servicesData;

const appContext = vm.createContext({});
vm.runInContext(
  [
    sourceBetween("const columnKeys = [", "const DRIVER_SERVICE_LEGACY_IDS"),
    sourceBetween("function getDoctorRoleIdByLabel", "function getDoctorFullName"),
    // Списки живут внутри renderDashboard, поэтому берём их литералы.
    `const doctorButtons = ${sourceBetween('  const doctorButtons = [', '  const excelColumns = [').replace('  const doctorButtons = ', '').trim().replace(/;$/, "")};`,
    `const excelColumns = ${sourceBetween('  const excelColumns = [', '  const tableLoading =').replace('  const excelColumns = ', '').trim().replace(/;$/, "")};`,
    "this.columnKeys = columnKeys;",
    "this.doctorRoleByExcelColumn = doctorRoleByExcelColumn;",
    "this.doctorButtons = doctorButtons;",
    "this.excelColumns = excelColumns;",
    "this.roleIdByLabel = getDoctorRoleIdByLabel;",
  ].join("\n"),
  appContext,
);

const roleCodeById = new Map(servicesData.doctorRoles.map((role) => [String(role.id), role.code]));
// В services-data.js у ролей нет кода — он берётся из того же порядка, что и на
// бэкенде, поэтому сверяем по имени роли из карточки врача.
const roleCodeByName = new Map([
  ["Терапевт", "therapist"],
  ["Психиатр", "psychiatrist"],
  ["Психиатр-нарколог", "psychiatrist-narcologist"],
  ["Невролог", "neurologist"],
  ["Отоларинголог", "otolaryngologist"],
  ["Гинеколог", "gynecologist"],
  ["Офтальмолог", "ophthalmologist"],
  ["Дерматовенеролог", "dermatologist"],
  ["Стоматолог", "dentist"],
  ["Хирург", "surgeon"],
  ["Фтизиатр", "phthisiatrist"],
  ["Узист", "uzist"],
  ["Председатель", "chairman"],
]);

function roleCodesRequiredByServices() {
  const codes = new Set();
  servicesData.services
    .filter((service) => service.isActive !== false)
    .forEach((service) => {
      (service.doctorRoleIds || []).forEach((roleId) => {
        const role = servicesData.doctorRoles.find((item) => String(item.id) === String(roleId));
        assert.ok(role, `Услуга «${service.name}» ссылается на несуществующую роль ${roleId}`);
        const code = roleCodeByName.get(role.name);
        assert.ok(code, `Нет кода для роли «${role.name}»`);
        codes.add(code);
      });
    });
  return codes;
}

const dashboardRoleCodes = () => new Set(Object.values(appContext.doctorRoleByExcelColumn));

test("у каждого столбца дашборда есть свой ключ", () => {
  assert.equal(appContext.columnKeys.length, appContext.excelColumns.length);
});

test("каждый врач, которого требует услуга, есть в столбцах дашборда", () => {
  const missing = [...roleCodesRequiredByServices()].filter((code) => !dashboardRoleCodes().has(code));
  assert.deepEqual(missing, [], `Нет столбца для ролей: ${missing.join(", ")}`);
});

test("каждый врач, которого требует услуга, есть среди кнопок врачей", () => {
  const buttonCodes = new Set(appContext.doctorButtons.map((label) => appContext.roleIdByLabel(label)));
  const missing = [...roleCodesRequiredByServices()].filter((code) => !buttonCodes.has(code));
  assert.deepEqual(missing, [], `Нет кнопки для ролей: ${missing.join(", ")}`);
});

test("психиатр-нарколог стоит в таблице своим столбцом, а не заодно с психиатром", () => {
  assert.equal(appContext.doctorRoleByExcelColumn.narcologist, "psychiatrist-narcologist");
  assert.equal(appContext.doctorRoleByExcelColumn.psychiatrist, "psychiatrist");

  const narcologistIndex = appContext.columnKeys.indexOf("narcologist");
  assert.notEqual(narcologistIndex, -1);
  assert.equal(appContext.excelColumns[narcologistIndex], "Психиатр-нарколог");
});

test("ГС и гостайна ведут клиента к наркологу", () => {
  const roleIdByCode = new Map([...roleCodeById].map(([id]) => {
    const role = servicesData.doctorRoles.find((item) => String(item.id) === id);
    return [roleCodeByName.get(role.name), Number(id)];
  }));
  const narcologistId = roleIdByCode.get("psychiatrist-narcologist");

  [2, 11].forEach((legacyId) => {
    const service = servicesData.services.find((item) => item.id === legacyId);
    assert.ok(service, `Услуга ${legacyId} не найдена`);
    assert.ok(
      (service.doctorRoleIds || []).includes(narcologistId),
      `Услуга «${service.name}» не зовёт нарколога`,
    );
  });
});

test("сетка таблицы и вертикальные заголовки учитывают новый столбец", () => {
  const gridStart = stylesSource.indexOf(".sketch-table__grid {");
  const gridEnd = stylesSource.indexOf("}", gridStart);
  const gridRule = stylesSource.slice(gridStart, gridEnd);
  const gridColumns = [...gridRule.matchAll(/var\(--excel-col-([A-Za-z]+)\)/g)].map(([, key]) => key);

  // columnKeys приходит из vm-контекста: сравниваем как обычный массив.
  assert.deepEqual(gridColumns, [...appContext.columnKeys]);
  assert.match(stylesSource, /--excel-col-narcologist:/);

  // Вертикальные подписи — со столбца врачей по «Очки» включительно.
  const glassesPosition = appContext.columnKeys.indexOf("glasses") + 1;
  const verticalHeaderRules = [...stylesSource.matchAll(/nth-child\(n \+ 7\):nth-child\(-n \+ (\d+)\)/g)];
  assert.ok(verticalHeaderRules.length > 0);
  verticalHeaderRules.forEach(([, bound]) => assert.equal(Number(bound), glassesPosition));
});
