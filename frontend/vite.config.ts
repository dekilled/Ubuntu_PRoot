import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// `base: "./"`: o Capacitor serve o build a partir dos assets do APK.
export default defineConfig({
  base: "./",
  plugins: [react()],
  server: { port: 5173, host: "127.0.0.1" },
  build: { outDir: "dist", sourcemap: false },
});
