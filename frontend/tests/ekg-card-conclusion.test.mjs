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
  assert.match(cardSource, /isAutoEkgConclusion\(storedEkgConclusion\) \? STANDARD_EKG_CONCLUSION : storedEkgConclusion/);
});

test("index.html грузит карточку ЭКГ с новым токеном кэша", () => {
  assert.match(indexSource, /service-cards\.js\?v=20261022-ekg-standard-conclusion-v1/);
});
