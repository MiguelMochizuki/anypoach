// Adapted from the Poach Chrome extension (Apache-2.0) and changed for AnyPoach. See NOTICE.
const base = "http://127.0.0.1:47832/v1";
const queues = new Map();

async function send(path, code, options = {}) {
  try {
    const response = await fetch(base + path, {
      ...options,
      headers: { Authorization: "Bearer " + code, ...options.headers },
      signal: AbortSignal.timeout(2500),
    });
    if (response.ok) return { ok: true };
    if (response.status === 401) return { error: "The pairing code changed. Pair again with the code shown in AnyPoach." };
    return { error: "AnyPoach couldn’t accept this capture." };
  } catch {
    return { error: "Open AnyPoach and try again." };
  }
}

async function handle(message) {
  if (message.anypoachBridge === "pair") {
    const code = message.code?.trim().toUpperCase();
    if (!/^[A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12}$/.test(code ?? "")) {
      return { error: "Paste the pairing code shown in AnyPoach." };
    }
    const result = await send("/pair", code);
    if (result.ok) await chrome.storage.local.set({ pairingCode: code });
    return result;
  }

  const { pairingCode } = await chrome.storage.local.get("pairingCode");
  if (!pairingCode) return { needsPairing: true, error: "Pair with AnyPoach first." };
  if (message.anypoachBridge === "ping") return send("/pair", pairingCode);
  const body = JSON.stringify(message.evidence);
  if (new Blob([body]).size > 256 * 1024) return { error: "This capture exceeds AnyPoach’s evidence limit." };
  return send("/capture", pairingCode, {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json", "X-AnyPoach-Final": message.final ? "1" : "0" },
  });
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id || !["pair", "ping", "capture"].includes(message?.anypoachBridge)) return;
  if (message.anypoachBridge === "capture" && !message.evidence) return;
  const key = message.evidence?.startedAtEpochMs ?? 0;
  const pending = queues.get(key);
  // A slow connection can drop intermediate snapshots. The final snapshot contains all evidence.
  if (pending && message.anypoachBridge === "capture" && !message.final) {
    respond({ ok: true });
    return;
  }
  const request = (pending ?? Promise.resolve()).then(() => handle(message));
  queues.set(key, request);
  request.then(respond, () => respond({ error: "Couldn’t reach AnyPoach." })).finally(() => {
    if (queues.get(key) === request) queues.delete(key);
  });
  return true;
});
