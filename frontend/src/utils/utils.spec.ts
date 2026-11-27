import { describe, expect, it } from 'vitest'
import type { LanguageShare } from '../api/types'
import {
  formatBucketDay,
  formatCompact,
  formatPercent,
  formatRelative,
  formatSignedPercent,
} from './format'
import { groupLanguages } from './languages'
import { parseRepositoryInput } from './repo'

describe('parseRepositoryInput', () => {
  it.each([
    ['vuejs/core', { owner: 'vuejs', name: 'core' }],
    ['https://github.com/vuejs/core', { owner: 'vuejs', name: 'core' }],
    ['github.com/vuejs/core/tree/main/packages', { owner: 'vuejs', name: 'core' }],
    ['git@github.com:vuejs/core.git', { owner: 'vuejs', name: 'core' }],
    ['https://github.com/vuejs/core?tab=readme', { owner: 'vuejs', name: 'core' }],
  ])('accepts %s', (input, expected) => {
    expect(parseRepositoryInput(input)).toEqual(expected)
  })

  it.each(['', 'vuejs', 'https://gitlab.com/a/b', '-bad/repo', 'owner/..', 'a b/c'])(
    'rejects %s',
    (input) => {
      expect(parseRepositoryInput(input)).toBeNull()
    },
  )
})

describe('groupLanguages', () => {
  const languages = (count: number): LanguageShare[] =>
    Array.from({ length: count }, (_, i) => ({
      language: `L${i}`,
      bytes: 100 - i,
      percentage: Math.round(((100 - i) / (count * 100)) * 10000) / 100,
    }))

  it('keeps up to seven languages without an Other bucket', () => {
    const segments = groupLanguages(languages(7))
    expect(segments).toHaveLength(7)
    expect(segments.every((s) => s.slot !== null)).toBe(true)
  })

  it('folds the tail into Other with a neutral colour', () => {
    const segments = groupLanguages(languages(10))
    expect(segments).toHaveLength(7)
    const other = segments.at(-1)
    expect(other?.label).toBe('Other (4)')
    expect(other?.slot).toBeNull()
    expect(segments.slice(0, 6).map((s) => s.slot)).toEqual([1, 2, 3, 4, 5, 6])
  })
})

describe('format helpers', () => {
  it('formats compact numbers and percentages', () => {
    expect(formatCompact(9_999)).toBe('9,999')
    expect(formatCompact(12_345)).toBe('12.3K')
    expect(formatCompact(null)).toBe('—')
    expect(formatPercent(12.345)).toBe('12.3%')
    expect(formatPercent(0.01)).toBe('<0.1%')
    expect(formatPercent(0)).toBe('0.0%')
    expect(formatSignedPercent(5)).toBe('+5.0%')
    expect(formatSignedPercent(-2.25)).toBe('-2.3%')
  })

  it('does not shift bucket dates across time zones', () => {
    expect(formatBucketDay('2026-11-23')).toBe('Nov 23')
  })

  it('formats relative times', () => {
    const now = new Date('2026-11-26T12:00:00Z')
    expect(formatRelative('2026-11-24T12:00:00Z', now)).toBe('2 days ago')
    expect(formatRelative('2026-11-26T11:59:40Z', now)).toBe('just now')
    expect(formatRelative(null, now)).toBe('—')
  })
})
