// СЭМД-196 заменила 086у и печатается её бланком, поэтому услуга зовёт тех же
// врачей: без осмотра строка врача на бланке остаётся с фамилией из шаблона.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const testDir = dirname(fileURLToPath(import.meta.url));
const servicesSource = readFileSync(resolve(testDir, "../public/demo/services-data.js"), "utf8");
const seedSource = readFileSync(resolve(testDir, "../../backend/app/services/seed.py"), "utf8");

const servicesContext = vm.createContext({ window: {} });
vm.runInContext(servicesSource, servicesContext);
const servicesData = servicesContext.window.servicesData;

const SEMD196_SERVICE_IDS = [43, 44];
const SEMD196_BLANK_DOCTORS = ["Гинеколог", "Невролог", "Отоларинголог", "Офтальмолог", "Председатель", "Терапевт", "Хирург"];

function seedDoctorRoleIds(serviceId) {
  const match = seedSource.match(new RegExp(`\\n\\s+${serviceId}: \\[([^\\]]*)\\],`));
  assert.ok(match, `в seed.py нет врачей услуги ${serviceId}`);
  return match[1].split(",").map((value) => Number(value.trim()));
}

test("услуги СЭМД-196 зовут всех врачей бланка, как 086у", () => {
  const roleNameById = new Map(servicesData.doctorRoles.map((role) => [role.id, role.name]));

  for (const serviceId of SEMD196_SERVICE_IDS) {
    const service = servicesData.services.find((item) => item.id === serviceId);
    assert.deepEqual(
      Array.from(service.doctorRoleIds, (roleId) => roleNameById.get(roleId)).sort(),
      SEMD196_BLANK_DOCTORS,
      service.name,
    );
    // Демо без бэкенда берёт врачей из services-data.js — он не должен расходиться с сидом.
    assert.deepEqual([...service.doctorRoleIds], seedDoctorRoleIds(serviceId), service.name);
  }
});
