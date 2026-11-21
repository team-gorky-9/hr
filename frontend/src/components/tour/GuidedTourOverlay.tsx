import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { TOUR_ROLES, TOUR_STEPS, type TourPlacement, type TourRole } from './tourSteps';

interface GuidedTourOverlayProps {
  role: TourRole | null;
  stepIndex: number;
  roleReady: boolean;
  onStepChange: (nextIndex: number) => void;
  onSwitchRole: () => void;
  onClose: () => void;
}

interface SpotlightRect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

interface CardCoords {
  left: number;
  top: number;
  centered: boolean;
}

const SPOTLIGHT_PAD = 8;
const CARD_GAP = 16;
const VIEWPORT_MARGIN = 16;
const TOP_SAFE_OFFSET = 52;
const STICKY_HEADER_CLEARANCE = 132;
const SOFT_TIMEOUT_MS = 1200;
const DEFAULT_CARD_WIDTH = 390;
const DEFAULT_CARD_HEIGHT = 290;

function clamp(value: number, min: number, max: number): number {
  if (max < min) return min;
  return Math.min(Math.max(value, min), max);
}

function isEditableElement(element: Element | null): boolean {
  if (!element || !(element instanceof HTMLElement)) return false;
  const tag = element.tagName;
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || element.isContentEditable;
}

function scrollTargetIntoView(element: HTMLElement): void {
  const rect = element.getBoundingClientRect();
  const vh = window.innerHeight;
  const usableHeight = Math.max(200, vh - STICKY_HEADER_CLEARANCE - 24);

  if (rect.height > usableHeight * 0.72) {
    if (rect.top < STICKY_HEADER_CLEARANCE - 8 || rect.top > STICKY_HEADER_CLEARANCE + 80) {
      const targetY = Math.max(0, window.scrollY + rect.top - STICKY_HEADER_CLEARANCE);
      window.scrollTo({ top: targetY, behavior: 'smooth' });
    }
    return;
  }

  if (rect.top < STICKY_HEADER_CLEARANCE || rect.bottom > vh - 32) {
    const desiredTop = STICKY_HEADER_CLEARANCE + (usableHeight - rect.height) / 2;
    const targetY = Math.max(0, window.scrollY + rect.top - desiredTop);
    window.scrollTo({ top: targetY, behavior: 'smooth' });
  }
}

function computeHoleRect(raw: DOMRect, vw: number, vh: number): SpotlightRect | null {
  const left = clamp(raw.left - SPOTLIGHT_PAD, 0, vw);
  const top = clamp(raw.top - SPOTLIGHT_PAD, 0, vh);
  const right = clamp(raw.right + SPOTLIGHT_PAD, 0, vw);
  const bottom = clamp(raw.bottom + SPOTLIGHT_PAD, 0, vh);
  const width = right - left;
  const height = bottom - top;
  if (width < 12 || height < 12) return null;
  return { left, top, right, bottom, width, height };
}

function computeCardCoords(
  hole: SpotlightRect | null,
  cardWidth: number,
  cardHeight: number,
  preferred: TourPlacement | undefined,
  vw: number,
  vh: number,
): CardCoords {
  if (!hole) {
    return {
      left: Math.max(VIEWPORT_MARGIN, Math.round((vw - cardWidth) / 2)),
      top: Math.max(TOP_SAFE_OFFSET, Math.round((vh - cardHeight) / 2)),
      centered: true,
    };
  }

  const order: TourPlacement[] = [];
  if (preferred) order.push(preferred);
  for (const side of ['bottom', 'top', 'right', 'left'] as const) {
    if (!order.includes(side)) order.push(side);
  }

  const minLeft = VIEWPORT_MARGIN;
  const maxLeft = Math.max(VIEWPORT_MARGIN, vw - cardWidth - VIEWPORT_MARGIN);
  const minTop = TOP_SAFE_OFFSET;
  const maxTop = Math.max(TOP_SAFE_OFFSET, vh - cardHeight - VIEWPORT_MARGIN);

  for (const side of order) {
    if (side === 'bottom' && vh - hole.bottom - VIEWPORT_MARGIN >= cardHeight + CARD_GAP) {
      return {
        left: Math.round(clamp(hole.left + hole.width / 2 - cardWidth / 2, minLeft, maxLeft)),
        top: Math.round(clamp(hole.bottom + CARD_GAP, minTop, maxTop)),
        centered: false,
      };
    }
    if (side === 'top' && hole.top - TOP_SAFE_OFFSET >= cardHeight + CARD_GAP) {
      return {
        left: Math.round(clamp(hole.left + hole.width / 2 - cardWidth / 2, minLeft, maxLeft)),
        top: Math.round(clamp(hole.top - CARD_GAP - cardHeight, minTop, maxTop)),
        centered: false,
      };
    }
    if (side === 'right' && vw - hole.right - VIEWPORT_MARGIN >= cardWidth + CARD_GAP) {
      return {
        left: Math.round(clamp(hole.right + CARD_GAP, minLeft, maxLeft)),
        top: Math.round(clamp(hole.top + hole.height / 2 - cardHeight / 2, minTop, maxTop)),
        centered: false,
      };
    }
    if (side === 'left' && hole.left - VIEWPORT_MARGIN >= cardWidth + CARD_GAP) {
      return {
        left: Math.round(clamp(hole.left - CARD_GAP - cardWidth, minLeft, maxLeft)),
        top: Math.round(clamp(hole.top + hole.height / 2 - cardHeight / 2, minTop, maxTop)),
        centered: false,
      };
    }
  }

  // Fallback for very large highlighted sections on 1280x720: dock cleanly in bottom-right corner.
  return {
    left: Math.round(clamp(vw - cardWidth - 20, minLeft, maxLeft)),
    top: Math.round(clamp(vh - cardHeight - 20, minTop, maxTop)),
    centered: false,
  };
}

