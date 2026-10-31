import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { resolve } from "node:path";

// Заключение ЭКГ по умолчанию: карточка и печать должны показывать один и тот же текст.
const demoDir = resolve(import.meta.dirname, "../public/demo");
const cardSource = readFileSync(resolve(demoDir, "service-cards.js"), "utf8");
const indexSource = readFileSync(resolve(demoDir, "index.html"), "utf8");
const backendSource = readFileSync(
  resolve(import.meta.dirname, "../../backend/app/services/document_generator.py"),
  "utf8",
);

function cardDefaultConclusion() {
  const match = cardSource.match(/const STANDARD_EKG_CONCLUSION =\s*"([^"]+)";/);
  assert.ok(match, "в карточке ЭКГ нет STANDARD_EKG_CONCLUSION");
  return match[1];
}

function printedDefaultConclusion() {
  const match = backendSource.match(/EKG_STANDARD_CONCLUSION = \(([\s\S]*?)\n\)/);
  assert.ok(match, "в document_generator.py нет EKG_STANDARD_CONCLUSION");
  return [...match[1].matchAll(/"([^"]*)"/g)].map(([, part]) => part).join("");
}

test("карточка ЭКГ предлагает то же заключение, что печатает бланк", () => {
  assert.equal(cardDefaultConclusion(), printedDefaultConclusion());
  assert.match(cardDefaultConclusion(), /^Синусовый водитель ритма\. /);
  assert.match(cardDefaultConclusion(), /электрической оси сердца\.$/);
});

test("заключение ЭКГ больше не переписывается от даты: оно редактируется в карточке", () => {
  assert.doesNotMatch(cardSource, /buildAutoEkgConclusion|syncAutoEkgConclusion/);
  assert.match(cardSource, /const ekgConclusion = isAutoEkgConclusion\(storedEkgConclusion\) \? "" : storedEkgConclusion;/);
  assert.doesNotMatch(cardSource, /isAutoEkgConclusion\(storedEkgConclusion\) \? STANDARD_EKG_CONCLUSION/);
});

test("index.html грузит карточку ЭКГ с новым токеном кэша", () => {
  assert.match(indexSource, /service-cards\.js\?v=20261024-ekg-bottom-to-top-v1/);
  assert.match(indexSource, /app\.js\?v=[\w-]*blank-packs-dialog-v1/);
});

test("пустое заключение карточки ЭКГ заполняется стандартным текстом, справка спорта не меняется", () => {
  assert.match(cardSource, /const conclusionText = state\.isEkg && !storedConclusionText\.trim\(\) \? STANDARD_EKG_CONCLUSION : storedConclusionText;/);
  assert.match(cardSource, /textarea name="conclusionText" rows="3">\$\{esc\(conclusionText\)\}/);
  assert.match(cardSource, /doctorRoleId: "chairman", isEkg: true \}\);/);
});

test("обе дороги в карточку ЭКГ передают признак isEkg", () => {
  const appSource = readFileSync(resolve(demoDir, "app.js"), "utf8");
  assert.match(appSource, /doctorRoleId: "chairman",\s*isEkg: true,/);
});

// Берём саму функцию из service-cards.js: она живёт внутри замыкания модуля.
function pickEkgConclusionForSave() {
  const match = cardSource.match(/  function pickEkgConclusionForSave\(form\) \{[\s\S]*?\n  \}\r?\n/);
  assert.ok(match, "в карточке ЭКГ нет pickEkgConclusionForSave");
  return new Function("STANDARD_EKG_CONCLUSION", `${match[0]}\nreturn pickEkgConclusionForSave;`)(
    cardDefaultConclusion(),
  );
}

function fakeCardForm({ top = ["", ""], bottom = [cardDefaultConclusion(), cardDefaultConclusion()] } = {}) {
  const field = ([value, defaultValue]) => ({ value, defaultValue });
  return { elements: { ekgConclusion: field(top), conclusionText: field(bottom) } };
}

test("правка нижнего «Заключения» карточки ЭКГ уходит в заключение, которое печатает бланк", () => {
  const pick = pickEkgConclusionForSave();
  assert.equal(
    pick(fakeCardForm({ bottom: ["Норма, без изменений.", cardDefaultConclusion()] })),
    "Норма, без изменений.",
  );
  assert.equal(pick(fakeCardForm({ bottom: ["", cardDefaultConclusion()] })), "");
});

test("стандартный текст в нижнем поле не копируется наверх, верхнее поле остаётся пустым", () => {
  const pick = pickEkgConclusionForSave();
  assert.equal(pick(fakeCardForm({ bottom: [cardDefaultConclusion(), cardDefaultConclusion()] })), null);
  assert.equal(
    pick(fakeCardForm({ bottom: [` ${cardDefaultConclusion()} `, cardDefaultConclusion()] })),
    "",
  );
});

test("если правили верхнее поле или оба, сохраняем верхнее как введено", () => {
  const pick = pickEkgConclusionForSave();
  assert.equal(pick(fakeCardForm({ top: ["Ручной текст", ""] })), null);
  assert.equal(
    pick(fakeCardForm({ top: ["Ручной текст", ""], bottom: ["Другой текст", cardDefaultConclusion()] })),
    null,
  );
});
