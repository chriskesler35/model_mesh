'use client'

import { useState, useRef, useCallback } from 'react'
import { API_BASE, AUTH_HEADERS } from '@/lib/config'

// ─── Constants ────────────────────────────────────────────────────────────────

const STT_PROVIDERS = [
  { value: 'openai', label: 'OpenAI Whisper' },
  { value: 'google', label: 'Google Speech-to-Text' },
]

const TTS_PROVIDERS = [
  { value: 'openai', label: 'OpenAI TTS' },
  { value: 'google', label: 'Google TTS' },
  { value: 'elevenlabs', label: 'ElevenLabs' },
]

const VOICES: Record<string, { value: string; label: string }[]> = {
  openai: [
    { value: 'alloy', label: 'Alloy' },
    { value: 'echo', label: 'Echo' },
    { value: 'fable', label: 'Fable' },
    { value: 'onyx', label: 'Onyx' },
    { value: 'nova', label: 'Nova' },
    { value: 'shimmer', label: 'Shimmer' },
  ],
  google: [
    { value: 'en-US-Standard-A', label: 'Standard A (Female)' },
    { value: 'en-US-Standard-B', label: 'Standard B (Male)' },
    { value: 'en-US-Standard-C', label: 'Standard C (Female)' },
    { value: 'en-US-Standard-D', label: 'Standard D (Male)' },
  ],
  elevenlabs: [
    { value: 'rachel', label: 'Rachel' },
    { value: 'drew', label: 'Drew' },
    { value: 'clyde', label: 'Clyde' },
    { value: 'paul', label: 'Paul' },
    { value: 'domi', label: 'Domi' },
    { value: 'dave', label: 'Dave' },
  ],
}

const PLAYBACK_SPEEDS = [
  { value: 0.5, label: '0.5x' },
  { value: 1, label: '1x' },
  { value: 1.25, label: '1.25x' },
  { value: 1.5, label: '1.5x' },
  { value: 2, label: '2x' },
]

// ─── Types ────────────────────────────────────────────────────────────────────

interface VoiceSettings {
  sttProvider: string
  ttsProvider: string
  voice: string
  playbackSpeed: number
  silenceSensitivity: number
  sttApiKey: string
  ttsApiKey: string
}

