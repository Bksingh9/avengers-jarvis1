"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Ear, EarOff, Mic, MicOff, Square, Volume2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  getSpeechRecognition,
  jarvisConverse,
  speak,
  stopSpeaking,
  supportsVoice,
} from "@/lib/jarvis";
import { useWakeWord } from "@/lib/wake-word";
import { cn } from "@/lib/utils";

type State = "idle" | "listening" | "thinking" | "speaking";

/**
 * Floating voice-command button. Visible on every page (mounted from
 * `app/layout.tsx`). Tap to expand into a transcript panel; hold the orb to
 * speak; JARVIS replies in voice + text without leaving the current page.
 *
 * Browser-native Web Speech API — no API keys.
 */
export function FloatingVoice() {
  const [state, setState] = useState<State>("idle");
  const [open, setOpen] = useState(false);
  const [thread, setThread] = useState<{ from: "you" | "jarvis"; text: string }[]>([]);
  const [voiceOk, setVoiceOk] = useState(false);
  const recogRef = useRef<any>(null);

  useEffect(() => {
    setVoiceOk(supportsVoice());
  }, []);

  const send = useCallback(async (text: string) => {
    setThread((p) => [...p, { from: "you", text }]);
    setState("thinking");
    try {
      const r = await jarvisConverse(text);
      setThread((p) => [...p, { from: "jarvis", text: r.text }]);
      setState("speaking");
      try {
        await speak(r.speakable);
      } catch {
        /* ignored */
      }
      setState("idle");
    } catch (e) {
      toast.error("JARVIS unreachable", { description: (e as Error).message });
      setState("idle");
    }
  }, []);

  const startListening = useCallback(() => {
    const SR = getSpeechRecognition();
    if (!SR) {
      toast.error("Voice not supported in this browser");
      return;
    }
    // @ts-expect-error — SR is a constructor
    const recog = new SR();
    recog.lang = "en-IN";
    recog.continuous = false;
    recog.interimResults = false;

    recog.onresult = (ev: any) => {
      const transcript: string = ev.results[0][0].transcript;
      send(transcript);
    };
    recog.onerror = (ev: any) => {
      setState("idle");
      if (ev.error !== "aborted") toast.error(`Voice: ${ev.error}`);
    };
    recog.onend = () => setState((s) => (s === "listening" ? "idle" : s));

    recogRef.current = recog;
    setState("listening");
    setOpen(true);
    recog.start();
  }, [send]);

  const stopAll = useCallback(() => {
    recogRef.current?.abort?.();
    stopSpeaking();
    setState("idle");
  }, []);

  // "Hey JARVIS" wake word — opt-in continuous listener. When it fires, we
  // start the same query-listening flow as a manual orb tap. Disabled
  // while we're already mid-conversation so the wake listener and the
  // query listener don't fight for the mic.
  const wake = useWakeWord(useCallback(() => {
    if (state === "idle") {
      toast("JARVIS heard you", { icon: "👂", duration: 1500 });
      startListening();
    }
  }, [state, startListening]));

  // Re-enabling wake-word after a conversation: nothing to do — the hook
  // automatically restarts on `onend`, which fires when the query
  // recognition releases the mic. The next user utterance will be the
  // next wake phrase.

  const Icon =
    state === "listening" ? MicOff :
    state === "speaking"  ? Volume2 :
    state === "thinking"  ? Square :
    Mic;

  return (
    <>
      {/* Floating orb — bottom right, always visible */}
      <div className="fixed bottom-6 right-6 z-40 flex flex-col items-end gap-3">
        <AnimatePresence>
          {open && (
            <motion.div
              initial={{ opacity: 0, y: 10, scale: 0.95 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.95 }}
              className="glass-strong w-80 max-w-[calc(100vw-3rem)] rounded-2xl shadow-glow"
            >
              <div className="flex items-center justify-between border-b border-border/60 p-3">
                <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                  JARVIS · voice
                </span>
                <div className="flex items-center gap-1">
                  {wake.supported && (
                    <button
                      type="button"
                      onClick={() => wake.setEnabled(!wake.enabled)}
                      className={cn(
                        "flex items-center gap-1.5 rounded-md px-2 py-1 text-[10px] uppercase tracking-wider transition-colors",
                        wake.enabled
                          ? "bg-success/15 text-success ring-1 ring-success/30"
                          : "text-muted-foreground hover:bg-muted hover:text-foreground",
                      )}
                      title={wake.enabled ? "Always-listening on" : "Enable 'Hey JARVIS' wake word"}
                    >
                      {wake.enabled ? <Ear size={11} /> : <EarOff size={11} />}
                      {wake.enabled
                        ? wake.active
                          ? "listening"
                          : "wake on"
                        : "wake off"}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => setOpen(false)}
                    className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label="Close"
                  >
                    <X size={14} />
                  </button>
                </div>
              </div>
              <div className="max-h-80 overflow-y-auto p-3">
                {thread.length === 0 ? (
                  <div className="space-y-2 text-center text-xs text-muted-foreground">
                    <p>Hold the orb. Ask anything, Cap Brij.</p>
                    {wake.supported && (
                      <p>
                        Or turn on{" "}
                        <button
                          type="button"
                          onClick={() => wake.setEnabled(!wake.enabled)}
                          className="text-primary underline-offset-2 hover:underline"
                        >
                          &ldquo;Hey JARVIS&rdquo;
                        </button>{" "}
                        — hands-free, always listening.
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2">
                    {thread.map((m, i) => (
                      <div
                        key={i}
                        className={cn(
                          "rounded-xl px-3 py-2 text-sm",
                          m.from === "you"
                            ? "ml-6 bg-primary/15"
                            : "mr-6 bg-muted/50",
                        )}
                      >
                        {m.text}
                      </div>
                    ))}
                    {state === "thinking" && (
                      <div className="mr-6 rounded-xl bg-muted/50 px-3 py-2 text-sm text-muted-foreground">
                        thinking…
                      </div>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          type="button"
          disabled={!voiceOk}
          onPointerDown={state === "speaking" || state === "thinking" ? stopAll : startListening}
          onClick={() => {
            if (state === "idle") setOpen((o) => !o);
          }}
          aria-label="JARVIS voice command"
          title={voiceOk ? "Hold to talk to JARVIS" : "Voice not supported"}
          className={cn(
            "relative grid h-14 w-14 place-items-center rounded-full text-white shadow-glow transition-all",
            state === "idle"      && "bg-gradient-to-br from-primary to-accent",
            state === "listening" && "scale-110 bg-gradient-to-br from-warning to-destructive",
            state === "thinking"  && "bg-gradient-to-br from-accent to-primary",
            state === "speaking"  && "bg-gradient-to-br from-success to-primary",
            !voiceOk && "opacity-40 cursor-not-allowed",
          )}
        >
          {state !== "idle" && (
            <>
              <motion.span
                aria-hidden
                className="absolute inset-0 rounded-full bg-white/20"
                animate={{ scale: [1, 1.4, 1], opacity: [0.5, 0, 0.5] }}
                transition={{ repeat: Infinity, duration: 1.8 }}
              />
              <motion.span
                aria-hidden
                className="absolute inset-0 rounded-full bg-white/10"
                animate={{ scale: [1, 1.7, 1], opacity: [0.3, 0, 0.3] }}
                transition={{ repeat: Infinity, duration: 2.4, delay: 0.4 }}
              />
            </>
          )}
          <Icon size={22} className="relative z-10" strokeWidth={1.5} />
          {/* Always-listening indicator — a green dot when the wake word is on */}
          {wake.enabled && state === "idle" && (
            <motion.span
              aria-hidden
              className={cn(
                "absolute right-0 top-0 h-3 w-3 rounded-full ring-2 ring-background",
                wake.active ? "bg-success" : "bg-warning",
              )}
              animate={wake.active ? { opacity: [1, 0.4, 1] } : { opacity: 1 }}
              transition={{ repeat: Infinity, duration: 1.6 }}
              title={wake.active ? "Listening for 'Hey JARVIS'" : "Wake word ready"}
            />
          )}
        </button>
      </div>
    </>
  );
}
