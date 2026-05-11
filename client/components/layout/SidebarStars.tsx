'use client';

import { useEffect, useRef } from 'react';

const DOT_COUNT    = 65;
const FOOTER_H     = 58;    // px from bottom: footer area (no dots)
const NAV_BOTTOM_PX = 390;  // px from top: bottom of Scraper Kontrol
// Fixed logical width = fully-expanded sidebar width.
// Dots always live in [0, LOGICAL_W]. The aside's overflow-hidden clips
// whatever falls outside the current (possibly collapsed) width.
// This means no reset on sidebar open/close — dots just get revealed.
const LOGICAL_W = 260;

interface Dot {
  x: number;
  y: number;
  r: number;
  baseOpacity: number;
  vy: number;
  phase: number;
  phaseSpeed: number;
  ampX: number;
}

function getOpacity(y: number, h: number): number {
  const denseBottom = h - FOOTER_H;
  const fadeTop     = NAV_BOTTOM_PX;
  if (y >= denseBottom || y <= fadeTop) return 0;
  return (y - fadeTop) / (denseBottom - fadeTop);
}

function spawnDot(h: number): Dot {
  const denseBottom = h - FOOTER_H;
  const range       = denseBottom - NAV_BOTTOM_PX;
  // pow² biases dots toward the bottom (footer line)
  const y = denseBottom - Math.pow(Math.random(), 2) * range;
  return {
    x:          Math.random() * LOGICAL_W,
    y,
    r:          0.9 + Math.random() * 1.4,
    baseOpacity: 0.28 + Math.random() * 0.58,
    vy:         -(0.1 + Math.random() * 0.2),
    phase:      Math.random() * Math.PI * 2,
    phaseSpeed: 0.004 + Math.random() * 0.005,
    ampX:       0.15 + Math.random() * 0.3,
  };
}

export default function SidebarStars() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let rafId    = 0;
    let dots: Dot[] = [];
    let prevH    = 0;

    const init = (h: number) => {
      // Set logical width once; height follows viewport.
      canvas.width  = LOGICAL_W;
      canvas.height = h;
      prevH = h;
      dots  = Array.from({ length: DOT_COUNT }, () => spawnDot(h));
    };

    const onResize = () => {
      const newH = canvas.offsetHeight;
      // Ignore width changes (sidebar open/close) — only react to height changes.
      if (Math.abs(newH - prevH) > 2) {
        canvas.height = newH; // clears bitmap for 1 frame, dots js-state preserved
        prevH = newH;
        dots  = Array.from({ length: DOT_COUNT }, () => spawnDot(newH));
      }
    };

    init(canvas.offsetHeight);

    const ro = new ResizeObserver(onResize);
    ro.observe(canvas);

    const animate = () => {
      const h = canvas.height;
      ctx.clearRect(0, 0, LOGICAL_W, h);
      const denseBottom = h - FOOTER_H;

      for (const dot of dots) {
        dot.y     += dot.vy;
        dot.phase += dot.phaseSpeed;
        dot.x     += Math.sin(dot.phase) * dot.ampX;

        // Wrap x within logical width
        if (dot.x < 0)        dot.x += LOGICAL_W;
        if (dot.x > LOGICAL_W) dot.x -= LOGICAL_W;

        // Reset dots that drift above the fade zone
        if (dot.y < NAV_BOTTOM_PX) {
          const range = denseBottom - NAV_BOTTOM_PX;
          dot.y = denseBottom - Math.pow(Math.random(), 2) * range;
          dot.x = Math.random() * LOGICAL_W;
        }

        const alpha = dot.baseOpacity * getOpacity(dot.y, h);
        if (alpha < 0.01) continue;

        ctx.beginPath();
        ctx.arc(dot.x, dot.y, dot.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${alpha.toFixed(3)})`;
        ctx.fill();
      }

      rafId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(rafId);
      ro.disconnect();
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="absolute top-0 left-0 h-full pointer-events-none"
      style={{ zIndex: 0, width: `${LOGICAL_W}px` }}
    />
  );
}
