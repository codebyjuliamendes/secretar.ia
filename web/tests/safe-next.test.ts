import assert from "node:assert/strict";
import { test } from "node:test";
import { safeNext } from "../src/lib/safe-next.ts";

const ORIGIN = "https://app.exemplo.com.br";

test("mantém caminhos internos com query", () => {
  assert.equal(safeNext("/app/t1/patients?search=ana", ORIGIN), "/app/t1/patients?search=ana");
});

test("bloqueia redirecionamento para outra origem", () => {
  for (const value of ["//evil.com", "/\\evil.com", "https://evil.com", "javascript:alert(1)", "", null]) {
    assert.equal(safeNext(value, ORIGIN), "/app", String(value));
  }
});
