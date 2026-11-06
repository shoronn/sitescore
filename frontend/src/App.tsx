import { LazyMotion, MotionConfig } from "motion/react";
import { lazy, StrictMode, Suspense, useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import "./theme";
import Home from "./pages/Home";

// Animation features arrive just after the first paint; until then pages simply appear.
const loadFeatures = () => import("./motion-features").then((r) => r.default);

// Only the home page is in the first download, so it paints fast on a phone. Results and
// the information pages load when opened (the address box prefetches the results page).
const ScanPage = lazy(() => import("./pages/ScanPage"));
const AboutPage = lazy(() => import("./pages/InfoPages").then((m) => ({ default: m.AboutPage })));
const PrivacyPage = lazy(() => import("./pages/InfoPages").then((m) => ({ default: m.PrivacyPage })));
const TermsPage = lazy(() => import("./pages/InfoPages").then((m) => ({ default: m.TermsPage })));
const NotFound = lazy(() => import("./pages/NotFound"));

// The sales dashboard is loaded only when someone opens it, so visitors never download it.
const AdminLeads = lazy(() => import("./pages/admin/AdminLeads"));
const AdminLead = lazy(() => import("./pages/admin/AdminLead"));
const AdminLogin = lazy(() => import("./pages/admin/AdminLogin"));

/** New pages open at the top, like a normal website. */
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

function Loading() {
  return (
    <div className="flex flex-1 items-center justify-center py-24" role="status" aria-label="Loading">
      <span className="spin h-7 w-7 rounded-full border-[3px] border-[var(--track)] border-t-[var(--brand)]" />
    </div>
  );
}

export function App() {
  const location = useLocation();
  return (
    <>
      <ScrollToTop />
      <div className="light-field" aria-hidden="true" />
      {/* Each page fades and rises in (plain CSS, so it never waits for the animation code).
          Keyed by path, so filters and search on one page do not replay it. */}
      <div key={location.pathname} className="page-enter relative flex flex-1 flex-col">
        <Suspense fallback={<Loading />}>
          <Routes location={location}>
            <Route path="/" element={<Home />} />
            <Route path="/scan/:token" element={<ScanPage />} />
            <Route path="/about" element={<AboutPage />} />
            <Route path="/privacy" element={<PrivacyPage />} />
            <Route path="/terms" element={<TermsPage />} />
            <Route path="/admin" element={<AdminLeads />} />
            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin/leads/:id" element={<AdminLead />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </div>
    </>
  );
}

/** The whole app around a router: BrowserRouter in the browser, StaticRouter when the home page is pre-rendered. */
export function Root({ children }: { children: React.ReactNode }) {
  return (
    <StrictMode>
      {/* reducedMotion="user": people who turn on Reduce Motion get instant changes instead of animation. */}
      <MotionConfig reducedMotion="user">
        <LazyMotion features={loadFeatures} strict>
          {children}
        </LazyMotion>
      </MotionConfig>
    </StrictMode>
  );
}
