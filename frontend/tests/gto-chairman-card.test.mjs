import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const modalSource = readFileSync(resolve(testDir, "../public/demo/doctor-exam-modal.js"), "utf8");
const templatesSource = readFileSync(resolve(testDir, "../public/demo/doctor-templates.js"), "utf8");
const stylesSource = readFileSync(resolve(testDir, "../public/demo/styles.css"), "utf8");

// Отрисовывает карточку председателя настоящим кодом окна, без страницы: окно
// берёт всё нужное у window, так что хватает заглушек данных.
function renderChairmanCard({ type = "gto", fields = {} } = {}) {
  const window = {
    appState: { doctorExamModal: { isOpen: true, clientId: 7, visitId: "visit-1", doctorRoleId: "chairman" } },
    getDoctorTemplate: () => ({ id: "chairman", name: "Председатель", layout: "chairmanClassic", fields: [] }),
    getDoctorExam: () => ({ id: "exam-1", fields }),
    getClientPool: () => [{ id: 7, fullName: "Иванов Иван Иванович", birthDate: "28.01.1990" }],
    getChairmanFormInfo: () => ({ type, label: "Председатель: справка ГТО", templateName: "ГТО" }),
  };
  const context = vm.createContext({
    window,
    document: { addEventListener() {}, querySelector: () => null, querySelectorAll: () => [] },
    setTimeout: () => 0,
  });
  vm.runInContext(modalSource, context);
  return window.renderDoctorExamModal();
}

function inputTags(html, name) {
  return [...html.matchAll(new RegExp(`<input[^>]*name="${name}"[^>]*>`, "g"))].map((match) => match[0]);
}

const ADMISSION_KEYS = ["gtoAdmitTraining", "gtoAdmitCompetitions", "gtoAdmitPhysicalEvents", "gtoAdmitComplex"];
const TEXT_KEYS = [
  "gtoAthleteRegistryNumber",
  "gtoEventName",
  "gtoSportKind",
  "gtoSportDiscipline",
  "gtoTrainingStage",
];

test("новая карточка ГТО: допущен ко всему, ограничений нет, строки описания нет", () => {
  const html = renderChairmanCard();

  for (const key of ADMISSION_KEYS) {
    const [tag] = inputTags(html, key);
    assert.ok(tag, `нет галочки ${key}`);
    assert.match(tag, /type="checkbox"/);
    assert.match(tag, /\schecked\s*\/?>/, `${key} должна стоять сама`);
  }
  const radios = inputTags(html, "gtoRestrictions");
  assert.equal(radios.length, 2);
  assert.match(radios.find((tag) => tag.includes('value="НЕТ"')), /\schecked\s*\/?>/);
  assert.doesNotMatch(radios.find((tag) => tag.includes('value="ДА"')), /\schecked/);
  assert.match(html, /data-gto-restrictions-text\s+hidden/);
});

test("карточка ГТО показывает ФИО, дату рождения и пять полей спортсмена", () => {
  const html = renderChairmanCard();

  assert.ok(html.includes("Иванов Иван Иванович"));
  assert.match(inputTags(html, "birthDate")[0], /value="28\.01\.1990"/);
  for (const key of TEXT_KEYS) {
    assert.equal(inputTags(html, key).length, 1, `нет поля ${key}`);
  }
  for (const label of [
    "Реестровый номер лица (спортсмена):",
    "Название мероприятия:",
    "Вид спорта:",
    "Спортивная дисциплина:",
    "Этап спортивной подготовки:",
    "ДОПУЩЕН к:",
    "Описать:",
  ]) {
    assert.ok(html.includes(label), `нет подписи «${label}»`);
  }
});

test("в карточке ГТО нет лишних полей общей карточки председателя", () => {
  const html = renderChairmanCard();

  for (const name of [
    "ekg",
    "ekgConclusion",
    "fluorography",
    "bloodGroup",
    "rhesusFactor",
    "medicalRequirements",
    "diagnosis",
    "conclusion",
    "validity",
    "organ",
    "note",
    "categoryB",
    "hasGlasses",
    "stampApplied",
  ]) {
    assert.ok(!html.includes(`name="${name}"`), `${name} лишнее`);
  }
});

test("сохранённая карточка ГТО открывается такой, какой её сохранили", () => {
  const html = renderChairmanCard({
    fields: {
      gtoAthleteRegistryNumber: "РН-77",
      gtoEventName: 'Кубок "А" <финал>',
      gtoSportKind: "Плавание",
      gtoAdmitCompetitions: false,
      gtoAdmitComplex: false,
      gtoRestrictions: "ДА",
      gtoRestrictionsText: "Без прыжков до 01.12.2026",
    },
  });

  assert.match(inputTags(html, "gtoAthleteRegistryNumber")[0], /value="РН-77"/);
  assert.match(inputTags(html, "gtoEventName")[0], /value="Кубок &quot;А&quot; &lt;финал&gt;"/);
  assert.doesNotMatch(inputTags(html, "gtoAdmitCompetitions")[0], /\schecked/);
  assert.doesNotMatch(inputTags(html, "gtoAdmitComplex")[0], /\schecked/);
  assert.match(inputTags(html, "gtoAdmitTraining")[0], /\schecked/);
  assert.match(inputTags(html, "gtoAdmitPhysicalEvents")[0], /\schecked/);
  assert.match(inputTags(html, "gtoRestrictions").find((tag) => tag.includes('value="ДА"')), /\schecked/);
  assert.doesNotMatch(html, /data-gto-restrictions-text\s+hidden/);
  assert.ok(html.includes("Без прыжков до 01.12.2026</textarea>"));
});

test("карточка без полей ГТО, сохранённая раньше, тоже допускает ко всему", () => {
  const html = renderChairmanCard({ fields: { conclusion: "Годен", examDate: "22.09.2026" } });

  for (const key of ADMISSION_KEYS) {
    assert.match(inputTags(html, key)[0], /\schecked/);
  }
  assert.match(inputTags(html, "examDate")[0], /value="22\.09\.2026"/);
});

test("карточки других справок остаются общей карточкой председателя", () => {
  for (const type of ["sport", "pool", "lmk"]) {
    const html = renderChairmanCard({ type });
    assert.equal(inputTags(html, "gtoEventName").length, 0, `${type}: поля ГТО не нужны`);
    assert.ok(html.includes('name="ekg"'), `${type}: общая карточка потеряла ЭКГ`);
  }
});

test("шаблон председателя знает поля ГТО и отмечает допуск по умолчанию", () => {
  for (const key of ADMISSION_KEYS) {
    assert.match(templatesSource, new RegExp(`key: "${key}"[^}]*type: "checkbox", defaultValue: true`));
  }
  assert.match(templatesSource, /key: "gtoRestrictions"[^}]*type: "radio", options: \["НЕТ", "ДА"\], defaultValue: "НЕТ"/);
  for (const key of [...TEXT_KEYS, "gtoRestrictionsText"]) {
    assert.match(templatesSource, new RegExp(`key: "${key}"`));
  }
});

test("строка «Описать» прячется и показывается по ответу об ограничениях", () => {
  assert.match(modalSource, /input\[name="gtoRestrictions"\]:checked/);
  assert.match(modalSource, /restrictionsText\.hidden = answer !== "ДА"/);
  // Правило display у самой строки перебило бы атрибут hidden.
  assert.match(stylesSource, /\.gto-chairman-row\[hidden\]\s*\{\s*display:\s*none;/);
});
