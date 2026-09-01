import { defineConfig } from "astro/config";
import sitemap from "@astrojs/sitemap";

export default defineConfig({
  site: "https://info.destaben.dev",
  integrations: [sitemap()],
  build: {
    format: "file",
  },
});