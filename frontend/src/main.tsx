import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { configureWebFallback } from "capacitor-proot-runtime";

import { App } from "./App";
import "./styles.css";

// No navegador (npm run dev:web) não há PRoot: o plugin aponta para o servidor que você subiu na mão.
if (import.meta.env.VITE_DEV_BACKEND_URL) configureWebFallback({ baseUrl: import.meta.env.VITE_DEV_BACKEND_URL });

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