const DEFAULT_SETTINGS: VoiceSettings = {
  sttProvider: 'openai',
  ttsProvider: 'openai',
  voice: 'alloy',
  playbackSpeed: 1,
  silenceSensitivity: 3,
  sttApiKey: '',
  ttsApiKey: '',
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function VoiceAudioTab() {
  const [settings, setSettings] = useState<VoiceSettings>(() => {
    if (typeof window === 'undefined') return DEFAULT_SETTINGS
    try {
      const stored = localStorage.getItem('devforge_voice_settings')
      return stored ? { ...DEFAULT_SETTINGS, ...JSON.parse(stored) } : DEFAULT_SETTINGS
    } catch {
      return DEFAULT_SETTINGS
    }
  })
  const [saved, setSaved] = useState(false)
  const [micTesting, setMicTesting] = useState(false)
  const [micResult, setMicResult] = useState<'success' | 'error' | null>(null)
  const [speakerTesting, setSpeakerTesting] = useState(false)
  const [speakerResult, setSpeakerResult] = useState<'success' | 'error' | null>(null)
  const micStreamRef = useRef<MediaStream | null>(null)

  const update = useCallback((partial: Partial<VoiceSettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...partial }
      // Reset voice when TTS provider changes
      if (partial.ttsProvider && partial.ttsProvider !== prev.ttsProvider) {
        const voices = VOICES[partial.ttsProvider]
        next.voice = voices?.[0]?.value || ''
      }
      return next
    })
    setSaved(false)
  }, [])

  const save = useCallback(() => {
    try {
      localStorage.setItem('devforge_voice_settings', JSON.stringify(settings))
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (e) {
      console.error('Failed to save voice settings:', e)
    }
  }, [settings])

  // ─── Test Microphone ──────────────────────────────────────────────────────

  const testMicrophone = useCallback(async () => {
    setMicTesting(true)
    setMicResult(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      micStreamRef.current = stream

      const mediaRecorder = new MediaRecorder(stream)
      const chunks: Blob[] = []

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.push(e.data)
      }

      mediaRecorder.onstop = () => {
        stream.getTracks().forEach(t => t.stop())
        micStreamRef.current = null

        const blob = new Blob(chunks, { type: 'audio/webm' })
        const url = URL.createObjectURL(blob)
        const audio = new Audio(url)
        audio.playbackRate = settings.playbackSpeed
        audio.onended = () => {
          URL.revokeObjectURL(url)
          setMicResult('success')
          setMicTesting(false)
        }
        audio.onerror = () => {
          URL.revokeObjectURL(url)
          setMicResult('error')
          setMicTesting(false)
        }
        audio.play()
      }

      mediaRecorder.start()
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop()
        }
      }, 3000)
    } catch {
      setMicResult('error')
      setMicTesting(false)
    }
  }, [settings.playbackSpeed])

  // ─── Test Speaker ─────────────────────────────────────────────────────────

  const testSpeaker = useCallback(async () => {
    setSpeakerTesting(true)
    setSpeakerResult(null)
    try {
      const res = await fetch(`${API_BASE}/v1/voice/tts`, {
        method: 'POST',
        headers: AUTH_HEADERS,
        body: JSON.stringify({
          text: 'Hello! This is a test of your text-to-speech settings. Everything sounds great!',
          voice: settings.voice,
          provider: settings.ttsProvider,
        }),
      })

      if (!res.ok) {
        // Fallback to browser TTS if API not available
        const utterance = new SpeechSynthesisUtterance(
          'Hello! This is a test of your text-to-speech settings. Everything sounds great!'
        )
        utterance.rate = settings.playbackSpeed
        utterance.onend = () => {
          setSpeakerResult('success')
          setSpeakerTesting(false)
        }
        utterance.onerror = () => {
          setSpeakerResult('error')
          setSpeakerTesting(false)
        }
        speechSynthesis.speak(utterance)
        return
      }

      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const audio = new Audio(url)
      audio.playbackRate = settings.playbackSpeed
      audio.onended = () => {
        URL.revokeObjectURL(url)
        setSpeakerResult('success')
        setSpeakerTesting(false)
      }
      audio.onerror = () => {
        URL.revokeObjectURL(url)
        setSpeakerResult('error')
        setSpeakerTesting(false)
      }
      audio.play()
    } catch {
      // Final fallback
      try {
        const utterance = new SpeechSynthesisUtterance('Hello! Speaker test.')
        utterance.rate = settings.playbackSpeed
        utterance.onend = () => { setSpeakerResult('success'); setSpeakerTesting(false) }
        utterance.onerror = () => { setSpeakerResult('error'); setSpeakerTesting(false) }
        speechSynthesis.speak(utterance)
      } catch {
        setSpeakerResult('error')
        setSpeakerTesting(false)
      }
    }
  }, [settings.voice, settings.ttsProvider, settings.playbackSpeed])

  const currentVoices = VOICES[settings.ttsProvider] || []

  return (
    <div className="space-y-6">
      {/* Info banner */}
      <div className="bg-violet-50 border border-violet-200 rounded-lg p-4 text-sm text-violet-800">
        <strong>🎙️ Voice & Audio</strong> — Configure speech-to-text, text-to-speech providers, voice selection,
        and playback options. Use the test buttons to verify your setup.
      </div>

      {/* STT Provider */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Speech-to-Text (STT)</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Transcription Provider</label>
              <select
                value={settings.sttProvider}
                onChange={e => update({ sttProvider: e.target.value })}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
              >
                {STT_PROVIDERS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {STT_PROVIDERS.find(p => p.value === settings.sttProvider)?.label} API Key
              </label>
              <input
                type="password"
                autoComplete="off"
                value={settings.sttApiKey}
                onChange={e => update({ sttApiKey: e.target.value })}
                placeholder="Paste your API key…"
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 font-mono text-sm"
              />
              <p className="mt-1 text-xs text-gray-400">
                Leave blank to use the key configured in API Keys tab.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Silence Detection Threshold
              </label>
              <div className="flex items-center gap-4">
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={0.5}
                  value={settings.silenceSensitivity}
                  onChange={e => update({ silenceSensitivity: parseFloat(e.target.value) })}
                  className="flex-1 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-orange-500"
                />
                <span className="text-sm font-mono text-gray-700 w-12 text-right">
                  {settings.silenceSensitivity}s
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-400">
                How long to wait after silence before stopping recording (1–5 seconds).
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* TTS Provider */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Text-to-Speech (TTS)</h3>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">TTS Provider</label>
              <select
                value={settings.ttsProvider}
                onChange={e => update({ ttsProvider: e.target.value })}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
              >
                {TTS_PROVIDERS.map(p => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Voice</label>
              <select
                value={settings.voice}
                onChange={e => update({ voice: e.target.value })}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 sm:text-sm"
              >
                {currentVoices.map(v => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-400">
                Available voices depend on the selected TTS provider.
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {TTS_PROVIDERS.find(p => p.value === settings.ttsProvider)?.label} API Key
              </label>
              <input
                type="password"
                autoComplete="off"
                value={settings.ttsApiKey}
                onChange={e => update({ ttsApiKey: e.target.value })}
                placeholder="Paste your API key…"
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-orange-500 focus:ring-orange-500 font-mono text-sm"
              />
              <p className="mt-1 text-xs text-gray-400">
                Leave blank to use the key configured in API Keys tab.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Playback */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Playback</h3>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">Playback Speed</label>
            <div className="flex gap-2">
              {PLAYBACK_SPEEDS.map(s => (
                <button
                  key={s.value}
                  onClick={() => update({ playbackSpeed: s.value })}
                  className={`px-3 py-1.5 text-sm font-medium rounded-md border transition-colors ${
                    settings.playbackSpeed === s.value
                      ? 'bg-orange-500 text-white border-orange-500'
                      : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Test Buttons */}
      <div className="bg-white shadow sm:rounded-lg overflow-hidden">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-base font-semibold text-gray-900 mb-4">Test Your Setup</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Test Microphone */}
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">🎤</span>
                <h4 className="text-sm font-medium text-gray-900">Microphone</h4>
              </div>
              <p className="text-xs text-gray-500 mb-3">
                Records 3 seconds of audio and plays it back.
              </p>
              <button
                onClick={testMicrophone}
                disabled={micTesting}
                className="w-full px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {micTesting ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>
                    Recording & Playing…
                  </span>
                ) : 'Test Microphone'}
              </button>
              {micResult === 'success' && (
                <p className="mt-2 text-xs text-green-600 font-medium">✓ Microphone working</p>
              )}
              {micResult === 'error' && (
                <p className="mt-2 text-xs text-red-500 font-medium">✗ Microphone access denied or unavailable</p>
              )}
            </div>

            {/* Test Speaker */}
            <div className="border border-gray-200 rounded-lg p-4">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">🔊</span>
                <h4 className="text-sm font-medium text-gray-900">Speaker</h4>
              </div>
              <p className="text-xs text-gray-500 mb-3">
                Synthesizes a sample phrase with current TTS settings.
              </p>
              <button
                onClick={testSpeaker}
                disabled={speakerTesting}
                className="w-full px-3 py-2 text-sm font-medium rounded-md border border-gray-300 text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {speakerTesting ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                    </svg>
                    Playing…
                  </span>
                ) : 'Test Speaker'}
              </button>
              {speakerResult === 'success' && (
                <p className="mt-2 text-xs text-green-600 font-medium">✓ Speaker working</p>
              )}
              {speakerResult === 'error' && (
                <p className="mt-2 text-xs text-red-500 font-medium">✗ TTS failed — check provider and API key</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button
          onClick={save}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-orange-600 hover:bg-orange-700"
        >
          Save Voice Settings
        </button>
        {saved && <span className="text-sm text-green-600 font-medium animate-pulse">Saved!</span>}
      </div>
    </div>
  )
}
