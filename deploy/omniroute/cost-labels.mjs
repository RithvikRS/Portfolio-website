import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export const PINNED_SHA256 = "af170bc444a7c85a0de7de2c4832466e447aa865b466a280ea05132d4d4ab3c6";
const prefix = '"use strict";exports.id=22453,exports.ids=[22453],exports.modules={122453:a=>{a.exports=';
const suffix = "}};";

// Decode only the pinned bundle's string literal; never execute vendor code.
export function decodeLiteral(literal) {
  assert.equal(literal[0], "'");
  assert.equal(literal.at(-1), "'");
  let decoded = "";
  for (let i = 1; i < literal.length - 1; i++) {
    let c = literal[i];
    assert.notEqual(c, "'", "Unescaped quote in bundle literal");
    if (c !== "\\") { decoded += c; continue; }
    c = literal[++i];
    const escapes = { "\\": "\\", "'": "'", '"': '"', n: "\n", r: "\r", t: "\t", b: "\b", f: "\f", v: "\v" };
    if (c === "u" || c === "x") {
      const width = c === "u" ? 4 : 2;
      const hex = literal.slice(i + 1, i + 1 + width);
      assert.equal(hex.length, width);
      assert.match(hex, /^[0-9a-fA-F]+$/);
      decoded += String.fromCharCode(parseInt(hex, 16)); i += width;
    } else {
      assert.ok(Object.hasOwn(escapes, c), "Unexpected literal escape");
      decoded += escapes[c];
    }
  }
  return decoded;
}

export function updateMessages(messages, changes) {
  const result = structuredClone(messages);
  for (const { namespace, key, before, after } of changes) {
    assert.equal(result[namespace]?.[key], before, `Review changed upstream message: ${namespace}.${key}`);
    assert.equal(typeof after, "string");
    // Preserve ICU interpolation parameters; this is a text-only customization.
    assert.deepEqual(after.match(/\{[^{}]+\}/g) || [], before.match(/\{[^{}]+\}/g) || []);
    result[namespace][key] = after;
  }
  return result;
}

export function patchBundle(buffer, changes) {
  assert.equal(createHash("sha256").update(buffer).digest("hex"), PINNED_SHA256,
    "Upstream asset changed; review the new image before updating the patch");
  const source = buffer.toString("utf8");
  assert.ok(source.startsWith(prefix) && source.endsWith(suffix));
  const messages = JSON.parse(decodeLiteral(source.slice(prefix.length, -suffix.length)));
  const updated = updateMessages(messages, changes);
  return prefix + JSON.stringify(JSON.stringify(updated)) + suffix;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const input = process.argv[2];
  const output = process.argv[3];
  assert.ok(input && output, "Usage: node cost-labels.mjs INPUT OUTPUT");
  const changes = JSON.parse(readFileSync(new URL("./cost-labels.json", import.meta.url), "utf8"));
  writeFileSync(output, patchBundle(readFileSync(input), changes));
  console.log(`Updated ${changes.length} English usage-value labels; no inference code changed.`);
}
