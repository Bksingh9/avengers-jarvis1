"use client";

/**
 * Continuous wake-word listener — "Hey JARVIS" / "OK JARVIS" / "Hi JARVIS".
 *
 * Implementation notes:
 *   * SpeechRecognition runs with continuous=true + interimResults=true so
 *     we get partial transcripts as the user is still talking.
 *   * Browsers (especially Chrome) auto-stop continuous recognition after
 *     ~60s of silence or on tab-blur. We restart on `onend` to keep it alive
 *     across both. There's a small backoff so we don't spin if the mic is
 *     permanently denied.
 *   * Once the wake phrase fires, we abort our listener so the caller's
 *     `onTrigger` can start a *fresh* recognition session for the actual
 *     query (otherwise the two listeners would fight over the mic).
 *   * Toggle is persisted to localStorage so it survives page navigation.
 *   * Trigger phrases are matched on a normalized lowercase transcript:
 *     "hey jarvis", "hey jarvi", "ok jarvis", "hi jarvis", "yo jarvis".
 *     Browser STT often misses the trailing "s" or mishears "jarvis" as
 *     "java's" / "jervis" — kept loose to maximize hit rate.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getSpeechRecognition } from "@/lib/jarvis";

const STORAGE_KEY = "jarvis.wake-word.enabled";

const TRIGGERS = [
  "hey jarvis",
  "hey jarvi",
  "hey jervis",
  "hey java's",
  "ok jarvis",
  "okay jarvis",
  "hi jarvis",
  "yo jarvis",
];

function normalize(s: string): string {
  return s.toLowerCase().replace(/[^a-z\s]/g, " ").replace(/\s+/g, " ").trim();
}

function matchesTrigger(transcript: string): boolean {
  const norm = normalize(transcript);
  return TRIGGERS.some((t) => norm.includes(t));
}

export function useWakeWord(onTrigger: () => void) {
  const [enabled, setEnabledState] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    return window.localStorage.getItem(STORAGE_KEY) === "true";
  });
  const [active, setActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recogRef = useRef<any>(null);
  const restartTimerRef = useRef<number | null>(null);
  const triggerRef = useRef(onTrigger);
  triggerRef.current = onTrigger;

  const setEnabled = useCallback((v: boolean) => {
    setEnabledState(v);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, String(v));
    }
  }, []);

  const stop = useCallback(() => {
    if (restartTimerRef.current !== null) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    try {
      recogRef.current?.abort?.();
    } catch {
      /* ignore */
    }
    recogRef.current = null;
    setActive(false);
  }, []);

  useEffect(() => {
    if (!enabled) {
      stop();
      return;
    }

    const SR = getSpeechRecognition();
    if (!SR) {
      setError("voice-unsupported");
      return;
    }

    let cancelled = false;
    let permissionDenied = false;

    const start = () => {
      if (cancelled || permissionDenied) return;
      // @ts-expect-error — SR is a constructor
      const recog = new SR();
      recog.lang = "en-IN";
      recog.continuous = true;
      recog.interimResults = true;

      recog.onstart = () => {
        setActive(true);
        setError(null);
      };

      recog.onresult = (ev: any) => {
        // Walk all results since the last fire — interim + final included.
        for (let i = ev.resultIndex; i < ev.results.length; i++) {
          const transcript = ev.results[i][0]?.transcript ?? "";
          if (matchesTrigger(transcript)) {
            // Stop the wake listener BEFORE firing the trigger so the
            // caller's recognition can grab the mic.
            cancelled = true;
            try {
              recog.abort();
            } catch {
              /* ignore */
            }
            setActive(false);
            // The trigger handler will likely re-enable wake-word after its
            // own conversation finishes.
            window.setTimeout(() => triggerRef.current(), 50);
            return;
          }
        }
      };

      recog.onerror = (ev: any) => {
        if (ev.error === "not-allowed" || ev.error === "service-not-allowed") {
          permissionDenied = true;
          setError("mic-denied");
          setActive(false);
          return;
        }
        // `no-speech` and `aborted` are normal — onend will restart us.
      };

      recog.onend = () => {
        setActive(false);
        if (cancelled || permissionDenied) return;
        // Restart after a short delay so we don't busy-loop if the API is
        // misbehaving.
        restartTimerRef.current = window.setTimeout(start, 400);
      };

      recogRef.current = recog;
      try {
        recog.start();
      } catch {
        // start() throws if already started; ignore and let onend cycle us.
      }
    };

    start();

    return () => {
      cancelled = true;
      stop();
    };
  }, [enabled, stop]);

  return {
    enabled,
    setEnabled,
    active,
    error,
    supported: typeof window !== "undefined" && getSpeechRecognition() !== null,
  };
}
