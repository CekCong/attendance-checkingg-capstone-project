import { studentRequest } from "./studentApi";

type Identity = {
  fingerprint: string;
  publicKey: string;
  privateKey: CryptoKey;
};
function openStore(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open("saiv-device-identity", 1);
    request.onupgradeneeded = () => request.result.createObjectStore("keys");
    request.onerror = () =>
      reject(
        new Error(
          "Device storage is unavailable. Enable site storage and try again.",
        ),
      );
    request.onsuccess = () => resolve(request.result);
  });
}
async function storedIdentity(userId: string): Promise<Identity> {
  if (!window.isSecureContext || !crypto.subtle)
    throw new Error("Device verification requires HTTPS or localhost.");
  const db = await openStore();
  try {
    const stored = await new Promise<Identity | undefined>(
      (resolve, reject) => {
        const request = db.transaction("keys").objectStore("keys").get(userId);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () =>
          reject(new Error("Unable to read device identity."));
      },
    );
    if (stored) return stored;
    const key = await crypto.subtle.generateKey(
      {
        name: "RSA-PSS",
        modulusLength: 2048,
        publicExponent: new Uint8Array([1, 0, 1]),
        hash: "SHA-256",
      },
      false,
      ["sign", "verify"],
    );
    const publicBytes = await crypto.subtle.exportKey("spki", key.publicKey);
    const fingerprint = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", publicBytes)),
      (b) => b.toString(16).padStart(2, "0"),
    ).join("");
    const encoded = btoa(
      String.fromCharCode(...Array.from(new Uint8Array(publicBytes))),
    );
    const identity = {
      fingerprint,
      publicKey: `-----BEGIN PUBLIC KEY-----\n${encoded.match(/.{1,64}/g)!.join("\n")}\n-----END PUBLIC KEY-----`,
      privateKey: key.privateKey,
    };
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction("keys", "readwrite");
      tx.objectStore("keys").put(identity, userId);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(new Error("Unable to save device identity."));
    });
    return identity;
  } finally {
    db.close();
  }
}
export async function prepareDevice(
  userId: string,
  token: string,
): Promise<Identity> {
  const identity = await storedIdentity(userId);
  const devices = await studentRequest<
    { device_fingerprint: string; is_active: boolean }[]
  >("/devices/my-devices", token);
  const existing = devices.find(
    (d) => d.device_fingerprint === identity.fingerprint,
  );
  if (existing && !existing.is_active)
    throw new Error(
      "This device has been deactivated. Contact your instructor.",
    );
  if (!existing)
    await studentRequest("/devices/register", token, {
      method: "POST",
      body: JSON.stringify({
        device_fingerprint: identity.fingerprint,
        public_key: identity.publicKey,
        device_name: "Attendance browser",
        platform: "web",
      }),
    });
  return identity;
}
export async function signDevice(
  identity: Identity,
  sessionId: string,
  token: string,
) {
  const ticket = await studentRequest<{ challenge: string }>(
    "/devices/challenge",
    token,
    {
      method: "POST",
      body: JSON.stringify({
        device_fingerprint: identity.fingerprint,
        session_id: sessionId,
      }),
    },
  );
  const signature = await crypto.subtle.sign(
    { name: "RSA-PSS", saltLength: 32 },
    identity.privateKey,
    new TextEncoder().encode(ticket.challenge),
  );
  return {
    device_fingerprint: identity.fingerprint,
    device_challenge: ticket.challenge,
    device_signature: btoa(
      String.fromCharCode(...Array.from(new Uint8Array(signature))),
    ),
  };
}
