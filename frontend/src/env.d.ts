/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend URL. Leave empty when the API is served from the same origin (/api). */
  readonly VITE_API_BASE_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
