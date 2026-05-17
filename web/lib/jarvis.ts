/**
 * JARVIS API client + Web Speech wrappers.
 *
 * Voice uses the browser's native SpeechRecognition (STT) and
 * SpeechSynthesis (TTS) — zero API keys, works in Chrome / Edge / Safari.
 * Firefox has limited support; we fall back to text-only there.
 */

import { authHeaders, DEMO_TENANT } from "@/lib/auth";

const API_BASE = typeof window === "undefined" ? "http://localhost:8080" : "/api/avengers";

export interface ConverseResponse {
  text: string;
  speakable: string;
  cost_usd: number;
  citations: { connector: string; tool: string; ref: string }[];
}

export interface ProactiveResponse {
  headline: string;
  body: string;
  speakable: string;
  sections: { agent: string; status: string; cost_usd: number }[];
  total_cost_usd: number;
}

export async function jarvisConverse(query: string): Promise<ConverseResponse> {
  const res = await fetch(`${API_BASE}/tenants/${DEMO_TENANT}/jarvis/converse`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ query, voice_mode: true }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`converse ${res.status}: ${await res.text()}`);
  return res.json();
}

export async function jarvisProactive(): Promise<ProactiveResponse> {
  const res = await fetch(`${API_BASE}/tenants/${DEMO_TENANT}/jarvis/proactive`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: "{}",
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`proactive ${res.status}: ${await res.text()}`);
  return res.json();
}

// ---- Voice: STT --------------------------------------------------------

type SR = typeof window extends { SpeechRecognition: infer T } ? T : never;

export function getSpeechRecognition(): SR | null {
  if (typeof window === "undefined") return null;
  // @ts-expect-error — webkit prefix on Safari/Chrome
  const Ctor = window.SpeechRecognition || window.webkitSpeechRecognition;
  return Ctor ?? null;
}

export function supportsVoice(): boolean {
  if (typeof window === "undefined") return false;
  return getSpeechRecognition() !== null && "speechSynthesis" in window;
}

// ---- Voice: TTS --------------------------------------------------------

/**
 * Speak `text` using the browser's SpeechSynthesis. Picks a UK or AU English
 * voice when available so JARVIS doesn't sound like a US weather forecast.
 * Returns a promise that resolves when speech ends or rejects on error.
 */
export function speak(text: string, opts: { rate?: number; pitch?: number } = {}): Promise<void> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      reject(new Error("TTS unavailable"));
      return;
    }
    const utt = new SpeechSynthesisUtterance(text);
    utt.rate = opts.rate ?? 1.05;
    utt.pitch = opts.pitch ?? 0.95;

    const pickVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      const preferred =
        voices.find((v) => /en-GB|en-IN|en-AU/i.test(v.lang)) ??
        voices.find((v) => /en-/i.test(v.lang)) ??
        voices[0];
      if (preferred) utt.voice = preferred;
    };
    if (window.speechSynthesis.getVoices().length === 0) {
      window.speechSynthesis.onvoiceschanged = () => pickVoice();
    } else {
      pickVoice();
    }

    utt.onend = () => resolve();
    utt.onerror = (e) => reject(new Error(`tts: ${e.error}`));
    window.speechSynthesis.cancel(); // stop any in-flight utterance
    window.speechSynthesis.speak(utt);
  });
}

export function stopSpeaking(): void {
  if (typeof window !== "undefined" && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
}
