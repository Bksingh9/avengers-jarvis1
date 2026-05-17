"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Bell, Volume2, VolumeX, X } from "lucide-react";
import { useEffect, useState } from "react";
import { jarvisProactive, speak, stopSpeaking, supportsVoice, type ProactiveResponse } from "@/lib/jarvis";

interface Props {
  intervalMs?: number;     // default: 15 min
  autoSpeak?: boolean;     // default: false (must be user-toggled per browser policy)
}

/**
 * "Cap Brij — here's what you need now." Polls the JARVIS proactive endpoint
 * on an interval and shows a dismissable banner above the dashboard. Optional
 * TTS readout when the user has explicitly enabled voice.
 */
export function ProactiveBanner({ intervalMs = 15 * 60_000, autoSpeak = false }: Props) {
  const [data, setData] = useState<ProactiveResponse | null>(null);
  const [dismissed, setDismissed] = useState<string | null>(null);
  const [speakEnabled, setSpeakEnabled] = useState(autoSpeak);
  const [speaking, setSpeaking] = useState(false);
  const hasVoice = typeof window !== "undefined" && supportsVoice();

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const r = await jarvisProactive();
        if (!cancelled) setData(r);
      } catch {
        // Silent — backend may be cold; we'll try again next tick.
      }
    };
    tick();
    const id = setInterval(tick, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [intervalMs]);

  // When new content arrives and TTS is enabled, read it.
  useEffect(() => {
    if (!data || !speakEnabled || dismissed === data.headline) return;
    setSpeaking(true);
    speak(data.speakable).catch(() => undefined).finally(() => setSpeaking(false));
  }, [data, speakEnabled, dismissed]);

  if (!data || dismissed === data.headline) return null;

  return (
    <AnimatePresence>
      <motion.div
        key={data.headline}
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className="glass-strong mb-4 flex items-start gap-3 rounded-2xl border-l-4 border-primary p-4"
      >
        <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-primary/20 text-primary">
          <Bell size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{data.headline}</p>
          <p className="mt-1 text-xs text-muted-foreground">{data.body}</p>
        </div>
        <div className="flex shrink-0 gap-1">
          {hasVoice && (
            <button
              type="button"
              onClick={() => {
                if (speaking) {
                  stopSpeaking();
                  setSpeaking(false);
                } else {
                  setSpeakEnabled(true);
                  speak(data.speakable).catch(() => undefined);
                }
              }}
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              aria-label={speaking ? "Stop speaking" : "Speak"}
              title={speaking ? "Stop" : "Speak"}
            >
              {speaking ? <VolumeX size={14} /> : <Volume2 size={14} />}
            </button>
          )}
          <button
            type="button"
            onClick={() => setDismissed(data.headline)}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Dismiss"
          >
            <X size={14} />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
