import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");
const appSource = readFileSync(resolve(testDir, "../public/demo/app.js"), "utf8");
const stylesSource = readFileSync(resolve(testDir, "../public/demo/styles.css"), "utf8");

// Карточки председателя по типу справки и карточка психиатра, отрисованные настоящим кодом окна.
const CHAIRMAN_TYPES = ["default", "gto", "certificate070", "certificate072", "certificate082", "certificate095"];

function renderCard({ layout = "chairmanClassic", type = "default", client = {}, fields = {} } = {}) {
  const roleId = layout === "psychiatristClassic" ? "psychiatrist" : "chairman";
  const window = {
    appState: { doctorExamModal: { isOpen: true, clientId: 7, visitId: "visit-1", doctorRoleId: roleId } },
    getDoctorTemplate: () => ({ id: roleId, name: "Карточка", layout, fields: [] }),
    getDoctorExam: () => ({ id: "exam-1", clientId: 7, visitId: "visit-1", doctorName: "Врач", fields }),
    getClientPool: () => [{ id: 7, fullName: "Иванов Иван Иванович", ...client }],
    getChairmanFormInfo: () => ({ type, label: "Справка", templateName: "Справка" }),
    formatApiDate: (value) => {
      const match = String(value || "").match(/^(\d{4})-(\d{2})-(\d{2})$/);
      return match ? `${match[3]}.${match[2]}.${match[1]}` : "";
    },
  };
  const context = vm.createContext({
    window,
    document: { addEventListener() {}, querySelector: () => null, querySelectorAll: () => [] },
    setTimeout: () => 0,
  });
  vm.runInContext(modalSource, context);
  return window.renderDoctorExamModal();
}

const shownDate = (text) => new RegExp(`class="doctor-classic-input doctor-classic-static">${text}<`);
const emptyDate = /class="doctor-classic-input doctor-classic-static doctor-classic-static--empty">не указана</;

test("дата рождения в карточках председателя берётся из записи клиента, старое поле карточки не показывается", () => {
  for (const type of CHAIRMAN_TYPES) {
    const html = renderCard({ type, client: { birthDate: "28.01.1990" }, fields: { birthDate: "01.01.1950" } });
    assert.match(html, shownDate("28\\.01\\.1990"), `${type}: нет даты клиента`);
    assert.ok(!html.includes("01.01.1950"), `${type}: показана дата из старого поля карточки`);
    assert.doesNotMatch(html, /name="birthDate"/, `${type}: дата осталась полем ввода`);
  }
});

test("клиент без даты: вместо заглушки 01.01.1900 видно «не указана»", () => {
  for (const type of CHAIRMAN_TYPES) {
    const html = renderCard({ type, client: { birthDate: "01.01.1900" } });
    assert.match(html, emptyDate, `${type}: нет «не указана»`);
    assert.ok(!html.includes("01.01.1900"), `${type}: видна заглушка`);
  }
});

test("дата берётся из исходной записи клиента, если готовой строки нет", () => {
  const html = renderCard({ type: "gto", client: { birthDate: "", rawApiClient: { birth_date: "1988-02-14" } } });
  assert.match(html, shownDate("14\\.02\\.1988"));
});

test("карточка психиатра: дата рождения только показывается", () => {
  const html = renderCard({
    layout: "psychiatristClassic",
    client: { birthDate: "28.01.1990" },
    fields: { birthDate: "01.01.1950" },
  });
  assert.match(html, shownDate("28\\.01\\.1990"));
  assert.ok(!html.includes("01.01.1950"));
  assert.doesNotMatch(html, /name="birthDate"/);
});

test("карточка психиатра у клиента без даты показывает «не указана»", () => {
  const html = renderCard({ layout: "psychiatristClassic", client: { birthDate: "01.01.1900" } });
  assert.match(html, emptyDate);
});

test("сохранение клиента не подставляет дату карточки и не затирает дату пустым полем", () => {
  assert.doesNotMatch(appSource, /setIfBlank\("birthDate"/);
  assert.match(appSource, /parseRuDateToIso\(formData\.get\("birthDate"\), ""\) \|\| raw\.birth_date \|\| "1900-01-01"/);
});

test("статичное поле даты выглядит полем только для чтения", () => {
  assert.match(stylesSource, /\.doctor-classic-input\.doctor-classic-static\s*\{[^}]*background:\s*#eef0f2/);
  assert.doesNotMatch(modalSource, /certificate095-static/);
});

test("при открытии карточки фокус не уходит в «Пункты вредности» и не открывает подбор", () => {
  assert.match(modalSource, /textarea:not\(\[data-medical-requirements-input\]\)/);
});
