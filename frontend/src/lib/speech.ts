export interface SpeechRecognitionEvent extends Event {
  resultIndex: number
  results: {
    length: number
    [index: number]: {
      isFinal: boolean
      [index: number]: {
        transcript: string
      }
    }
  }
}

export interface SpeechRecognitionErrorEvent extends Event {
  error: string
  message?: string
}

export interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean
  interimResults: boolean
  lang: string
  onstart: ((this: SpeechRecognitionInstance, ev: Event) => any) | null
  onend: ((this: SpeechRecognitionInstance, ev: Event) => any) | null
  onerror: ((this: SpeechRecognitionInstance, ev: SpeechRecognitionErrorEvent) => any) | null
  onresult: ((this: SpeechRecognitionInstance, ev: SpeechRecognitionEvent) => any) | null
  start(): void
  stop(): void
  abort(): void
}

export function getSpeechRecognitionClass(): (new () => SpeechRecognitionInstance) | null {
  if (typeof window === 'undefined') return null
  const SpeechRecognition =
    (window as any).SpeechRecognition ||
    (window as any).webkitSpeechRecognition ||
    null
  return SpeechRecognition
}

/**
 * Returns true if text contains Devanagari (Hindi) or Kannada characters.
 */
export function isNonEnglish(text: string): boolean {
  if (!text) return false
  return /[\u0900-\u097F\u0C80-\u0CFF]/.test(text)
}

/**
 * Cleans assistant reply text for text-to-speech reading.
 * - Removes markdown, bullets, code, URLs, sources, receipts, plan text
 * - Skips non-English replies
 * - For refusals: keeps only the first sentence
 * - For standard replies: keeps up to the first 3 sentences or ~400 characters
 */
export function cleanSpokenText(text: string, isRefusal = false): string {
  if (!text || typeof text !== 'string') return ''
  if (isNonEnglish(text)) return ''

  let cleaned = text
    // Remove code blocks and inline code
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`([^`]+)`/g, '$1')
    // Remove markdown links [title](url) -> title
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    // Remove raw URLs
    .replace(/https?:\/\/\S+/g, '')
    // Remove bold and italic markers
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/__([^_]+)__/g, '$1')
    .replace(/_([^_]+)_/g, '$1')
    // Remove headers (# ... )
    .replace(/^#{1,6}\s+/gm, '')
    // Remove bullet points and numbered list markers
    .replace(/^[\s]*[-*•]\s+/gm, '')
    .replace(/^[\s]*\d+\.\s+/gm, '')
    // Remove Sources / receipts blocks and plan headers
    .replace(/Sources\s*\(.*?\):?[\s\S]*$/i, '')
    .replace(/Plan:?[\s\S]*$/i, '')
    // Collapse excess whitespace
    .replace(/\s+/g, ' ')
    .trim()

  if (!cleaned) {
    const rawSentences = text.match(/[^.!?]+[.!?]+|\S[^.!?]*$/g) || [text]
    cleaned = (rawSentences[0] || text).slice(0, 300).trim()
  }

  if (!cleaned) return ''

  // Split into sentences using punctuation boundaries (. ! ?)
  const rawSentences = cleaned.match(/[^.!?]+[.!?]+|\S[^.!?]*$/g) || [cleaned]
  const sentences = rawSentences.map((s) => s.trim()).filter(Boolean)

  if (isRefusal) {
    // Speak at most one sentence for refusals
    return sentences[0] || cleaned
  }

  // Keep at most 3 sentences or ~400 characters
  let result = ''
  for (let i = 0; i < Math.min(3, sentences.length); i++) {
    const s = sentences[i]
    if (result && result.length + s.length + 1 > 420) {
      break
    }
    result = result ? `${result} ${s}` : s
  }

  if (!result && sentences.length > 0) {
    result = sentences[0]
  }

  if (result.length > 400) {
    const cut = result.slice(0, 400)
    const lastSpace = cut.lastIndexOf(' ')
    result = (lastSpace > 200 ? cut.slice(0, lastSpace) : cut) + '...'
  }

  return result
}

/**
 * Select preferred English voice from available synthesis voices:
 * 1. en-IN
 * 2. en-GB
 * 3. en-US
 * 4. any English voice
 * 5. default voice
 * 6. first available voice
 */
export function selectEnglishVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  if (!voices || voices.length === 0) return null

  const normalize = (v: SpeechSynthesisVoice) => (v.lang || '').replace('_', '-').toLowerCase()

  const enIN = voices.find((v) => normalize(v) === 'en-in')
  if (enIN) return enIN

  const enGB = voices.find((v) => normalize(v) === 'en-gb')
  if (enGB) return enGB

  const enUS = voices.find((v) => normalize(v) === 'en-us')
  if (enUS) return enUS

  const anyEn = voices.find((v) => normalize(v).startsWith('en'))
  if (anyEn) return anyEn

  const defaultVoice = voices.find((v) => v.default)
  if (defaultVoice) return defaultVoice

  return voices[0] || null
}
