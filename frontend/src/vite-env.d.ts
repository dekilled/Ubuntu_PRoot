/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** URL do servidor quando o app roda no navegador (definida por `npm run init`). */
  readonly VITE_DEV_BACKEND_URL?: string;
}
