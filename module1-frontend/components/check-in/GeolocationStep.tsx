"use client";

import { useEffect, useRef, useState } from "react";
import type { GeoCoordinates } from "@/lib/types";
import { GlassCard } from "./GlassCard";

type GeolocationStepProps = {
  onComplete: (coords: GeoCoordinates) => void;
  onError: (message: string) => void;
};

function mapGeoError(error: GeolocationPositionError): string {
  switch (error.code) {
    case error.PERMISSION_DENIED:
      return "Location permission was denied in the browser. Enable location for this site and try again.";
    case error.POSITION_UNAVAILABLE:
      return "Location is currently unavailable. Move to an open area or check device GPS settings.";
    case error.TIMEOUT:
      return "Location request timed out. Please try again.";
    default:
      return "Unable to read your location. Please try again.";
  }
}

export function GeolocationStep({ onComplete, onError }: GeolocationStepProps) {
  const [status, setStatus] = useState<"requesting" | "reading">("requesting");
  const finished = useRef(false);

  useEffect(() => {
    let active = true;
    if (!("geolocation" in navigator)) {
      onError("This browser does not support geolocation.");
      return;
    }

    setStatus("reading");

    navigator.geolocation.getCurrentPosition(
      (position) => {
        if (!active || finished.current) return;
        finished.current = true;
        onComplete({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
        });
      },
      (error) => {
        if (!active || finished.current) return;
        finished.current = true;
        onError(mapGeoError(error));
      },
      {
        enableHighAccuracy: true,
        timeout: 15000,
        maximumAge: 0,
      },
    );
    return () => { active = false; };
  }, [onComplete, onError]);

  return (
    <GlassCard className="w-full max-w-md p-8 text-center animate-fade-up">
      <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-full border border-white/30 bg-white/15 backdrop-blur-md">
        <span className="relative flex h-3 w-3">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-300 opacity-75" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-emerald-200" />
        </span>
      </div>
      <h2 className="font-display text-2xl font-semibold text-white">
        Confirming location
      </h2>
      <p className="mt-3 text-sm leading-relaxed text-white/80">
        {status === "requesting"
          ? "Requesting location permission…"
          : "Reading GPS coordinates for attendance verification…"}
      </p>
    </GlassCard>
  );
}
