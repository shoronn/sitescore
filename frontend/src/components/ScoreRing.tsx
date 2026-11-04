import { m } from "motion/react";
import { useEffect, useRef, useState } from "react";
import type { Band, Status } from "../api";
import { CHECKS } from "../checks";
import { EASE_OUT } from "../motion";

const STATUS_COLOR: Record<Status, string> = {
  pass: "var(--pass)",
  warn: "var(--warn)",
  fail: "var(--fail)",
  not_checked: "var(--neutral)",
};

// Text-safe versions, so the big number stays readable on light glass.
export const BAND_INK: Record<Band, string> = { good: "var(--pass-ink)", attention: "var(--warn-ink)", risk: "var(--fail-ink)" };

interface Props {
  statuses: Record<string, Status | undefined>;
  running?: boolean;
  score?: number | null;
  band?: Band | null;
  size?: number;
  caption?: string;
  /** Segments to draw: the health checks by default; the home page shows every check. */
  checks?: { key: string }[];
}

// Geometry in a 200 x 200 viewBox. Round caps reach STROKE/2 past each end of a segment,
// so the gap between segment paths must be wider than STROKE or the caps overlap and
// the ring looks beaded. GAP_UNITS is the clear space left between neighbouring caps.
const C = 100;
const R = 84;
// With many checks the segments get shorter, so the stroke and gaps get finer to keep
// each segment a clear dash rather than a dot.
function geometry(n: number) {
  const stroke = n > 26 ? 7 : n > 16 ? 8 : 10;
  const gapUnits = n > 26 ? 3 : n > 16 ? 3.5 : 5;
  return { stroke, gapDeg: ((stroke + gapUnits) / R) * (180 / Math.PI) };
}

function arc(startDeg: number, endDeg: number): string {
  const rad = (d: number) => ((d - 90) * Math.PI) / 180;
  const x1 = C + R * Math.cos(rad(startDeg));
  const y1 = C + R * Math.sin(rad(startDeg));
  const x2 = C + R * Math.cos(rad(endDeg));
  const y2 = C + R * Math.sin(rad(endDeg));
  return `M ${x1.toFixed(3)} ${y1.toFixed(3)} A ${R} ${R} 0 0 1 ${x2.toFixed(3)} ${y2.toFixed(3)}`;
}

function useCountUp(target: number | null | undefined): number | null {
  const [value, setValue] = useState<number | null>(typeof target === "number" ? 0 : null);
  useEffect(() => {
    if (typeof target !== "number") {
      setValue(null);
      return;
    }
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
      setValue(target);
      return;
    }
    let frame = 0;
    const startAt = performance.now();
    const duration = 900;
    const step = (now: number) => {
      const t = Math.min(1, (now - startAt) / duration);
      setValue(Math.round(target * (1 - Math.pow(1 - t, 3))));
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target]);
  return value;
}

/** One segment per check, coloured when the results arrive. */
export default function ScoreRing({ statuses, running = false, score, band, size = 248, caption, checks = CHECKS }: Props) {
  const n = checks.length;
  const { stroke: STROKE, gapDeg: GAP_DEG } = geometry(n);
  const step = 360 / n;
  const done = checks.filter((ch) => statuses[ch.key]).length;
  const hasScore = typeof score === "number";
  const idle = !hasScore && !running && done === 0;
  const shown = useCountUp(hasScore ? score : null);
  const mountedAt = useRef(performance.now());
  const label = hasScore
    ? `Score ${score} out of 100${caption ? `, ${caption}` : ""}`
    : running
      ? `Checking: ${done} of ${n} checks done`
      : `${n} checks`;

  // The glass lens sits inside the ring with a little air, so its edge never cuts a segment.
  const lensInset = size * ((C - R + STROKE / 2 + 7) / 200);

  return (
    <div className="relative mx-auto" style={{ width: size, height: size }} role="img" aria-label={label}>
      <div className="glass absolute rounded-full" style={{ inset: lensInset }} />
      <svg viewBox="0 0 200 200" className={`absolute inset-0 h-full w-full ${idle ? "ring-idle" : ""}`} aria-hidden="true" shapeRendering="geometricPrecision">
        {checks.map((ch, i) => {
          const s = statuses[ch.key];
          const start = i * step + GAP_DEG / 2;
          const end = (i + 1) * step - GAP_DEG / 2;
          // While a scan runs, finished checks show as progress only (brand colour); the real
          // pass, warn and fail colours appear together when the whole scan is done.
          const stroke = s ? (running ? "var(--brand)" : STATUS_COLOR[s]) : idle ? "var(--brand)" : "var(--track)";
          if (s) {
            // A finished check draws its segment in. On a page that opens with results
            // already in, the segments draw one after another around the ring.
            const fresh = performance.now() - mountedAt.current < 400;
            return (
              <m.path
                key={`${ch.key}-done`}
                d={arc(start, end)}
                fill="none"
                strokeWidth={STROKE}
                strokeLinecap="round"
                stroke={stroke}
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 1 }}
                transition={{ duration: 0.5, ease: EASE_OUT, delay: fresh ? 0.15 + i * 0.045 : 0 }}
                style={{ transition: "stroke 0.45s ease" }}
              />
            );
          }
          return (
            <path
              key={ch.key}
              d={arc(start, end)}
              fill="none"
              strokeWidth={STROKE}
              strokeLinecap="round"
              stroke={stroke}
              className={!s && running ? "seg-pending" : undefined}
              style={{
                transition: "stroke 0.45s ease",
                // Idle ring: a comet of brightness; the whole ring then rotates (see .ring-idle).
                opacity: idle ? 0.28 + 0.72 * Math.pow(i / (n - 1), 1.6) : undefined,
                // Negative delays start each segment mid-cycle, so the breathing is already running on first paint.
                animationDelay: !s && running ? `${(i % 4) * 0.2 - 1.6}s` : undefined,
              }}
            />
          );
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center" aria-hidden="true">
        {hasScore ? (
          <>
            <div
              className="tabular font-display font-bold leading-none tracking-[-0.03em]"
              style={{ fontSize: size * 0.29, color: band ? BAND_INK[band] : "var(--label)" }}
            >
              {shown ?? score}
            </div>
            <div className="text-2 mt-1.5 text-[15px] font-semibold">{caption ?? "out of 100"}</div>
          </>
        ) : running ? (
          <>
            <div className="tabular font-display font-semibold leading-none tracking-tight" style={{ fontSize: size * 0.17 }}>
              {done}
              <span className="text-3">/{n}</span>
            </div>
            <div className="text-2 mt-2 text-[15px] font-medium">checks done</div>
          </>
        ) : (
          <>
            <div className="tabular font-display font-bold leading-none tracking-tight" style={{ fontSize: size * 0.21 }}>
              {n}
            </div>
            <div className="text-2 mt-2 text-[15px] font-medium">checks, free</div>
          </>
        )}
      </div>
    </div>
  );
}
