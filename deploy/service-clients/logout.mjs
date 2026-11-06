import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { brotliCompressSync, gzipSync } from "node:zlib";

const logout = 'window.location.replace("/oauth2/sign_out?rd=%2Freturn-to-dashboard")';
function readPinned(file, hash) {
  const data = readFileSync(file);
  assert.equal(createHash("sha256").update(data).digest("hex"), hash, "Review the new upstream client before publishing");
  return data.toString("utf8");
}
function replaceOnce(source, before, after) {
  assert.equal(source.split(before).length, 2, "Expected one upstream match: " + before);
  return source.replace(before, () => after);
}

mkdirSync("out", { recursive: true });
if (process.argv[2] === "kuma") {
  const file = "index-KKUg83qb.js";
  const original = readPinned(file, "437e9541d311e6806e9b87261c99fe1dc9b08ab0d171744c57de006f417b6ff5");
  // Automatic token rejection calls logout() without a click. Only user actions
  // carry a browser Event. Wait for the server acknowledgement before leaving.
  const updated = replaceOnce(original, 'logout(){ft.emit("logout",()=>{}),',
    'logout(event){ft.emit("logout",()=>{if(event instanceof Event){' + logout + '}}),');
  writeFileSync("out/" + file, updated);
  writeFileSync("out/" + file + ".gz", gzipSync(updated));
  writeFileSync("out/" + file + ".br", brotliCompressSync(updated));
} else {
  assert.equal(process.argv[2], "vault");
  const file = "main.1176a28a68b7b4809391.js";
  let source = readPinned(file, "5defb27621655bc05a54d042e32ce21d66dadd337b3bc60bc0cb49c234e441d1");
  source = replaceOnce(source, 'case"logout":yield this.logOut(e.redirect);',
    'case"logout":yield this.logOut(e.redirect,e.logoutReason==="userInitiated");');
  source = replaceOnce(source, 'logOut(){return H(this,arguments,void 0,function*(e=!0){this.ngZone',
    'logOut(){return H(this,arguments,void 0,function*(e=!0,returnToDashboard=false){this.ngZone');
  // This point follows the native key, cipher, token and account cleanup and
  // the LoggedOut status check. Lock, cancellation and expiry retain their UI.
  source = replaceOnce(source, 'yield this.accountService.switchAccount(null),yield i,e&&',
    'yield this.accountService.switchAccount(null),yield i;if(returnToDashboard){' + logout + ';return}e&&');
  const name = "main." + createHash("sha256").update(source).digest("hex").slice(0,20) + ".js";
  mkdirSync("out/app", { recursive: true });
  writeFileSync("out/app/" + name, source);
  writeFileSync("out/index.html", replaceOnce(readFileSync("index.html", "utf8"), "app/" + file, "app/" + name));
}
