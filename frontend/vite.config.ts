import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { build, defineConfig, type Plugin } from "vite";
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

/**
 * After the build, render the home page to HTML and put it in index.html, so its text is in
 * the page as sent: visitors see it before the script runs, and AI agents and social apps that
 * never run scripts can read it. Every other page uses app.html, the same page with an empty
 * root (nginx serves it for the app's routes, and with status 404 for unknown addresses).
 */
function prerenderHome(): Plugin {
  let outDir = "dist";
  return {
    name: "sitescore-prerender-home",
    apply: "build",
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
    },
    async closeBundle() {
      // A small server build of the home page, bundled with everything it needs, then run here.
      const tmp = mkdtempSync(join(tmpdir(), "sitescore-prerender-"));
      try {
        await build({
          configFile: false,
          root: resolve(__dirname),
          plugins: [react()],
          logLevel: "error",
          ssr: { noExternal: true, target: "node" },
          build: { ssr: "src/prerender.tsx", outDir: tmp, emptyOutDir: true, rollupOptions: { output: { format: "esm" } } },
        });
        const { renderHome } = (await import(pathToFileURL(join(tmp, "prerender.js")).href)) as { renderHome: () => string };
        const html = readFileSync(`${outDir}/index.html`, "utf8");
        const empty = '<div id="root"></div>';
        if (!html.includes(empty)) throw new Error("index.html has no empty root to fill.");
        // The canonical link belongs to the home page alone.
        writeFileSync(`${outDir}/app.html`, html.replace(/\s*<!-- home-only -->[\s\S]*?<!-- \/home-only -->/, ""));
        writeFileSync(`${outDir}/index.html`, html.replace(empty, `<div id="root">${renderHome()}</div>`));
      } finally {
        rmSync(tmp, { recursive: true, force: true });
      }
    },
  };
}

export default defineConfig({
  plugins: [react(), siteFiles(), inlineThemeScript(), prerenderHome()],
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.SITESCORE_API ?? "http://localhost:8077", changeOrigin: false } },
  },
  preview: {
    port: 4173,
    proxy: { "/api": { target: process.env.SITESCORE_API ?? "http://localhost:8077", changeOrigin: false } },
  },
});
