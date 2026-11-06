import { createRoot, hydrateRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
// Bangla text uses Noto Sans Bengali. English pages never download it.
import "@fontsource/noto-sans-bengali/bengali-400.css";
import "@fontsource/noto-sans-bengali/bengali-500.css";
import "@fontsource/noto-sans-bengali/bengali-600.css";
import "@fontsource/noto-sans-bengali/bengali-700.css";
import "./index.css";
import { App, Root } from "./App";
import { getLang } from "./i18n";

const el = document.getElementById("root")!;
const tree = (
  <Root>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </Root>
);

// The home page arrives already rendered (see prerender.tsx), so it shows its text before any
// script runs; React then takes over that markup. Every other page starts empty (nginx sends
// app.html for them); if one ever gets the home page's markup, it is simply replaced. The
// markup is English, so Bangla visitors get a fresh render in Bangla instead.
if (el.firstElementChild && window.location.pathname === "/" && getLang() === "en") {
  hydrateRoot(el, tree);
} else {
  el.textContent = "";
  createRoot(el).render(tree);
}
