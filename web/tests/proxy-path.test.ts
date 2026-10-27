import assert from "node:assert/strict";
import { test } from "node:test";
import { isSafeSegment, resolveProxyPath } from "../src/lib/server/proxy-path.ts";

test("encaminha caminhos normais da API, recodificando cada segmento", () => {
  const r = resolveProxyPath(["clinic", "abc123", "export", "patients.csv"]);
  assert.deepEqual(r, { ok: true, path: "clinic/abc123/export/patients.csv", encoded: "clinic/abc123/export/patients.csv" });
  const odd = resolveProxyPath(["auth", "invites", "tok en?#"]);
  assert.ok(odd.ok && odd.encoded === "auth/invites/tok%20en%3F%23");
});

test("recusa segmentos de navegação e barras decodificadas", () => {
  for (const segments of [["clinic", "..", "webhooks", "whatsapp"], ["clinic", ".", "x"], ["..%2Fwebhooks"], ["a/b"], ["a\\b"], []]) {
    const r = resolveProxyPath(segments.map((s) => s.replace("%2F", "/")));
    assert.deepEqual(r, { ok: false, status: 400 }, JSON.stringify(segments));
  }
  assert.equal(isSafeSegment(""), false);
});

test("rotas de webhook, cron e push do Google nunca passam pelo BFF", () => {
  for (const segments of [["webhooks", "whatsapp"], ["internal", "cron", "daily"], ["integrations", "google", "notify"]]) {
    assert.deepEqual(resolveProxyPath(segments), { ok: false, status: 404 });
  }
  assert.ok(resolveProxyPath(["integrations", "google", "callback"]).ok);
});
