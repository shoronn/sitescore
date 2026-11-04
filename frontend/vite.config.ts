import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const SITE = "https://sitescore.maktechgroup.com";

/**
 * Files for search engines, AI agents and security researchers that carry dates, written
 * fresh on every build: the sitemap (last changed) and security.txt (must expire within a
 * year, RFC 9116). The static ones (robots.txt, llms.txt, index.md) live in public/.
 */
function siteFiles(): Plugin {
  return {
    name: "sitescore-site-files",
    apply: "build",
    generateBundle() {
      const now = new Date();
      const day = now.toISOString().slice(0, 10);
      const expires = new Date(now.getTime() + 330 * 24 * 3600 * 1000).toISOString().replace(/\.\d+Z$/, "Z");
      const pages = ["/", "/about", "/privacy", "/terms"];
      const sitemap =
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
        pages.map((p) => `  <url><loc>${SITE}${p}</loc><lastmod>${day}</lastmod></url>`).join("\n") +
        "\n</urlset>\n";
      const security = [
        "Contact: mailto:sitescore@maktechgroup.com",
        `Expires: ${expires}`,
        "Preferred-Languages: en, bn",
        `Canonical: ${SITE}/.well-known/security.txt`,
        "",
      ].join("\n");
      this.emitFile({ type: "asset", fileName: "sitemap.xml", source: sitemap });
      this.emitFile({ type: "asset", fileName: ".well-known/security.txt", source: security });
    },
  };
}

/**
 * The theme script runs before the first paint. Inlining it saves a blocking download (about
 * 0.3 s on a phone). The Content-Security-Policy forbids inline scripts except those listed by
 * hash, so the build checks that nginx lists this exact script and stops if it does not.
 */
function inlineThemeScript(): Plugin {
  const code = readFileSync(new URL("./theme-boot.js", import.meta.url), "utf8").trim();
  const hash = `'sha256-${createHash("sha256").update(code).digest("base64")}'`;
  return {
    name: "sitescore-inline-theme",
    transformIndexHtml: {
      order: "pre",
      handler(html, ctx) {
        if (ctx.server === undefined) {
          const nginx = readFileSync(new URL("./nginx/default.conf.template", import.meta.url), "utf8");
          const policies = nginx.split("\n").filter((l) => l.includes("Content-Security-Policy"));
          if (!policies.length || policies.some((l) => !l.includes(hash))) {
            throw new Error(
              `The theme script changed. Put ${hash} in script-src of every Content-Security-Policy line in nginx/default.conf.template.`,
            );
          }
        }
        return html.replace('<script src="/theme.js"></script>', `<script>${code}</script>`);
      },
    },
  };
}

export default defineConfig({
  plugins: [react(), siteFiles(), inlineThemeScript()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.SITESCORE_API ?? "http://localhost:8077", changeOrigin: false } },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: process.env.SITESCORE_API ?? "http://localhost:8077", changeOrigin: false } },
  },
});
