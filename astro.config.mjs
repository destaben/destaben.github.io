import { defineConfig } from "astro/config";
import react from "@astrojs/react";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://info.destaben.dev",
  integrations: [react(), sitemap()],
  build: {
    format: "directory",
    inlineStylesheets: "always",
  },
});