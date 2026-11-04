import { m } from "motion/react";
import type { CheckResult, Scan } from "../api";
import { AGENT_AREA, AGENT_SCORED } from "../checks";
import { EASE_OUT } from "../motion";
import StatusIcon from "./StatusIcon";

const TONE = { good: "pass", attention: "warn", risk: "fail" } as const;

/** The AI agent readiness score: shown first on the results page, before website health. */
export default function AgentReadiness({ scan, byKey }: { scan: Scan; byKey: Record<string, CheckResult> }) {
  const a = scan.agent;
  const tone = a.band ? TONE[a.band] : null;
  const passed = AGENT_SCORED.filter((c) => byKey[c.key]?.status === "pass").length;
  const llms = byKey["llms_txt"];
  const Icon = AGENT_AREA.icon;
  return (
    <section aria-labelledby="agent-title" className="glass rise-enter relative overflow-hidden rounded-glass p-5 sm:p-6 lg:p-7">
      <div
        className="pointer-events-none absolute -left-20 -top-24 h-72 w-72 rounded-full opacity-60 blur-3xl"
        style={{ background: "radial-gradient(circle, rgba(248,98,45,.30), transparent 70%)" }}
        aria-hidden="true"
      />
      <div className="relative grid gap-6 lg:grid-cols-[minmax(0,280px)_minmax(0,1fr)] lg:gap-8 xl:grid-cols-[minmax(0,320px)_minmax(0,1fr)] xl:gap-10">
        <div>
          <h2 id="agent-title" className="ink-brand flex items-center gap-2 text-[13px] font-semibold uppercase tracking-[0.06em]">
            <Icon size={16} aria-hidden="true" /> {AGENT_AREA.label}
          </h2>
          <div className="mt-3 flex items-end gap-3">
            <p
              className="tabular font-display text-[64px] font-bold leading-[0.9] tracking-[-0.04em] lg:text-[76px]"
              style={{ color: tone ? `var(--${tone}-ink)` : "var(--label-3)" }}
            >
              {a.score ?? "--"}
              <span className="text-3 ml-1 text-[18px] font-semibold tracking-normal">/100</span>
            </p>
          </div>
          {a.label ? (
            <span
              className="mt-3 inline-flex rounded-capsule px-3 py-1 text-[14px] font-semibold"
              style={{ background: tone ? `var(--tint-${tone})` : "var(--field-fill)", color: tone ? `var(--${tone}-ink)` : "var(--label-2)" }}
            >
              {a.label}
            </span>
          ) : null}
          <p className="text-2 mt-3 max-w-[34ch] text-[15px] leading-snug">
            {a.score === null
              ? "We could not load your site to check this."
              : `${passed} of ${AGENT_SCORED.length} passed. ${AGENT_AREA.blurb}`}
          </p>
        </div>

        <div>
          <ul className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
            {AGENT_SCORED.map((c, i) => {
              const r = byKey[c.key];
              return (
                <m.li
                  key={c.key}
                  className="flex items-start gap-3 rounded-[20px] p-3.5"
                  style={{ background: "var(--field-fill)", border: "1px solid var(--field-edge)" }}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.4, ease: EASE_OUT, delay: 0.05 + i * 0.04 }}
                >
                  <StatusIcon status={r?.status} size={24} />
                  <span className="min-w-0">
                    <span className="text-3 block text-[12px] font-semibold uppercase tracking-[0.05em]">{c.name}</span>
                    <span className="mt-0.5 block text-[15px] font-semibold leading-snug">{r?.title ?? c.blurb}</span>
                  </span>
                </m.li>
              );
            })}
          </ul>
          <p className="text-3 mt-3 px-1 text-[13px] leading-snug">
            {llms ? `${llms.title}. ` : ""}Each finding is explained under Every check below.
          </p>
        </div>
      </div>
    </section>
  );
}
