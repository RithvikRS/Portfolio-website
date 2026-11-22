import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { decodeLiteral, updateMessages, patchBundle } from "../deploy/omniroute/cost-labels.mjs";
const changes = JSON.parse(readFileSync(new URL("../deploy/omniroute/cost-labels.json", import.meta.url)));
test("decode JSON string data without executing the vendor bundle", () => {
  assert.equal(decodeLiteral("'a\\'b\\\\c\\u0020d'"), "a'b\\c d");
  assert.throws(() => decodeLiteral("'bad\\q'"));
});
test("fail closed when the pinned vendor bundle changes", () => {
  assert.throws(() => patchBundle(Buffer.from("unexpected upstream release"), changes), /Upstream asset changed/);
});
test("cost labels preserve unrelated messages and interpolation", () => {
  const messages = { settings: { hidePaidModels: true }, costs: { cost: "Cost" } };
  const result = updateMessages(messages, [{ namespace: "costs", key: "cost", before: "Cost", after: "Usage value" }]);
  assert.equal(result.costs.cost, "Usage value");
  assert.equal(messages.costs.cost, "Cost");
  assert.deepEqual(result.settings, messages.settings);
  assert.throws(() => updateMessages(messages, [{ namespace: "costs", key: "cost", before: "Changed", after: "Value" }]));
  assert.throws(() => updateMessages({ costs: { cost: "{count} cost" } }, [{ namespace: "costs", key: "cost", before: "{count} cost", after: "Value" }]));
});
test("billing copy never equates missing provider costs or zero estimates with a free bill", () => {
  const fields = Object.fromEntries(changes.map(c => [`${c.namespace}.${c.key}`, c.after]));
  assert.match(fields["costs.overviewDescription"], /Actual charges: not available/);
  assert.match(fields["costs.overviewDescription"], /provider-reported costs/);
  assert.match(fields["costs.overviewDescription"], /list-price estimates/);
  assert.match(fields["costs.overviewDescription"], /Free-tier estimates are not bills/);
  assert.match(fields["costs.noCostDataDescription"], /does not confirm/);
  assert.match(fields["costs.costExplorerDescription"], /missing provider cost/);
  assert.equal(fields["costs.cost"], "Usage value");
});
