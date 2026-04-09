'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { API_BASE, AUTH_HEADERS } from '@/lib/config'

// ─── Types ────────────────────────────────────────────────────────────────────
type VoiceState = 'idle' | 'listening' | 'transcribing' | 'waiting' | 'speaking'

interface VoiceModeProps {
  /** Whether voice mode is active */
  active: boolean
  /** Toggle voice mode on/off */
  onToggle: () => void
  /** Called with transcribed text — parent should send it as a chat message */
  onTranscript: (text: string) => void
  /** The latest assistant message text — will be spoken via TTS */
  lastAssistantMessage: string | null
  /** Whether the parent is currently waiting for an AI response */
  loading: boolean
  /** Configurable silence duration in seconds (1-5) */
  silenceDuration?: number
}

// ─── Component ────────────────────────────────────────────────────────────────
export default function VoiceMode({
  active,
  onToggle,
  onTranscript,
  lastAssistantMessage,
  loading,
  silenceDuration = 3,
}: VoiceModeProps) {
  const [state, setState] = useState<VoiceState>('idle')
  const [silenceConfig, setSilenceConfig] = useState(silenceDuration)
  const [showConfig, setShowConfig] = useState(false)
  const [pushToTalk, setPushToTalk] = useState(false)
  const [pttActive, setPttActive] = useState(false)

  // Refs for audio resources
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const silenceCheckRef = useRef<number | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const blobUrlRef = useRef<string | null>(null)
  const lastSpokenRef = useRef<string | null>(null)
  const activeRef = useRef(active)
  const configRef = useRef<HTMLDivElement>(null)

  // Keep activeRef in sync
  useEffect(() => { activeRef.current = active }, [active])

  // ─── Cleanup all audio resources ──────────────────────────────────────────
  const cleanupAudio = useCallback(() => {
    if (silenceCheckRef.current) cancelAnimationFrame(silenceCheckRef.current)
    silenceCheckRef.current = null

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.onstop = null
      mediaRecorderRef.current.stop()
    }
    mediaRecorderRef.current = null

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }

    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {})
      audioCtxRef.current = null
    }
    analyserRef.current = null
    chunksRef.current = []

    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current = null
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
  }, [])

  // ─── Transcribe recorded audio ────────────────────────────────────────────
  const transcribe = useCallback(async (blob: Blob) => {
    if (!activeRef.current) return
    setState('transcribing')
    try {
      const formData = new FormData()
      formData.append('file', blob, 'recording.webm')

      const resp = await fetch(`${API_BASE}/v1/audio/transcribe`, {
        method: 'POST',
        headers: { Authorization: AUTH_HEADERS['Authorization'] },
        body: formData,
      })

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail || `Transcription failed (${resp.status})`)
      }

      const data = await resp.json()
      if (data.text && data.text.trim()) {
        setState('waiting')
        onTranscript(data.text.trim())
      } else {
        // No speech detected — go back to listening
        if (activeRef.current) startListening()
        else setState('idle')
      }
    } catch (err) {
      console.error('Voice mode transcription error:', err)
      if (activeRef.current) startListening()
      else setState('idle')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [onTranscript])

  // ─── Start listening (recording) ──────────────────────────────────────────
  const startListening = useCallback(async () => {
    if (!activeRef.current) return
    setState('listening')

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      const audioCtx = new AudioContext()
      audioCtxRef.current = audioCtx
      const source = audioCtx.createMediaStreamSource(stream)
      const analyser = audioCtx.createAnalyser()
      analyser.fftSize = 2048
      analyser.smoothingTimeConstant = 0.8
      source.connect(analyser)
      analyserRef.current = analyser

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : ''

      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined)
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType || 'audio/webm' })
        chunksRef.current = []
        if (blob.size > 0) {
          transcribe(blob)
        } else {
          if (activeRef.current) startListening()
          else setState('idle')
        }
      }

      recorder.start(250)

      // Silence detection (only in auto mode, not push-to-talk)
      if (!pushToTalk) {
        const dataArray = new Uint8Array(analyser.frequencyBinCount)
        let silenceStart: number | null = null
        const SILENCE_THRESHOLD = 15
        const SILENCE_MS = silenceConfig * 1000

        const checkSilence = () => {
          if (!analyserRef.current || !mediaRecorderRef.current) return
          if (mediaRecorderRef.current.state === 'inactive') return
          analyserRef.current.getByteTimeDomainData(dataArray)

          let sum = 0
          for (let i = 0; i < dataArray.length; i++) {
            const v = (dataArray[i] - 128) / 128
            sum += v * v
          }
          const rms = Math.sqrt(sum / dataArray.length) * 100

          if (rms < SILENCE_THRESHOLD) {
            if (!silenceStart) silenceStart = Date.now()
            else if (Date.now() - silenceStart > SILENCE_MS) {
              stopListening()
              return
            }
          } else {
            silenceStart = null
          }

          silenceCheckRef.current = requestAnimationFrame(checkSilence)
        }
        silenceCheckRef.current = requestAnimationFrame(checkSilence)
      }
    } catch (err) {
      console.error('Voice mode mic error:', err)
      setState('idle')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transcribe, silenceConfig, pushToTalk])

  // ─── Stop listening ───────────────────────────────────────────────────────
  const stopListening = useCallback(() => {
    if (silenceCheckRef.current) cancelAnimationFrame(silenceCheckRef.current)
    silenceCheckRef.current = null

    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop() // triggers onstop → transcribe
    }

    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }

    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {})
      audioCtxRef.current = null
    }
    analyserRef.current = null
  }, [])

  // ─── Speak the AI response via TTS ────────────────────────────────────────
  const speak = useCallback(async (text: string) => {
    if (!activeRef.current) return
    setState('speaking')

    try {
      const resp = await fetch(`${API_BASE}/v1/audio/synthesize`, {
        method: 'POST',
        headers: { ...AUTH_HEADERS, 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: text.slice(0, 4096), voice: 'alloy' }),
      })

      if (!resp.ok) {
        // TTS failed — skip speaking, go back to listening
        if (activeRef.current) startListening()
        else setState('idle')
        return
      }

      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      blobUrlRef.current = url
      const audio = new Audio(url)
      audioRef.current = audio

      audio.onended = () => {
        if (blobUrlRef.current) {
          URL.revokeObjectURL(blobUrlRef.current)
          blobUrlRef.current = null
        }
        audioRef.current = null
        // Loop: go back to listening
        if (activeRef.current) startListening()
        else setState('idle')
      }

      audio.onerror = () => {
        if (blobUrlRef.current) {
          URL.revokeObjectURL(blobUrlRef.current)
          blobUrlRef.current = null
        }
        audioRef.current = null
        if (activeRef.current) startListening()
        else setState('idle')
      }

      await audio.play()
    } catch {
      if (activeRef.current) startListening()
      else setState('idle')
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [startListening])

  // ─── When voice mode activates, start listening ───────────────────────────
  useEffect(() => {
    if (active) {
      lastSpokenRef.current = null
      startListening()
    } else {
      cleanupAudio()
      setState('idle')
    }
    return () => {
      if (!active) return
      cleanupAudio()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active])

  // ─── When AI responds, speak it ───────────────────────────────────────────
  useEffect(() => {
    if (!active || !lastAssistantMessage) return
    if (state !== 'waiting') return
    if (loading) return
    // Don't re-speak the same message
    if (lastAssistantMessage === lastSpokenRef.current) return

    lastSpokenRef.current = lastAssistantMessage
    speak(lastAssistantMessage)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active, lastAssistantMessage, loading, state])

  // ─── Push-to-talk: spacebar ───────────────────────────────────────────────
  useEffect(() => {
    if (!active || !pushToTalk) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat) return
      // Don't capture if user is typing in an input
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      e.preventDefault()
      if (state === 'idle' || state === 'listening') {
        setPttActive(true)
        if (state !== 'listening') startListening()
      }
    }

    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      e.preventDefault()
      if (pttActive) {
        setPttActive(false)
        stopListening()
      }
    }

    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [active, pushToTalk, state, pttActive, startListening, stopListening])

  // ─── Close config dropdown on outside click ───────────────────────────────
  useEffect(() => {
    if (!showConfig) return
    const handler = (e: MouseEvent) => {
      if (configRef.current && !configRef.current.contains(e.target as Node)) {
        setShowConfig(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showConfig])

  // ─── State label ──────────────────────────────────────────────────────────
  const stateLabel: Record<VoiceState, string> = {
    idle: 'Voice Mode Off',
    listening: pushToTalk && pttActive ? 'Listening (hold Space)…' : 'Listening…',
    transcribing: 'Transcribing…',
    waiting: 'Thinking…',
    speaking: 'Speaking…',
  }

  if (!active) return null

  return (
    <div className="flex items-center justify-center py-2 px-4 bg-orange-50/80 dark:bg-orange-950/30 border-t border-orange-200 dark:border-orange-800 flex-shrink-0">
      <div className="flex items-center gap-4">
        {/* Voice state indicator */}
        <div className="flex items-center gap-2">
          {/* Pulsing mic icon */}
          <div className={`relative flex items-center justify-center w-8 h-8 rounded-full transition-colors ${
            state === 'listening'
              ? 'bg-red-100 dark:bg-red-900/40 text-red-500'
              : state === 'speaking'
                ? 'bg-green-100 dark:bg-green-900/40 text-green-500'
                : state === 'transcribing' || state === 'waiting'
                  ? 'bg-orange-100 dark:bg-orange-900/40 text-orange-500'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-400'
          }`}>
            {state === 'listening' ? (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
                </svg>
                <span className="absolute inset-0 rounded-full border-2 border-red-400 animate-ping opacity-40" />
              </>
            ) : state === 'speaking' ? (
              /* Waveform-like icon */
              <div className="flex items-center gap-0.5">
                {[0, 1, 2, 3, 4].map(i => (
                  <div
                    key={i}
                    className="w-0.5 bg-green-500 rounded-full animate-pulse"
                    style={{
                      height: `${8 + Math.sin(i * 1.5) * 6}px`,
                      animationDelay: `${i * 100}ms`,
                      animationDuration: '0.6s',
                    }}
                  />
                ))}
              </div>
            ) : state === 'transcribing' || state === 'waiting' ? (
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
              </svg>
            )}
          </div>

          <span className="text-xs font-medium text-gray-600 dark:text-gray-300">
            {stateLabel[state]}
          </span>
        </div>

        {/* Config button */}
        <div className="relative" ref={configRef}>
          <button
            onClick={() => setShowConfig(p => !p)}
            className="p-1.5 rounded-md hover:bg-orange-100 dark:hover:bg-orange-900/30 text-gray-400 hover:text-orange-600 transition-colors"
            title="Voice settings"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>

          {showConfig && (
            <div className="absolute bottom-full mb-2 right-0 w-56 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-xl shadow-lg p-3 space-y-3 z-50">
              <div>
                <label className="text-xs font-medium text-gray-600 dark:text-gray-300 block mb-1">
                  Silence duration: {silenceConfig}s
                </label>
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={0.5}
                  value={silenceConfig}
                  onChange={e => setSilenceConfig(Number(e.target.value))}
                  className="w-full accent-orange-500"
                />
                <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                  <span>1s</span>
                  <span>5s</span>
                </div>
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={pushToTalk}
                  onChange={e => setPushToTalk(e.target.checked)}
                  className="rounded border-gray-300 text-orange-500 focus:ring-orange-500"
                />
                <span className="text-xs text-gray-600 dark:text-gray-300">Push-to-talk (hold Space)</span>
              </label>
            </div>
          )}
        </div>

        {/* Stop button */}
        <button
          onClick={onToggle}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 text-white text-xs font-medium transition-colors"
          title="Stop voice mode"
        >
          <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
          Stop
        </button>
      </div>
    </div>
  )
}

// ─── Toggle Button (for chat header) ────────────────────────────────────────
export function VoiceModeToggle({ active, onToggle }: { active: boolean; onToggle: () => void }) {
  return (
    <button
      onClick={onToggle}
      title={active ? 'Stop voice mode' : 'Start voice mode'}
      className={`relative text-xs p-1 rounded-md transition-colors ${
        active
          ? 'bg-orange-100 dark:bg-orange-900/40 text-orange-600 dark:text-orange-400 hover:bg-orange-200 dark:hover:bg-orange-800/50'
          : 'hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500 hover:text-orange-600'
      }`}
    >
      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={active ? 2.5 : 2}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z" />
      </svg>
      {active && <span className="absolute -top-0.5 -right-0.5 w-2 h-2 bg-red-500 rounded-full animate-pulse" />}
    </button>
  )
}
