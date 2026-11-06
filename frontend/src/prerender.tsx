import { renderToString } from "react-dom/server";
import { StaticRouter } from "react-router-dom";
import { App, Root } from "./App";

/**
 * The home page as HTML, written into index.html at build time. Visitors see the page before
 * the script loads, and AI agents and social apps that never run scripts still read it.
 */
export function renderHome(): string {
  return renderToString(
    <Root>
      <StaticRouter location="/">
        <App />
      </StaticRouter>
    </Root>,
  );
}
