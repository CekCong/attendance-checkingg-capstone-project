/** Read only attendance codes. Scanned URLs never become navigation targets. */
export function readSessionQr(text: string, sessionId: string): string {
  if (text.length > 512) throw new Error("This is not a session verification code.");
  let code = text.trim();
  if (/^https?:\/\//i.test(code)) {
    // Extract only the code; never navigate to a scanned address.
    try { code = new URLSearchParams(new URL(code).hash.slice(1)).get("attendance") ?? ""; }
    catch { throw new Error("This is not a session verification code."); }
  }
  if (code.startsWith("{")) {
    let payload;
    try { payload = JSON.parse(code); }
    catch { throw new Error("This is not a session verification code."); }
    if (payload?.v !== 1 || payload.session_id !== sessionId)
      throw new Error("This QR code is for a different session. Check your selection.");
    code = payload.code;
  }
  if (typeof code !== "string" || !/^[A-Za-z0-9_-]{8,128}$/.test(code))
    throw new Error("This is not a session verification code.");
  return code;
}
