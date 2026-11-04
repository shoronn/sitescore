import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { AnimatePresence, m, useDragControls } from "motion/react";
import { useEffect, useRef } from "react";
import { EASE_OUT } from "../motion";
import { useMediaQuery } from "./Form";

interface Props {
  open: boolean;
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}

/**
 * iOS-style sheet. On phones it slides up from the bottom and can be dragged down to close;
 * on larger screens it floats in the middle. Radix Dialog handles focus, Escape, screen
 * readers and scroll locking; Motion handles the movement.
 */
export default function Sheet({ open, title, onClose, children }: Props) {
  const wide = useMediaQuery("(min-width: 640px)");
  const drag = useDragControls();
  // The sheet opens from a form, not a trigger button, so remember where focus was and return it.
  const returnTo = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (open) returnTo.current = document.activeElement as HTMLElement | null;
  }, [open]);

  const panel = wide
    ? { initial: { opacity: 0, scale: 0.96, y: 8 }, animate: { opacity: 1, scale: 1, y: 0 }, exit: { opacity: 0, scale: 0.97, y: 4 } }
    : { initial: { y: "100%" }, animate: { y: 0 }, exit: { y: "100%" } };

  return (
    <Dialog.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <AnimatePresence>
        {open ? (
          <Dialog.Portal forceMount>
            <Dialog.Overlay asChild forceMount>
              <m.div
                className="fixed inset-0 z-50"
                style={{ background: "var(--overlay)" }}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25 }}
              />
            </Dialog.Overlay>
            <div className="pointer-events-none fixed inset-0 z-50 flex items-end justify-center sm:items-center sm:p-6">
              <Dialog.Content
                asChild
                forceMount
                aria-describedby={undefined}
                onCloseAutoFocus={(e) => {
                  e.preventDefault();
                  if (returnTo.current?.isConnected) returnTo.current.focus({ preventScroll: true });
                }}
                onOpenAutoFocus={(e) => {
                  // Focus the first text field rather than the close button.
                  e.preventDefault();
                  const el = e.currentTarget as HTMLElement | null;
                  (el?.querySelector<HTMLElement>("input:not([type=checkbox])") ?? el?.querySelector<HTMLElement>("button"))?.focus();
                }}
              >
                <m.div
                  className="glass-float pointer-events-auto relative flex max-h-[92dvh] w-full flex-col overflow-hidden rounded-t-[32px] sm:max-w-md sm:rounded-[32px]"
                  style={{
                    background: "var(--sheet-bg)",
                    border: "1px solid var(--glass-edge)",
                    boxShadow: "inset 0 1px 0 var(--glass-shine), 0 -10px 50px -12px rgba(0,0,0,.35)",
                  }}
                  {...panel}
                  transition={wide ? { duration: 0.24, ease: EASE_OUT } : { type: "spring", stiffness: 380, damping: 40, mass: 0.9 }}
                  drag={wide ? false : "y"}
                  dragControls={drag}
                  dragListener={false}
                  dragConstraints={{ top: 0, bottom: 0 }}
                  dragElastic={{ top: 0, bottom: 0.7 }}
                  onDragEnd={(_, info) => {
                    if (info.offset.y > 110 || info.velocity.y > 600) onClose();
                  }}
                >
                  {/* Grab area: drag down from here to close on phones. */}
                  <div
                    className="shrink-0 touch-none px-5 pt-3 sm:px-6 sm:pt-6"
                    onPointerDown={(e) => !wide && drag.start(e)}
                  >
                    <div className="mx-auto mb-3 h-[5px] w-10 rounded-full sm:hidden" style={{ background: "var(--neutral)" }} aria-hidden="true" />
                    <div className="mb-5 flex items-start justify-between gap-4">
                      <Dialog.Title className="balance pt-0.5 font-display text-[22px] font-bold leading-tight tracking-tight">{title}</Dialog.Title>
                      <Dialog.Close
                        className="-mr-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                        style={{ background: "var(--field-fill)" }}
                        aria-label="Close"
                        onPointerDown={(e) => e.stopPropagation()}
                      >
                        <X size={18} strokeWidth={2.4} className="text-2" aria-hidden="true" />
                      </Dialog.Close>
                    </div>
                  </div>
                  <div className="overflow-y-auto overscroll-contain px-5 pb-[max(24px,env(safe-area-inset-bottom))] sm:px-6 sm:pb-6">{children}</div>
                </m.div>
              </Dialog.Content>
            </div>
          </Dialog.Portal>
        ) : null}
      </AnimatePresence>
    </Dialog.Root>
  );
}
