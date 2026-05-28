import { describe, it, expect } from 'vitest'
import { formatDate, truncate, capitalize, initials } from '@utils/format'

describe('format utils', () => {
  it('truncates strings over maxLength', () => {
    expect(truncate('Hello World', 5)).toBe('Hello…')
    expect(truncate('Hi', 10)).toBe('Hi')
  })

  it('capitalizes first letter', () => {
    expect(capitalize('hello')).toBe('Hello')
    expect(capitalize('WORLD')).toBe('World')
  })

  it('extracts initials', () => {
    expect(initials('John Doe')).toBe('JD')
    expect(initials('Alice')).toBe('AL')
  })

  it('formats date string', () => {
    const result = formatDate('2024-01-15T00:00:00.000Z')
    expect(result).toContain('2024')
  })
})
