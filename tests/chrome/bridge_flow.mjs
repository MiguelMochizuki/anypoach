// Drives the extension's service worker (bridge.js) against a real AnyPoach server.
// usage: node bridge_flow.mjs <port> <pairing code> <session.json> <bridge.js>
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const [port, code, sessionFile, bridgePath] = process.argv.slice(2);
const stored = {};
let listener;
globalThis.chrome = {
  storage: { local: { get: async () => ({ pairingCode: stored.pairingCode }), set: async values => Object.assign(stored, values) } },
  runtime: { id: "test-extension", onMessage: { addListener: fn => { listener = fn; } } },
};
const realFetch = globalThis.fetch;
globalThis.fetch = (url, options) => realFetch(String(url).replace(":47832", `:${port}`), options);
await import(pathToFileURL(bridgePath).href);

const send = message => new Promise(resolve => {
  if (!listener(message, { id: "test-extension" }, resolve)) resolve({ ignored: true });
});
const session = JSON.parse(readFileSync(sessionFile, "utf8"));
const out = {};
out.wrongCode = await send({ anypoachBridge: "pair", code: "00000000-0000-4000-8000-000000000000" });
out.malformedCode = await send({ anypoachBridge: "pair", code: "nope" });
out.rightCode = await send({ anypoachBridge: "pair", code });
out.storedAfterPairing = stored.pairingCode === code;
out.capture = await send({ anypoachBridge: "capture", evidence: session, final: true });
out.oversized = await send({ anypoachBridge: "capture", evidence: { ...session, padding: "x".repeat(300 * 1024) }, final: true });
const bigList = Array.from({ length: 3000 }, (_, id) => ({ id, pad: "x".repeat(90) }));
out.droppedComponentsAtEnd = await send({ anypoachBridge: "capture", evidence: { ...session, componentsAtEnd: bigList }, final: true });
stored.pairingCode = "11111111-1111-4111-8111-111111111111";
out.changedCode = await send({ anypoachBridge: "capture", evidence: session, final: true });
out.foreignMessage = await new Promise(resolve => resolve(listener({ anypoachBridge: "capture", evidence: session }, { id: "someone-else" }, () => {})));
console.log(JSON.stringify(out));
