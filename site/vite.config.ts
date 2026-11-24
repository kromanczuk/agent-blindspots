import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Served from https://<user>.github.io/agent-blindspots/, so every asset path needs that prefix.
export default defineConfig({
  base: "/agent-blindspots/",
  plugins: [react()],
});
