/** Disposable staging only. Copy to /app/apps/api/src; never ship or run against production.
 * Requires an empty migrated DB named rakazo_workspace_verify_* and separate runtime/owner URLs.
 * Run: VERIFY_RAKAZO_DISPOSABLE=1 pnpm exec vitest run apps/api/src/verify-workspace.postgres.test.ts --maxWorkers=1
 * The only emulated boundary is HTTPS OIDC transport: genuine PKCE, signed ID tokens, auth sessions,
 * tenant middleware, RPC handlers, encryption and persistence execute against the real API/DB.
 */
import { createHash, generateKeyPairSync, randomBytes, sign } from "node:crypto";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { Pool } from "pg";
import { expect, it, vi } from "vitest";
import { createApp, type AppHandles } from "./app.js";

it("admits only verified owner OIDC and persists inert workspaces without any execution", async () => {
  if (process.env.VERIFY_RAKAZO_DISPOSABLE !== "1") throw new Error("Explicit disposable staging opt-in required");
  const runtimeUrl = process.env.DATABASE_URL!;
  const ownerUrl = process.env.DATABASE_MIGRATION_URL!;
  for (const url of [runtimeUrl, ownerUrl]) {
    if (!url || !/^\/rakazo_workspace_verify_[a-z0-9_]+$/.test(new URL(url).pathname))
      throw new Error("Use a newly migrated rakazo_workspace_verify_* database");
  }
  if (runtimeUrl === ownerUrl) throw new Error("Separate runtime and migration roles required");
  const ownerDb = new Pool({ connectionString: ownerUrl, max: 1 });
  const users = await ownerDb.query('SELECT count(*)::int AS count FROM "user"');
  if (users.rows[0].count !== 0) { await ownerDb.end(); throw new Error("Refusing nonempty user database"); }
  const issuer = "https://identity.example.test";
  const origin = "https://rakazo.example.test";
  const email = "owner@example.test";
  const secret = randomBytes(32).toString("hex");
  const dataDir = await mkdtemp(join(tmpdir(), "rakazo-workspace-verify-"));
  const { privateKey, publicKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });
  const jwk = { ...publicKey.export({ format: "jwk" }), kid: "disposable", alg: "RS256", use: "sig" };
  const codes = new Map<string, { nonce: string; challenge: string; claims: Record<string, unknown> }>();
  let nonIssuerRequests = 0;
  let userInfoClaims: Record<string,unknown> = {};
  let handles: AppHandles | undefined;
  const jwt = (claims: Record<string, unknown>) => {
    const header = Buffer.from(JSON.stringify({ alg: "RS256", kid: "disposable" })).toString("base64url");
    const payload = Buffer.from(JSON.stringify({ iss: issuer, aud: "disposable-client", iat: Math.floor(Date.now()/1000), exp: Math.floor(Date.now()/1000)+300, ...claims })).toString("base64url");
    const body = `${header}.${payload}`;
    return `${body}.${sign("RSA-SHA256", Buffer.from(body), privateKey).toString("base64url")}`;
  };
  vi.stubGlobal("fetch", async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    if (url.origin !== issuer) { nonIssuerRequests++; throw new Error("Provider/network request forbidden in workspace verification"); }
    if (url.pathname.endsWith("openid-configuration")) return Response.json({ issuer, authorization_endpoint: `${issuer}/authorize`, token_endpoint: `${issuer}/token`, userinfo_endpoint: `${issuer}/userinfo`, jwks_uri: `${issuer}/jwks`, id_token_signing_alg_values_supported: ["RS256"] });
    if (url.pathname === "/userinfo") return Response.json(userInfoClaims);
    if (url.pathname === "/jwks") return Response.json({ keys: [jwk] });
    if (url.pathname === "/token") {
      const body = new URLSearchParams(String(init?.body));
      const code = body.get("code")!;
      const entry = codes.get(code); codes.delete(code);
      if (!entry || entry.challenge !== createHash("sha256").update(body.get("code_verifier") ?? "").digest("base64url")) return Response.json({ error: "invalid_grant" }, { status: 400 });
      userInfoClaims = entry.claims;
      return Response.json({ access_token: "disposable-token", token_type: "Bearer", expires_in: 300, id_token: jwt({ ...entry.claims, nonce: entry.nonce }) });
    }
    throw new Error("Unexpected OIDC endpoint");
  });
  for (const [key,value] of Object.entries({ WORKSPACE_ONLY:"true", SIGNUP_ALLOWLIST:email, SIGNUPS_ENABLED:"true", AUTH_PASSWORD_ENABLED:"false", OIDC_ISSUER:issuer, OIDC_CLIENT_ID:"disposable-client", OIDC_CLIENT_SECRET:secret, OIDC_ALLOW_SIGNUP_BYPASS:"false", BETTER_AUTH_URL:origin, WEB_ORIGIN:origin, API_URL:origin, BETTER_AUTH_SECRET:secret, ENCRYPTION_KEY:secret, SCREEN_PROXY_SECRET:secret, SECRET_STORE:"encrypted", CONTENT_ENCRYPTION:"on", MASTER_KEY_PROVIDER:"local", EMAIL_PROVIDER:"none", SANDBOX_PROVIDER:"none", CLOUD_AGENT_PROVIDER:"none", USER_DEVICES_ENABLED:"false", WAKEUP_DRIVER:"graphile", NODE_ENV:"test" })) vi.stubEnv(key,value);
  try {
    handles = await createApp({ dataDir });
    expect((await handles.app.request("/ready")).status).toBe(200);
    const request = async (path: string, jar: Map<string,string>, body?: unknown, extra: Record<string,string> = {}) => {
      const response = await handles!.app.request(new Request(origin+path, { method: body === undefined ? "GET" : "POST", headers: { origin, "content-type":"application/json", cookie:[...jar].map(([k,v])=>`${k}=${v}`).join("; "), ...extra }, ...(body === undefined ? {} : { body:JSON.stringify(body) }) }));
      for (const raw of response.headers.getSetCookie()) { const pair=raw.split(";")[0]!; const split=pair.indexOf("="); jar.set(pair.slice(0,split),pair.slice(split+1)); }
      return response;
    };
    const login = async (address: string, verified: boolean) => {
      const jar = new Map<string,string>();
      const start = await request("/api/auth/sign-in/social",jar,{provider:"oidc",callbackURL:origin+"/app",errorCallbackURL:origin+"/sign-in",disableRedirect:true});
      expect(start.status, await start.clone().text()).toBe(200);
      const authorization = new URL((await start.json()).url);
      expect(authorization.searchParams.get("code_challenge_method")).toBe("S256");
      const code=randomBytes(16).toString("hex");
      codes.set(code,{nonce:authorization.searchParams.get("nonce")!,challenge:authorization.searchParams.get("code_challenge")!,claims:{sub:address,email:address,email_verified:verified,name:"Disposable owner"}});
      await request(`/api/auth/callback/oidc?state=${encodeURIComponent(authorization.searchParams.get("state")!)}&code=${code}`,jar);
      return jar;
    };
    const rpc = (name:string, jar:Map<string,string>, body:unknown={}, space?:string) => request("/rpc/"+name,jar,{json:body},space?{"x-rakazo-space-id":space}:{});
    const value = async (response:Response) => { expect(response.status,await response.clone().text()).toBe(200); return (await response.json()).json; };
    expect((await rpc("me",new Map())).status).toBe(401);
    const outsider=await login("outsider@example.test",true);
    expect((await rpc("me",outsider)).status).toBe(401);
    const unverified=await login("unverified@example.test",false);
    expect((await rpc("me",unverified)).status).toBe(401);
    const jar=await login(email,true);
    expect(await value(await rpc("me",jar))).toMatchObject({workspaceOnly:true,needsModel:false});
    expect(await value(await rpc("models/credentials",jar))).toEqual([]);
    const space=await value(await rpc("spaces/create",jar,{name:"Disposable workspace"}));
    await value(await rpc("spaces/rename",jar,{spaceId:space.id,name:"Renamed workspace"}));
    expect(JSON.stringify(await value(await rpc("spaces/list",jar)))).toContain("Renamed workspace");
    const bot=await value(await rpc("bots/create",jar,{name:"Inert draft",instructions:"Plan only"},space.id));
    expect(bot).toMatchObject({dailyCheckIns:false,fleetManagement:false});
    await value(await rpc("bots/update",jar,{botId:bot.id,name:"Updated draft",instructions:"Keep offline",expectedInstructions:"Plan only"},space.id));
    const item=await value(await rpc("scratchpad/create",jar,{botId:bot.id,title:"Persist this",notes:"Original"},space.id));
    await value(await rpc("scratchpad/update",jar,{itemId:item.id,notes:"Updated notes"},space.id));
    expect(await value(await rpc("scratchpad/list",jar,{botId:bot.id},space.id))).toEqual(expect.arrayContaining([expect.objectContaining({id:item.id,notes:"Updated notes"})]));
    // A separate authenticated read sees durable data, not a frontend mock or in-memory state.
    const secondJar=await login(email,true);
    expect(await value(await rpc("scratchpad/list",secondJar,{botId:bot.id},space.id))).toEqual(expect.arrayContaining([expect.objectContaining({id:item.id,notes:"Updated notes"})]));
    for (const procedure of ["models/connect","models/probeCatalog","threads/send","routines/create","routines/run","mcp/add","connections/begin","computer/start","bots/duplicate","onboarding/start"]) expect((await rpc(procedure,jar,{},space.id)).status).toBe(403);
    for (const path of ["/rpc","/api/account/import","/api/voice/transcribe","/api/v1/bots/test/webhook","/api/devices/connect"]) expect((await request(path,jar,{})).status).toBe(403);
    expect((await rpc("bots/update",jar,{botId:bot.id,dailyCheckIns:true},space.id)).status).toBe(403);
    await expect(handles.jobs.enqueue({ name:"run.continue",payload:{} } as never)).rejects.toThrow("disabled");
    for (const table of ["tasks","runs","user_model_credentials","routines"]) {
      const result=await ownerDb.query(`SELECT count(*)::int AS count FROM ${table}`);
      expect(result.rows[0].count,table).toBe(0);
    }
    const jobTables=await ownerDb.query("SELECT tablename FROM pg_tables WHERE schemaname='graphile_worker' AND tablename IN ('jobs','_private_jobs')");
    for (const {tablename} of jobTables.rows) expect((await ownerDb.query(`SELECT count(*)::int AS count FROM graphile_worker.${tablename}`)).rows[0].count).toBe(0);
    expect(nonIssuerRequests).toBe(0);
    expect((await ownerDb.query('SELECT count(*)::int AS count FROM "user"')).rows[0].count).toBe(1);
    await value(await rpc("scratchpad/remove",jar,{itemId:item.id},space.id));
    await value(await rpc("bots/remove",jar,{botId:bot.id},space.id));
    await value(await rpc("spaces/remove",jar,{spaceId:space.id}));
    expect((await request("/api/auth/sign-out",jar,{})).status).toBe(200);
    expect((await rpc("me",jar)).status).toBe(401);
    console.log("Verified owner-only OIDC, durable workspace/profile/scratchpad CRUD, blocked execution, zero provider requests and zero durable work.");
  } finally {
    await handles?.stop(); await ownerDb.end(); vi.unstubAllGlobals(); vi.unstubAllEnvs();
    await rm(dataDir,{recursive:true,force:true});
  }
},120_000);
