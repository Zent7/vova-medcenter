import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const appSource = readFileSync(new URL("../public/demo/app.js", import.meta.url), "utf8");
const pageSource = readFileSync(new URL("../public/demo/services-page.js", import.meta.url), "utf8");
const modalSource = readFileSync(new URL("../public/demo/client-modal.js", import.meta.url), "utf8");

function functionSource(source, name) {
  const start = source.indexOf(`function ${name}(`);
  assert.ok(start >= 0, `Missing ${name}`);
  const rest = source.slice(start);
  const next = rest.slice(1).search(/\n(?:async )?function /);
  return next < 0 ? rest : rest.slice(0, next + 1);
}

function catalog({ driverId = 2, certificatesId = 7, services = [], serverServices = [] } = {}) {
  const context = vm.createContext({
    window: {},
    serviceGroups: [
      { id: driverId, code: "legacy-group-2", name: "ВУ", isActive: true },
      { id: certificatesId, code: "legacy-group-7", name: "Справки", isActive: true },
    ],
    structuredServices: services,
    data: { serverServices, serverServicesLoaded: true },
    doctorRoles: [],
    appState: { serviceGroupFilter: String(driverId) },
    escapeHtml: (value) => String(value ?? ""),
  });
  vm.runInContext([
    appSource.slice(appSource.indexOf("const SERVICE_SERIES_OVERRIDES"), appSource.indexOf("function getStoredDriverPrintSeries")),
    functionSource(appSource, "buildServiceSeriesAbbreviation"),
    functionSource(appSource, "formatCertificate086SeriesForSex"),
    functionSource(appSource, "normalizeSemd196ServiceGroup"),
    functionSource(appSource, "refreshServiceCatalog"),
    functionSource(modalSource, "getVisibleClientServices"),
    pageSource,
  ].join("\n"), context);
  return context;
}

test("actual driver chips do not label the service with backend ID 44 as СЭНД", () => {
  const services = [
    { id: 5, backendId: 5, legacySourceId: 8, name: "Медицинская комиссия", groupId: 3 },
    { id: 9, backendId: 9, legacySourceId: 7, name: "071У", groupId: 3 },
    { id: 44, backendId: 44, legacySourceId: null, name: "Водительская после лишения", groupId: 3 },
    { id: 41, backendId: 41, legacySourceId: 43, name: "Справка по форме СЭМД-196 без ФЛГ", groupId: 8 },
  ];
  const context = catalog({ driverId: 3, certificatesId: 8, services });
  context.getClientModalSexKey = () => "male";
  vm.runInContext([
    functionSource(modalSource, "getActiveClientServiceGroups"),
    functionSource(modalSource, "renderClientServiceSelector"),
  ].join("\n"), context);
  context.appState.clientServiceGroupFilter = "3";
  const html = context.renderClientServiceSelector();
  assert.doesNotMatch(html, /СЭНД/);
  assert.match(html, /ВУ после лишения/);
  assert.match(html, /ВУ \(водительская\)/);
  assert.match(html, /071у/);
  context.appState.clientServiceGroupFilter = "8";
  assert.match(context.renderClientServiceSelector(), /СЭНД/);
});

test("custom services never use their database ID as a legacy abbreviation ID", () => {
  const context = catalog();
  assert.notEqual(context.buildServiceSeriesAbbreviation({ id: 43, name: "Новая услуга" }), "СЭНД");
  assert.equal(context.buildServiceSeriesAbbreviation({ id: 100, legacy_source_id: 44, name: "Справка" }), "СЭНД");
});

test("cached СЭНД disappears from Услуги → ВУ and remains available in Справки", () => {
  const context = catalog({ services: [
    { id: 500, name: "СЭНД", groupId: 2, isActive: true },
    { id: 9, name: "071У", groupId: 2, isActive: true },
  ] });
  assert.match(context.renderServicesPage(), /data-service-id="500"/);

  context.refreshServiceCatalog();

  assert.doesNotMatch(context.renderServicesPage(), /data-service-id="500"/);
  assert.match(context.renderServicesPage(), /data-service-id="9"/);
  assert.deepEqual(Array.from(context.getVisibleClientServices(2), (service) => service.name), ["071У"]);
  context.appState.serviceGroupFilter = "7";
  assert.match(context.renderServicesPage(), /data-service-id="500"/);
  assert.deepEqual(Array.from(context.getVisibleClientServices(7), (service) => service.name), ["СЭНД"]);
});

test("API categories use actual IDs and keep ordinary driver service ID 44 in ВУ", () => {
  const services = [
    { id: 41, legacySourceId: 43, name: "Переименованная справка", groupId: 3 },
    { id: 42, legacy_source_id: 44, name: "Справка с ФЛГ", groupId: 3 },
    { id: 43, name: "Справка СЭМД-196", groupId: 3 },
    { id: 500, name: "сэмт 196", groupId: 3 },
    { id: 44, name: "Водительская после лишения", groupId: 3 },
  ];
  const context = catalog({ driverId: 3, certificatesId: 8, services, serverServices: services.map((service) => ({ ...service })) });
  context.refreshServiceCatalog();
  assert.deepEqual(services.map((service) => service.groupId), [8, 8, 8, 8, 3]);
  assert.deepEqual(context.data.serverServices.map((service) => service.groupId), [8, 8, 8, 8, 3]);
  assert.match(context.renderServicesPage(), /data-service-id="44"/);
  assert.doesNotMatch(context.renderServicesPage(), /data-service-id="41"/);
});

test("new СЭНД is saved to Справки even when the form selected ВУ", async () => {
  const context = catalog();
  let submit;
  let payload;
  const form = { addEventListener: (type, handler) => { if (type === "submit") submit = handler; } };
  context.document = { getElementById: (id) => id === "serviceCreateForm" ? form : null };
  context.openActionModal = () => {};
  context.actionModal = { classList: { add() {} } };
  context.renderApp = () => {};
  context.showToast = () => {};
  context.FormData = class {
    get(name) { return { name: "СЭНД", groupId: "2", price: "2500", isActive: "true" }[name] ?? ""; }
    getAll() { return []; }
  };
  context.window.apiRequest = async (_path, options) => {
    payload = JSON.parse(options.body);
    return { id: 500 };
  };
  context.openServiceModal();
  await submit({ preventDefault() {} });
  assert.equal(payload.category_id, 7);
  assert.equal(context.structuredServices[0].groupId, 7);
});
