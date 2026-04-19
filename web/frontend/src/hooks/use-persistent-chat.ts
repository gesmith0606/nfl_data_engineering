'use client';

import { useChat } from '@ai-sdk/react';
import {
  DefaultChatTransport,
  lastAssistantMessageIsCompleteWithToolCalls,
  type UIMessage
} from 'ai';
import * as React from 'react';

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export interface UsePersistentChatOptions {
  /** localStorage key used for persistence. Default: 'advisor:conversation:v1' */
  storageKey?: string;
  /** Max messages retained in memory / storage. Older messages dropped first. Default: 100 */
  maxMessages?: number;
}

export interface UsePersistentChatReturn {
  messages: UIMessage[];
  sendMessage: ReturnType<typeof useChat>['sendMessage'];
  status: ReturnType<typeof useChat>['status'];
  error: Error | null;
  /** Wipe both in-memory messages and persisted storage. */
  clear: () => void;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_STORAGE_KEY = 'advisor:conversation:v1';
const DEFAULT_MAX_MESSAGES = 100;
const WRITE_DEBOUNCE_MS = 250;

// ---------------------------------------------------------------------------
// Internal helpers (SSR-safe, quota/corrupt-safe)
// ---------------------------------------------------------------------------

function isBrowser(): boolean {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined';
}

function readStoredMessages(key: string): UIMessage[] | null {
  if (!isBrowser()) return null;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) {
      // Corrupt shape — remove and start fresh
      window.localStorage.removeItem(key);
      return null;
    }
    return parsed as UIMessage[];
  } catch (err) {
    // Corrupt JSON, quota error, or private-mode denial. Wipe and recover silently.
    try {
      window.localStorage.removeItem(key);
    } catch {
      /* ignore secondary removal failure */
    }
    // eslint-disable-next-line no-console
    console.warn('[usePersistentChat] Failed to read storage; resetting.', err);
    return null;
  }
}

function writeStoredMessages(key: string, messages: UIMessage[]): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.setItem(key, JSON.stringify(messages));
  } catch (err) {
    // Safari private mode, quota exceeded, etc. — log and continue, do not crash the UI.
    // eslint-disable-next-line no-console
    console.warn('[usePersistentChat] Failed to persist messages.', err);
  }
}

function clearStoredMessages(key: string): void {
  if (!isBrowser()) return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* ignore */
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Wraps `useChat` from `@ai-sdk/react` with localStorage-backed persistence.
 *
 * Behaviour:
 *   - On mount (client only): reads `localStorage[storageKey]` and hydrates the chat.
 *   - On `messages` change: debounce-writes back (250ms trailing).
 *   - Truncates at `maxMessages` (drops oldest first).
 *   - SSR-safe: all storage access gated behind `typeof window !== 'undefined'`.
 *   - Corrupt-storage safe: on parse failure removes the key and starts fresh.
 *   - Quota/private-mode safe: storage errors are logged but never thrown.
 *
 * Both the floating ChatWidget and the dedicated /dashboard/advisor page use
 * this hook with the same default storage key, so they share conversation state.
 */
export function usePersistentChat(
  opts: UsePersistentChatOptions = {}
): UsePersistentChatReturn {
  const storageKey = opts.storageKey ?? DEFAULT_STORAGE_KEY;
  const maxMessages = opts.maxMessages ?? DEFAULT_MAX_MESSAGES;

  const transportRef = React.useRef<DefaultChatTransport<UIMessage> | null>(null);
  if (transportRef.current === null) {
    transportRef.current = new DefaultChatTransport({ api: '/api/chat' });
  }

  const chat = useChat({
    transport: transportRef.current,
    sendAutomaticallyWhen: lastAssistantMessageIsCompleteWithToolCalls
  });

  const { messages, setMessages, sendMessage, status, error } = chat;

  // ---- Hydrate once on mount (client only) -------------------------------
  const hydratedRef = React.useRef(false);
  React.useEffect(() => {
    if (hydratedRef.current) return;
    hydratedRef.current = true;
    const stored = readStoredMessages(storageKey);
    if (stored && stored.length > 0) {
      // Enforce maxMessages on hydration (drop oldest)
      const trimmed =
        stored.length > maxMessages ? stored.slice(-maxMessages) : stored;
      setMessages(trimmed);
    }
    // storageKey intentionally static across a hook's lifetime; re-keying is
    // not supported and would require a remount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---- Debounced write on every messages change --------------------------
  const writeTimerRef = React.useRef<number | null>(null);
  const latestMessagesRef = React.useRef<UIMessage[]>(messages);
  latestMessagesRef.current = messages;

  React.useEffect(() => {
    // Only write after initial hydration has had a chance to run.
    if (!hydratedRef.current) return;
    if (!isBrowser()) return;

    if (writeTimerRef.current !== null) {
      window.clearTimeout(writeTimerRef.current);
    }
    writeTimerRef.current = window.setTimeout(() => {
      const current = latestMessagesRef.current;
      // Enforce maxMessages on write (drop oldest)
      const toWrite =
        current.length > maxMessages ? current.slice(-maxMessages) : current;
      if (toWrite.length === 0) {
        // Nothing to persist — remove the key so a fresh conversation is truly fresh.
        clearStoredMessages(storageKey);
      } else {
        writeStoredMessages(storageKey, toWrite);
      }
      writeTimerRef.current = null;
    }, WRITE_DEBOUNCE_MS);

    return () => {
      if (writeTimerRef.current !== null) {
        window.clearTimeout(writeTimerRef.current);
        writeTimerRef.current = null;
      }
    };
  }, [messages, storageKey, maxMessages]);

  // ---- Enforce in-memory truncation --------------------------------------
  // If the messages array grows beyond maxMessages, trim the head so UI and
  // storage stay in lockstep.
  React.useEffect(() => {
    if (messages.length > maxMessages) {
      setMessages(messages.slice(-maxMessages));
    }
  }, [messages, maxMessages, setMessages]);

  // ---- Clear API ---------------------------------------------------------
  const clear = React.useCallback(() => {
    if (writeTimerRef.current !== null && isBrowser()) {
      window.clearTimeout(writeTimerRef.current);
      writeTimerRef.current = null;
    }
    clearStoredMessages(storageKey);
    setMessages([]);
  }, [storageKey, setMessages]);

  return {
    messages,
    sendMessage,
    status,
    // useChat types `error` as `Error | undefined`; normalise to `Error | null`.
    error: error ?? null,
    clear
  };
}
