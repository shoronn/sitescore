import { ArrowLeft, Check, Copy, Eye, EyeOff, Loader2, LockKeyhole } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi, ApiError, type LoginStep } from "../../api";
import CodeInput from "../../components/CodeInput";
import { ErrorText } from "../../components/Form";
import { AdminHeader } from "./shared";

export default function AdminLogin() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [step, setStep] = useState<LoginStep | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [errorKey, setErrorKey] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    document.title = "Sales sign-in | SiteScore";
  }, []);

  const handle = async (fn: () => Promise<LoginStep>) => {
    setBusy(true);
    setError(null);
    try {
      const next = await fn();
      if (next.step === "done") navigate("/admin", { replace: true });
      else {
        setStep(next);
        setCode("");
      }
    } catch (e) {
      setError((e as ApiError).message);
      setErrorKey((k) => k + 1);
      setCode("");
    } finally {
      setBusy(false);
    }
  };

  const submitCode = (value: string) => {
    if (step?.step === "enroll") handle(() => adminApi.enroll(step.enroll_token, value));
    else handle(() => adminApi.login(email.trim(), password, value));
  };

  const back = () => {
    setStep(null);
    setError(null);
    setCode("");
  };

  return (
    <>
      <AdminHeader staff={null} />
      <main className="relative z-10 mx-auto w-full max-w-md px-5 pb-16 pt-10">
        <div className="glass rise-enter rounded-glass p-6 sm:p-7">
          {!step ? (
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                handle(() => adminApi.login(email.trim(), password));
              }}
            >
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl" style={{ background: "var(--tint-brand)" }} aria-hidden="true">
                <LockKeyhole size={22} className="ink-brand" />
              </span>
              <div>
                <h1 className="font-display text-[26px] font-bold tracking-tight">Sales sign-in</h1>
                <p className="text-2 mt-0.5 text-[15px]">For MAKTECH staff only.</p>
              </div>
              <div>
                <label htmlFor="staff-email" className="mb-1.5 block px-1 text-[14px] font-semibold">Email</label>
                <input
                  id="staff-email"
                  className="field"
                  type="email"
                  autoComplete="username"
                  inputMode="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div>
                <label htmlFor="staff-password" className="mb-1.5 block px-1 text-[14px] font-semibold">Password</label>
                <div className="relative">
                  <input
                    id="staff-password"
                    className="field pr-14"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="text-2 absolute right-1.5 top-1/2 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-xl"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    aria-pressed={showPassword}
                  >
                    {showPassword ? <EyeOff size={19} aria-hidden="true" /> : <Eye size={19} aria-hidden="true" />}
                  </button>
                </div>
              </div>
              {error ? <ErrorText>{error}</ErrorText> : null}
              <button className="btn-primary w-full" disabled={busy} aria-busy={busy || undefined}>
                {busy ? <Loader2 className="spin" size={20} aria-hidden="true" /> : null}
                {busy ? "Checking..." : "Continue"}
              </button>
            </form>
          ) : step.step === "enroll" ? (
            <div className="space-y-4">
              <h1 className="balance font-display text-[24px] font-bold leading-tight tracking-tight">Set up your authenticator app</h1>
              <p className="text-2 text-[15px] leading-snug">
                Open Google Authenticator, Microsoft Authenticator or a similar app, tap Add, and scan this code. You'll need it every time you sign in.
              </p>
              <div
                className="qr mx-auto w-52 rounded-2xl bg-white p-2.5"
                style={{ boxShadow: "0 0 0 1px var(--hairline), 0 8px 24px -12px rgba(0,0,0,.3)" }}
                role="img"
                aria-label="QR code for your authenticator app"
                dangerouslySetInnerHTML={{ __html: step.qr_svg }}
              />
              <SetupKey secret={step.secret} />
              <p className="pt-1 text-[15px] font-semibold">Then enter the 6-digit code the app shows:</p>
              <CodeInput value={code} onChange={setCode} onComplete={submitCode} invalid={!!error} disabled={busy} errorKey={errorKey} />
              {error ? <ErrorText>{error}</ErrorText> : null}
              <button type="button" className="link-quiet" onClick={back}>
                <ArrowLeft size={16} aria-hidden="true" /> Back
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              <h1 className="font-display text-[24px] font-bold tracking-tight">Enter your code</h1>
              <p className="text-2 text-[15px] leading-snug">Open your authenticator app and enter the 6-digit code for SiteScore.</p>
              <CodeInput value={code} onChange={setCode} onComplete={submitCode} invalid={!!error} disabled={busy} errorKey={errorKey} />
              {error ? <ErrorText>{error}</ErrorText> : null}
              <button type="button" className="link-quiet" onClick={back}>
                <ArrowLeft size={16} aria-hidden="true" /> Use a different account
              </button>
            </div>
          )}
        </div>
      </main>
    </>
  );
}

/** The manual setup key, in groups of four so it can be typed without mistakes. */
function SetupKey({ secret }: { secret: string }) {
  const [copied, setCopied] = useState(false);
  const groups = secret.match(/.{1,4}/g) ?? [secret];
  return (
    <div className="rounded-2xl p-3 text-center" style={{ background: "var(--field-fill)", border: "1px solid var(--field-edge)" }}>
      <p className="text-2 text-[13px] font-medium">Can't scan? Enter this key in the app:</p>
      <div className="mt-1.5 flex items-center justify-center gap-2">
        {/* Plain text with spaces: it wraps only between groups and copies cleanly. */}
        <span className="select-all font-mono text-[14px] font-semibold leading-relaxed tracking-wide [word-spacing:0.25em]" style={{ color: "var(--label)" }}>
          {groups.join(" ")}
        </span>
        <button
          type="button"
          className="text-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-xl"
          aria-label={copied ? "Key copied" : "Copy key"}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(secret);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            } catch {
              /* clipboard blocked: the key can still be selected */
            }
          }}
        >
          {copied ? <Check size={17} className="ink-pass" aria-hidden="true" /> : <Copy size={17} aria-hidden="true" />}
        </button>
      </div>
    </div>
  );
}