export const GuidedTourOverlay: React.FC<GuidedTourOverlayProps> = ({
  role,
  stepIndex,
  roleReady,
  onStepChange,
  onSwitchRole,
  onClose,
}) => {
  const steps = role ? TOUR_STEPS[role] : [];
  const step = steps[stepIndex] ?? null;
  const roleMeta = role ? TOUR_ROLES.find((item) => item.id === role) ?? null : null;

  const overlayRootRef = useRef<HTMLDivElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const targetElementRef = useRef<HTMLElement | null>(null);
  const scrolledRef = useRef<boolean>(false);
  const allowFallbackRef = useRef<boolean>(false);

  const [holeRect, setHoleRect] = useState<SpotlightRect | null>(null);
  const [fallbackReady, setFallbackReady] = useState<boolean>(false);
  const [viewport, setViewport] = useState<{ vw: number; vh: number }>(() => ({
    vw: typeof window !== 'undefined' ? window.innerWidth : 1280,
    vh: typeof window !== 'undefined' ? window.innerHeight : 720,
  }));
  const [cardSize, setCardSize] = useState<{ width: number; height: number }>({
    width: DEFAULT_CARD_WIDTH,
    height: DEFAULT_CARD_HEIGHT,
  });

  const findVisibleTarget = useCallback(
    (allowFallback: boolean): HTMLElement | null => {
      if (!step) return null;
      const primary = document.querySelector<HTMLElement>(step.targetSelector);
      if (primary) {
        const rect = primary.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) return primary;
      }
      if (allowFallback && step.fallbackSelector) {
        const secondary = document.querySelector<HTMLElement>(step.fallbackSelector);
        if (secondary) {
          const rect = secondary.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) return secondary;
        }
      }
      return null;
    },
    [step],
  );

  const measure = useCallback(
    (shouldScrollIfFirst: boolean) => {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      setViewport((prev) => (prev.vw === vw && prev.vh === vh ? prev : { vw, vh }));

      if (!roleReady || !step) {
        targetElementRef.current = null;
        setHoleRect(null);
        return;
      }

      const found = findVisibleTarget(allowFallbackRef.current);
      targetElementRef.current = found;

      if (!found) {
        setHoleRect(null);
        return;
      }

      if (shouldScrollIfFirst && !scrolledRef.current) {
        scrolledRef.current = true;
        scrollTargetIntoView(found);
      }

      const computed = computeHoleRect(found.getBoundingClientRect(), vw, vh);
      setHoleRect((prev) => {
        if (!prev && !computed) return prev;
        if (
          prev &&
          computed &&
          Math.abs(prev.left - computed.left) < 1 &&
          Math.abs(prev.top - computed.top) < 1 &&
          Math.abs(prev.width - computed.width) < 1 &&
          Math.abs(prev.height - computed.height) < 1
        ) {
          return prev;
        }
        return computed;
      });
    },
    [findVisibleTarget, roleReady, step],
  );

  // Measure the rendered step card dimensions for accurate auto-placement.
  useLayoutEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const updateSize = () => {
      const width = el.offsetWidth || DEFAULT_CARD_WIDTH;
      const height = el.offsetHeight || DEFAULT_CARD_HEIGHT;
      setCardSize((prev) => (prev.width === width && prev.height === height ? prev : { width, height }));
    };
    updateSize();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(updateSize);
    ro.observe(el);
    return () => ro.disconnect();
  }, [role, stepIndex, fallbackReady, Boolean(holeRect)]);

  // Track target appearance via MutationObserver + requestAnimationFrame + 1200ms soft timeout.
  useEffect(() => {
    if (!role || !step) {
      setHoleRect(null);
      setFallbackReady(false);
      return;
    }

    scrolledRef.current = false;
    allowFallbackRef.current = false;
    targetElementRef.current = null;
    setHoleRect(null);
    setFallbackReady(false);

    let rafId: number | null = null;
    let targetResizeObserver: ResizeObserver | null = null;
    let observedTarget: HTMLElement | null = null;

    const scheduleMeasure = (shouldScroll: boolean) => {
      if (rafId !== null) window.cancelAnimationFrame(rafId);
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        measure(shouldScroll);
        const currentTarget = targetElementRef.current;
        if (typeof ResizeObserver !== 'undefined' && currentTarget !== observedTarget) {
          targetResizeObserver?.disconnect();
          observedTarget = currentTarget;
          if (currentTarget) {
            targetResizeObserver = new ResizeObserver(() => scheduleMeasure(false));
            targetResizeObserver.observe(currentTarget);
          }
        }
      });
    };

    scheduleMeasure(true);

    const softTimer = window.setTimeout(() => {
      allowFallbackRef.current = true;
      setFallbackReady(true);
      scheduleMeasure(true);
    }, SOFT_TIMEOUT_MS);

    const mutationObserver = new MutationObserver((mutations) => {
      const root = overlayRootRef.current;
      const hasExternalChange = mutations.some((mutation) => !root || !root.contains(mutation.target));
      if (hasExternalChange) {
        scheduleMeasure(!scrolledRef.current);
      }
    });
    mutationObserver.observe(document.body, { childList: true, subtree: true });

    const handleScrollOrResize = () => scheduleMeasure(false);
    window.addEventListener('scroll', handleScrollOrResize, true);
    window.addEventListener('resize', handleScrollOrResize);

    return () => {
      window.clearTimeout(softTimer);
      if (rafId !== null) window.cancelAnimationFrame(rafId);
      mutationObserver.disconnect();
      targetResizeObserver?.disconnect();
      window.removeEventListener('scroll', handleScrollOrResize, true);
      window.removeEventListener('resize', handleScrollOrResize);
    };
  }, [role, step, roleReady, measure]);

  // Keyboard navigation: Esc closes tour; ArrowLeft / ArrowRight step when not typing.
  useEffect(() => {
    if (!role || !step) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (isEditableElement(document.activeElement)) return;
      if (event.key === 'ArrowRight' && stepIndex < steps.length - 1) {
        event.preventDefault();
        onStepChange(stepIndex + 1);
      } else if (event.key === 'ArrowLeft' && stepIndex > 0) {
        event.preventDefault();
        onStepChange(stepIndex - 1);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [role, step, stepIndex, steps.length, onStepChange, onClose]);

  if (!role || !step || !roleMeta) return null;

  const isFirst = stepIndex === 0;
  const isLast = stepIndex === steps.length - 1;
  const progressPercent = Math.round(((stepIndex + 1) / steps.length) * 100);
  const showCard = Boolean(holeRect) || fallbackReady;

  const coords = computeCardCoords(
    holeRect,
    cardSize.width,
    cardSize.height,
    step.preferredPlacement,
    viewport.vw,
    viewport.vh,
  );

  return (
    <div ref={overlayRootRef} className="fixed inset-0 z-[70] pointer-events-none">
      {/* Spotlight Scrim: 4 non-blocking panels around the target hole so the highlighted element stays 100% interactive */}
      {holeRect ? (
        <>
          <div
            aria-hidden="true"
            className="fixed left-0 right-0 top-0 bg-[#141A24]/45 transition-all duration-200"
            style={{ height: holeRect.top }}
          />
          <div
            aria-hidden="true"
            className="fixed left-0 right-0 bottom-0 bg-[#141A24]/45 transition-all duration-200"
            style={{ top: holeRect.bottom }}
          />
          <div
            aria-hidden="true"
            className="fixed left-0 bg-[#141A24]/45 transition-all duration-200"
            style={{ top: holeRect.top, width: holeRect.left, height: holeRect.height }}
          />
          <div
            aria-hidden="true"
            className="fixed right-0 bg-[#141A24]/45 transition-all duration-200"
            style={{ top: holeRect.top, left: holeRect.right, height: holeRect.height }}
          />
          <div
            aria-hidden="true"
            className="fixed z-[75] rounded-2xl border-2 border-[#1F4FD1] shadow-[0_0_0_4px_rgba(31,79,209,0.22)] transition-all duration-200"
            style={{
              left: holeRect.left,
              top: holeRect.top,
              width: holeRect.width,
              height: holeRect.height,
            }}
          />
        </>
      ) : (
        showCard && (
          <div
            aria-hidden="true"
            className="fixed inset-0 bg-[#141A24]/40 transition-opacity duration-200"
          />
        )
      )}

      {/* Step Card */}
      {showCard && (
        <div
          ref={cardRef}
          role="dialog"
          aria-modal="false"
          aria-labelledby="guided-tour-step-title"
          className="fixed z-[80] pointer-events-auto w-[390px] max-w-[calc(100vw-32px)] bg-white rounded-2xl border border-[#E1E5EB] shadow-2xl overflow-hidden transition-all duration-200"
          style={{ left: coords.left, top: coords.top }}
        >
          {/* Progress bar */}
          <div className="h-1 w-full bg-[#EEF1F5]">
            <div
              className="h-full bg-[#1F4FD1] transition-all duration-300"
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          <div className="p-5 space-y-3.5">
            {/* Top row: Role badge + step counter + close */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold truncate ${roleMeta.accentBg} ${roleMeta.accentText}`}
                >
                  {roleMeta.shortLabel}
                </span>
                <span className="text-[12px] font-semibold text-[#616977] whitespace-nowrap">
                  Шаг {stepIndex + 1} из {steps.length}
                </span>
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Закрыть гид"
                className="shrink-0 w-7 h-7 rounded-lg text-[#616977] hover:text-[#141A24] hover:bg-[#F3F5F8] flex items-center justify-center transition-colors"
              >
                <svg aria-hidden="true" viewBox="0 0 16 16" fill="none" className="w-4 h-4">
                  <path
                    d="M4.2 4.2 11.8 11.8M11.8 4.2 4.2 11.8"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </svg>
              </button>
            </div>

            {/* Title & Description */}
            <div>
              <h3
                id="guided-tour-step-title"
                className="text-[16px] font-bold text-[#141A24] leading-snug"
              >
                {step.title}
              </h3>
              <p className="mt-1.5 text-[13px] text-[#4A5363] leading-relaxed">
                {step.description}
              </p>
            </div>

            {/* Try action callout */}
            <div className="rounded-xl bg-[#F3F5F8] border border-[#E1E5EB] px-3.5 py-2.5 text-[12.5px] leading-relaxed text-[#141A24]">
              <span className="font-semibold text-[#1F4FD1]">Что попробовать: </span>
              <span>{step.tryAction}</span>
            </div>

            {!holeRect && !roleReady && (
              <p className="text-[12px] text-[#616977]">
                Загружаем экран выбранной роли…
              </p>
            )}

            {/* Footer controls */}
            <div className="pt-2 border-t border-[#E1E5EB] flex items-center justify-between gap-2">
              {!isLast ? (
                <button
                  type="button"
                  onClick={onSwitchRole}
                  className="text-[12.5px] font-semibold text-[#4A5363] hover:text-[#1F4FD1] transition-colors whitespace-nowrap"
                >
                  Сменить роль
                </button>
              ) : (
                <button
                  type="button"
                  onClick={onSwitchRole}
                  className="px-3 py-1.5 rounded-lg text-[12.5px] font-semibold text-[#1F4FD1] bg-[#EEF3FE] hover:bg-[#DCE7FD] transition-colors whitespace-nowrap"
                >
                  Выбрать другую роль
                </button>
              )}

              <div className="flex items-center gap-2">
                {!isFirst && (
                  <button
                    type="button"
                    onClick={() => onStepChange(stepIndex - 1)}
                    className="px-3 py-1.5 rounded-lg text-[13px] font-semibold text-[#141A24] bg-white border border-[#C9D0DB] hover:bg-[#F3F5F8] transition-colors whitespace-nowrap"
                  >
                    Назад
                  </button>
                )}
                {!isLast ? (
                  <button
                    type="button"
                    onClick={() => onStepChange(stepIndex + 1)}
                    className="px-3.5 py-1.5 rounded-lg text-[13px] font-semibold text-white bg-[#1F4FD1] hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
                  >
                    Далее
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={onClose}
                    className="px-3.5 py-1.5 rounded-lg text-[13px] font-semibold text-white bg-[#1F4FD1] hover:bg-[#1841B2] transition-colors shadow-sm whitespace-nowrap"
                  >
                    Завершить
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default GuidedTourOverlay;
