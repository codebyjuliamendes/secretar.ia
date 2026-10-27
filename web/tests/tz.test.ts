import assert from "node:assert/strict";
import { test } from "node:test";
import { addCalendarDays, localInputToUtc, utcToLocalInput, zonedParts, zonedToUtc } from "../src/lib/tz.ts";

test("horário da clínica independe do fuso de quem usa o painel", () => {
  const utc = zonedToUtc(2026, 9, 14, 9, 30, "America/Sao_Paulo");
  assert.equal(utc.toISOString(), "2026-09-14T12:30:00.000Z");
  const parts = zonedParts(utc, "America/Sao_Paulo");
  assert.equal(parts.dateKey, "2026-09-14");
  assert.equal(parts.hour, 9);
  assert.equal(parts.weekday, 0); // segunda
});

test("ida e volta do campo datetime-local no fuso da clínica", () => {
  const utc = localInputToUtc("2026-12-31T23:15", "America/Manaus");
  assert.equal(utc.toISOString(), "2027-01-01T03:15:00.000Z");
  assert.equal(utcToLocalInput(utc, "America/Manaus"), "2026-12-31T23:15");
});

test("virada de mês e de ano ao somar dias", () => {
  assert.equal(addCalendarDays("2026-12-30", 3), "2027-01-02");
  assert.equal(addCalendarDays("2028-02-28", 1), "2028-02-29");
});
