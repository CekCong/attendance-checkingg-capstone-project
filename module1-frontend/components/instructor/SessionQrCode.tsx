"use client";
import { useEffect, useRef, useState } from "react";
import { studentRequest } from "@/lib/studentApi";

type Ticket = { code: string; payload: string; expires_at: string };
export function SessionQrCode({ sessionId, token }: { sessionId: string; token: string }) {
  const [ticket, setTicket] = useState<(Ticket & { image: string }) | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const generation = useRef(0);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(timer); generation.current += 1; };
  }, []);
  async function rotate() {
    const current = generation.current;
    setBusy(true); setError(""); setTicket(null);
    try {
      const QRCode = await import("qrcode");
      const issued = await studentRequest<Ticket>(`/sessions/${sessionId}/qr-code`, token, { method: "POST" });
      const image = await QRCode.toDataURL(issued.payload, { width: 280, margin: 4, errorCorrectionLevel: "M" });
      if (current === generation.current) { setTicket({ ...issued, image }); setNow(Date.now()); }
    } catch (e) { if (current === generation.current) setError((e as Error).message); }
    finally { if (current === generation.current) setBusy(false); }
  }
  const seconds = ticket ? Math.max(0, Math.ceil((Date.parse(ticket.expires_at) - now) / 1000)) : 0;
  return <div className="mt-2">
    <p className="text-sm">Issuing a QR code requires students to provide the current code. Rotating it invalidates the previous code.</p>
    <button type="button" disabled={busy} onClick={() => void rotate()} className="mt-2 underline">
      {busy ? "Issuing code…" : "Issue / rotate session QR"}
    </button>
    {ticket && seconds > 0 && <div className="mt-3">
      <img src={ticket.image} width={280} height={280} alt="Session verification QR code" className="max-w-full" />
      <p className="mt-2 break-all">Manual code: <code>{ticket.code}</code></p>
      <p>Expires in {seconds} seconds. Complete verification before it expires.</p>
    </div>}
    {ticket && seconds === 0 && <p role="status">QR code expired. Issue a new code for students still checking in.</p>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
