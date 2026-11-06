import { ArrowRight, Loader2 } from "lucide-react";
import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type Lead, type PublicConfig } from "../api";
import { ErrorText, Field } from "../components/Form";
import Sheet from "../components/Sheet";
import Turnstile from "../components/Turnstile";
import { useT } from "../i18n";

/** Email and optional details. Loaded on demand, so the home page stays light. */
export default function SignInSheet({
  open,
  onClose,
  config,
  initialEmail,
  submitLabel,
  onSignedIn,
}: {
  open: boolean;
  onClose: () => void;
  config: PublicConfig | null;
  initialEmail?: string;
  submitLabel?: string;
  onSignedIn: (l: Lead) => void;
}) {
  const { t } = useT();
  const [email, setEmail] = useState(initialEmail ?? "");
  const [name, setName] = useState("");
  const [business, setBusiness] = useState("");
  const [phone, setPhone] = useState("");
  const [turnstile, setTurnstile] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const onToken = useCallback((t: string | null) => setTurnstile(t), []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const next: Record<string, string> = {};
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) next.email = t("sheet.email_invalid");
    setErrors(next);
    if (Object.keys(next).length) return;
    setBusy(true);
    try {
      const { lead } = await api.signUp({
        email: email.trim(),
        name: name || undefined,
        business_name: business || undefined,
        phone: phone || undefined,
        turnstile_token: turnstile || undefined,
      });
      onSignedIn(lead);
    } catch (err) {
      const e2 = err as ApiError;
      setErrors({ [e2.field || "form"]: e2.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={open} title={t("sheet.title")} onClose={onClose}>
      <form onSubmit={submit} noValidate className="space-y-4">
        <Field label={t("sheet.email")} error={errors.email}>
          <input
            className="field"
            type="email"
            autoComplete="email"
            inputMode="email"
            enterKeyHint="next"
            placeholder="you@yourbusiness.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </Field>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-3">
          <Field label={t("sheet.name")} optional error={errors.name}>
            <input className="field" autoComplete="name" enterKeyHint="next" value={name} onChange={(e) => setName(e.target.value)} />
          </Field>
          <Field label={t("sheet.business")} optional error={errors.business_name}>
            <input className="field" autoComplete="organization" enterKeyHint="next" value={business} onChange={(e) => setBusiness(e.target.value)} />
          </Field>
        </div>
        <Field label={t("sheet.phone")} optional error={errors.phone}>
          <input
            className="field"
            type="tel"
            autoComplete="tel"
            inputMode="tel"
            placeholder="01XXXXXXXXX"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </Field>

        <Turnstile siteKey={config?.turnstile_site_key ?? null} onToken={onToken} />
        {errors.form ? <ErrorText>{errors.form}</ErrorText> : null}

        <button type="submit" className="btn-primary w-full" disabled={busy} aria-busy={busy || undefined}>
          {busy ? <Loader2 className="spin" size={20} aria-hidden="true" /> : null}
          {busy ? t("sheet.checking") : submitLabel ?? t("home.start_scan")}
          {busy ? null : <ArrowRight size={19} aria-hidden="true" />}
        </button>
        <p className="text-2 text-[13px] leading-relaxed">
          {t("sheet.note")}{" "}
          <Link to="/privacy" className="font-semibold underline underline-offset-2" target="_blank">{t("sheet.privacy")}</Link> {t("sheet.and")}{" "}
          <Link to="/terms" className="font-semibold underline underline-offset-2" target="_blank">{t("sheet.terms")}</Link>{t("scan.verdict_end")}
        </p>
      </form>
    </Sheet>
  );
}
