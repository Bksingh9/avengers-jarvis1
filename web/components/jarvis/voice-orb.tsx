"use client";

import { motion } from "framer-motion";
import { Mic, MicOff, Square, Volume2 } from "lucide-react";
import { cn } from "@/lib/utils";

type State = "idle" | "listening" | "thinking" | "speaking";

interface Props {
  state: State;
  onPress: () => void;
  onStop: () => void;
  disabled?: boolean;
}

const COPY: Record<State, { hint: string; tone: string }> = {
  idle:      { hint: "Hold to talk to JARVIS", tone: "from-primary to-accent" },
  listening: { hint: "Listening…",              tone: "from-warning to-destructive" },
  thinking:  { hint: "Thinking…",               tone: "from-accent to-primary" },
  speaking:  { hint: "Speaking…",               tone: "from-success to-primary" },
};

export function VoiceOrb({ state, onPress, onStop, disabled }: Props) {
  const cfg = COPY[state];
  const Icon = state === "listening" ? MicOff : state === "speaking" ? Volume2 : state === "thinking" ? Square : Mic;
  return (
    <div className="flex flex-col items-center gap-3">
      <button
        type="button"
        disabled={disabled}
        onPointerDown={onPress}
        onPointerUp={state === "listening" ? onStop : undefined}
        onClick={state === "speaking" ? onStop : undefined}
        aria-label="JARVIS voice"
        className={cn(
          "relative grid h-32 w-32 place-items-center rounded-full transition-all",
          "bg-gradient-to-br shadow-glow text-white",
          cfg.tone,
          state !== "idle" && "scale-105",
          disabled && "opacity-40 cursor-not-allowed",
        )}
      >
        {/* Pulsing halo while active */}
        {state !== "idle" && (
          <>
            <motion.span
              aria-hidden
              className="absolute inset-0 rounded-full bg-white/20"
              animate={{ scale: [1, 1.35, 1], opacity: [0.55, 0, 0.55] }}
              transition={{ repeat: Infinity, duration: 1.8 }}
            />
            <motion.span
              aria-hidden
              className="absolute inset-0 rounded-full bg-white/10"
              animate={{ scale: [1, 1.6, 1], opacity: [0.35, 0, 0.35] }}
              transition={{ repeat: Infinity, duration: 2.4, delay: 0.4 }}
            />
          </>
        )}
        <Icon size={42} className="relative z-10" strokeWidth={1.5} />
      </button>
      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{cfg.hint}</p>
    </div>
  );
}
