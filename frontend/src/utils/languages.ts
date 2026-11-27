import type { LanguageShare } from '../api/types'

export interface LanguageSegment {
  label: string
  percentage: number
  bytes: number
  /** Categorical slot (1-based) or `null` for the neutral "Other" bucket. */
  slot: number | null
}

/**
 * Keep the largest languages as their own segments and fold the tail into "Other".
 * The palette has 8 validated categorical slots; past that, colors stop being distinguishable.
 */
export function groupLanguages(languages: LanguageShare[], maxSegments = 6): LanguageSegment[] {
  const sorted = [...languages].sort((a, b) => b.bytes - a.bytes)
  const head = sorted.length > maxSegments + 1 ? sorted.slice(0, maxSegments) : sorted
  const tail = sorted.slice(head.length)

  const segments: LanguageSegment[] = head.map((language, index) => ({
    label: language.language,
    percentage: language.percentage,
    bytes: language.bytes,
    slot: index + 1,
  }))
  if (tail.length > 0) {
    segments.push({
      label: `Other (${tail.length})`,
      percentage: Math.round(tail.reduce((sum, l) => sum + l.percentage, 0) * 100) / 100,
      bytes: tail.reduce((sum, l) => sum + l.bytes, 0),
      slot: null,
    })
  }
  return segments
}
