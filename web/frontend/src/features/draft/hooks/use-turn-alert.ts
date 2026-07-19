'use client'

import { useEffect, useRef } from 'react'

/**
 * On-the-clock alerting. The last live-draft dress rehearsal failed because
 * nobody noticed the pick timer — the platform quietly autodrafted the whole
 * team. A silent border highlight is not enough: this hook plays a chime,
 * fires a browser notification, and flashes the tab title the moment
 * `isMyTurn` flips true (including on connect, if you're already up).
 */

let audioCtx: AudioContext | null = null

/** Two-tone chime via Web Audio — no asset required. */
function playChime() {
  try {
    audioCtx = audioCtx ?? new AudioContext()
    void audioCtx.resume()
    const t0 = audioCtx.currentTime
    for (const [freq, start] of [
      [880, 0],
      [1174.66, 0.18]
    ] as const) {
      const osc = audioCtx.createOscillator()
      const gain = audioCtx.createGain()
      osc.type = 'sine'
      osc.frequency.value = freq
      gain.gain.setValueAtTime(0.0001, t0 + start)
      gain.gain.exponentialRampToValueAtTime(0.25, t0 + start + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + start + 0.35)
      osc.connect(gain).connect(audioCtx.destination)
      osc.start(t0 + start)
      osc.stop(t0 + start + 0.4)
    }
  } catch {
    // Audio blocked (autoplay policy, no device) — notification still fires.
  }
}

/** Ask for notification permission — call from a user gesture (Connect). */
export function requestTurnNotificationPermission() {
  if (
    typeof window !== 'undefined' &&
    'Notification' in window &&
    Notification.permission === 'default'
  ) {
    void Notification.requestPermission()
  }
}

export function useTurnAlert(isMyTurn: boolean, enabled: boolean, message: string) {
  const wasMyTurn = useRef(false)

  useEffect(() => {
    if (!enabled) {
      wasMyTurn.current = false
      return
    }
    if (isMyTurn && !wasMyTurn.current) {
      playChime()
      if ('Notification' in window && Notification.permission === 'granted') {
        try {
          const notification = new Notification("You're on the clock", {
            body: message
          })
          notification.onclick = () => window.focus()
        } catch {
          // Notifications unsupported in this context — chime already fired.
        }
      }
    }
    wasMyTurn.current = isMyTurn
  }, [isMyTurn, enabled, message])

  // Flash the tab title while on the clock so a backgrounded tab screams.
  useEffect(() => {
    if (!enabled || !isMyTurn) return
    const original = document.title
    let flip = false
    const id = window.setInterval(() => {
      document.title = flip ? original : "🟢 YOU'RE ON THE CLOCK"
      flip = !flip
    }, 1000)
    return () => {
      window.clearInterval(id)
      document.title = original
    }
  }, [isMyTurn, enabled])
}
