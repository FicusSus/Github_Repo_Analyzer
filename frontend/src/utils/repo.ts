const OWNER = /^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$/
const NAME = /^[A-Za-z0-9._-]{1,100}$/

/**
 * Light client-side check so obvious typos are caught before a request is sent.
 * The backend performs the authoritative parsing.
 */
export function parseRepositoryInput(raw: string): { owner: string; name: string } | null {
  let value = raw.trim()
  if (!value) return null
  value = value.replace(/^git@github\.com:/i, '').replace(/^(https?:\/\/)?(www\.)?github\.com\//i, '')
  if (/^[a-z]+:\/\//i.test(value)) return null
  const [owner, rawName] = value.split(/[/?#]/).filter(Boolean)
  if (!owner || !rawName) return null
  const name = rawName.replace(/\.git$/, '')
  if (!OWNER.test(owner) || !NAME.test(name) || name === '.' || name === '..') return null
  return { owner, name }
}

export function splitFullName(fullName: string): { owner: string; name: string } {
  const [owner = '', name = ''] = fullName.split('/')
  return { owner, name }
}
