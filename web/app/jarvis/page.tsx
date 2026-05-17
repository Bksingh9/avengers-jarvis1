"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Send, Sparkles } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { ProactiveBanner } from "@/components/jarvis/proactive-banner";
import { VoiceOrb } from "@/components/jarvis/voice-orb";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  getSpeechRecognition,
  jarvisConverse,
  speak,
  stopSpeaking,
  supportsVoice,
} from "@/lib/jarvis";
import { cn } from "@/lib/utils";

type Role = "cap" | "jarvis";
interface Msg {
  role: Role;
  text: string;
  ts: number;
  citations?: { connector: string; tool: string; ref: string }[];
}
type State = "idle" | "listening" | "thinking" | "speaking";

const SUGGESTIONS = [
  "What broke overnight?",
  "Top three things I should look at today?",
  "Show me anomalies in the last 24 hours.",
  "Catalog quality summary for this week.",
];

export default function JarvisPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [state, setState] = useState<State>("idle");
  const [draft, setDraft] = useState("");
  const [voiceOk, setVoiceOk] = useState(false);
  const recogRef = useRef<any>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setVoiceOk(supportsVoice());
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const send = useCallback(async (text: string) => {
    if (!text.trim() || state === "thinking") return;
    setMessages((prev) => [...prev, { role: "cap", text, ts: Date.now() }]);
    setDraft("");
    setState("thinking");
    try {
      const r = await jarvisConverse(text);
      setMessages((prev) => [
        ...prev,
        { role: "jarvis", text: r.text, ts: Date.now(), citations: r.citations },
      ]);
      if (voiceOk) {
        setState("speaking");
        try {
          await speak(r.speakable);
        } catch {
          /* TTS race on quick re-tap; ignore */
        }
        setState("idle");
      } else {
        setState("idle");
      }
    } catch (e) {
      toast.error("JARVIS unreachable", { description: (e as Error).message });
      setState("idle");
    }
  }, [state, voiceOk]);

  const startListening = useCallback(() => {
    if (state === "speaking") stopSpeaking();
    if (state !== "idle" && state !== "speaking") return;

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
      if (ev.error !== "aborted") {
        toast.error(`Voice: ${ev.error}`);
      }
    };
    recog.onend = () => {
      setState((s) => (s === "listening" ? "idle" : s));
    };

    recogRef.current = recog;
    setState("listening");
    recog.start();
  }, [send, state]);

  const stopListening = useCallback(() => {
    recogRef.current?.stop?.();
    setState("idle");
  }, []);

  const stopAll = useCallback(() => {
    recogRef.current?.abort?.();
    stopSpeaking();
    setState("idle");
  }, []);

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-4">
        <ProactiveBanner />

        <header className="flex items-end justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
              JARVIS · personal AI for Cap Brij
            </p>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">
              Talk to your operating system.
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Hold the orb to speak. JARVIS replies in voice + text, with every claim sourced.
            </p>
          </div>
        </header>

        {/* Conversation thread */}
        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <div ref={scrollRef} className="h-[60vh] overflow-y-auto p-4">
              {messages.length === 0 && (
                <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
                  <div className="grid h-14 w-14 place-items-center rounded-full bg-primary/10 text-primary">
                    <Sparkles size={26} />
                  </div>
                  <p className="max-w-sm text-sm text-muted-foreground">
                    JARVIS is ready, Cap Brij. Push the orb, or pick a suggestion below.
                  </p>
                  <div className="flex flex-wrap justify-center gap-2 pt-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => send(s)}
                        className="rounded-full border border-border bg-muted/30 px-3 py-1 text-xs text-muted-foreground transition-all hover:border-primary hover:bg-primary/10 hover:text-foreground"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              <div className="space-y-3">
                <AnimatePresence>
                  {messages.map((m, i) => (
                    <MessageBubble key={i} msg={m} />
                  ))}
                </AnimatePresence>
              </div>
            </div>

            {/* Composer + voice orb */}
            <div className="border-t border-border/60 p-4">
              <form
                className="flex items-end gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  send(draft);
                }}
              >
                <textarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(draft);
                    }
                  }}
                  rows={2}
                  placeholder="Type or hold the orb…"
                  disabled={state === "thinking"}
                  className="min-h-[2.5rem] flex-1 resize-none rounded-xl border border-border bg-muted/30 px-3 py-2 text-sm outline-none transition-colors focus:border-primary focus:bg-muted"
                />
                <Button type="submit" disabled={state === "thinking" || !draft.trim()}>
                  <Send size={14} />
                </Button>
              </form>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Voice orb panel */}
      <aside className="space-y-4">
        <Card>
          <CardContent className="flex flex-col items-center gap-6 p-6">
            <VoiceOrb
              state={state}
              onPress={startListening}
              onStop={state === "listening" ? stopListening : stopAll}
              disabled={!voiceOk}
            />
            {!voiceOk && (
              <p className="text-center text-xs text-muted-foreground">
                Voice unavailable in this browser. Use Chrome, Edge, or Safari.
              </p>
            )}
            <div className="w-full space-y-2 text-[11px] text-muted-foreground">
              <Row k="Tenant" v="jarvis" />
              <Row k="Mode" v={state} />
              <Row k="Voice" v={voiceOk ? "browser native" : "off"} />
              <Row k="Lang" v="en-IN" />
            </div>
          </CardContent>
        </Card>
      </aside>
    </div>
  );
}

function MessageBubble({ msg }: { msg: Msg }) {
  const isCap = msg.role === "cap";
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn("flex", isCap ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-snug",
          isCap
            ? "bg-primary/15 text-foreground"
            : "bg-muted/50 text-foreground",
        )}
      >
        <p>{msg.text}</p>
        {msg.citations && msg.citations.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {msg.citations.slice(0, 4).map((c, j) => (
              <span
                key={j}
                title={c.ref}
                className="rounded-full bg-background/60 px-2 py-0.5 text-[10px] text-muted-foreground"
              >
                {c.connector}·{c.tool}
              </span>
            ))}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b border-border/40 py-1 last:border-0">
      <span>{k}</span>
      <span className="font-medium text-foreground">{v}</span>
    </div>
  );
}
