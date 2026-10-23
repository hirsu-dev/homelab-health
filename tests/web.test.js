import test from "node:test";
import assert from "node:assert/strict";
import { Window } from "happy-dom";
import { readFile } from "node:fs/promises";
import { summarize, synthetic } from "../lantern/web/model.js";
test("missing coverage stays unknown and active/recovered scenarios differ", () => {
  for (const scenario of ["normal", "incident", "recovery", "gap"]) {
    const { services, samples } = synthetic(200000, scenario),
      r = summarize(services, samples, 200000, 24, 600);
    if (scenario === "incident") assert.equal(r.services[1].state, "down");
    if (scenario === "recovery")
      assert.equal(r.services[1].incidents[0].resolution, "observed recovery");
    if (scenario === "gap") {
      assert.equal(r.services[0].state, "unknown");
      assert.ok(r.services[0].coverage < 100);
    }
  }
});
test("empty history has no reachability percentage", () => {
  const r = summarize([{ id: "a", label: "A", kind: "http" }], [], 2000, 1, 60)
    .services[0];
  assert.equal(r.reachability, null);
  assert.equal(r.coverage, 0);
});
test("dashboard scenarios and inspector work through real DOM events", async () => {
  const window = new Window({ url: "https://example.test" });
  window.document.write(
    await readFile(
      new URL("../lantern/web/index.html", import.meta.url),
      "utf8",
    ),
  );
  const globals = {
    window,
    document: window.document,
    location: window.location,
  };
  const old = new Map(
    Object.keys(globals).map((k) => [
      k,
      Object.getOwnPropertyDescriptor(globalThis, k),
    ]),
  );
  for (const [k, v] of Object.entries(globals))
    Object.defineProperty(globalThis, k, {
      value: v,
      writable: true,
      configurable: true,
    });
  try {
    await import("../lantern/web/app.js");
    await new Promise((r) => setTimeout(r, 10));
    assert.equal(window.document.querySelectorAll(".service").length, 4);
    const select = window.document.querySelector("#scenario");
    select.value = "incident";
    select.dispatchEvent(new window.Event("change"));
    await new Promise((r) => setTimeout(r, 10));
    window.document.querySelector('[data-inspect="mesh"]').click();
    assert.match(
      window.document.querySelector("#details").textContent,
      /Down \/ ongoing/,
    );
    select.value = "gap";
    select.dispatchEvent(new window.Event("change"));
    await new Promise((r) => setTimeout(r, 10));
    assert.match(
      window.document.querySelector("#services").textContent,
      /Unknown/,
    );
  } finally {
    for (const [k, d] of old) {
      if (d) Object.defineProperty(globalThis, k, d);
      else delete globalThis[k];
    }
    await window.happyDOM.abort();
  }
});
