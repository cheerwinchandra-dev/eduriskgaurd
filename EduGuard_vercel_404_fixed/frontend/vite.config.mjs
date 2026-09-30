import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Electron loads the built files from disk (file://), where the "crossorigin"
// attribute Vite adds to script/link tags can stop them from loading. Remove it.
const stripCrossorigin = {
  name: "strip-crossorigin",
  apply: "build",
  transformIndexHtml: (html) => html.replace(/ crossorigin/g, ""),
};

const isVercel = process.env.VERCEL === "1";

export default defineConfig({
  base: isVercel ? "/" : "./",
  plugins: [react(), stripCrossorigin],
  build: { outDir: "dist", emptyOutDir: true },
  server: { port: 5173, strictPort: true },
});
