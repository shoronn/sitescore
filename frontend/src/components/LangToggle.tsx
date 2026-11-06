import { Languages } from "lucide-react";
import { setLang, useT } from "../i18n";

/** Switches the whole site between English and Bangla. Shows the other language's name. */
export default function LangToggle() {
  const { t, lang } = useT();
  const other = lang === "en" ? "bn" : "en";
  return (
    <button
      type="button"
      className="glass inline-flex min-h-[44px] shrink-0 items-center gap-1.5 rounded-capsule px-3.5 text-[14px] font-semibold"
      lang={other}
      title={t("lang.switch_label")}
      onClick={() => setLang(other)}
    >
      <Languages size={17} className="ink-brand" aria-hidden="true" />
      {t("lang.switch")}
    </button>
  );
}
