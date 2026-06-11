'use client';

import { useEffect, useRef } from 'react';

const TILE_SIZE = 300;
const DOODLE_SCALE = 0.75;
const REPEL_RADIUS = 140;
const REPEL_STRENGTH = 70;
const LERP_FACTOR = 0.1;
const SCROLL_PARALLAX = 0.4;

// Jittered-grid layout: 5 cols × 4 rows within each TILE_SIZE cell.
// Same positions every tile (seamless) but not axis-aligned.
const COLS = 5;
const ROWS = 4;
const CELL_W = TILE_SIZE / COLS; // 60px
const CELL_H = TILE_SIZE / ROWS; // 75px

/** Deterministic pseudo-random [0, 1) from seed — consistent across frames */
function stableRand(seed: number): number {
  const s = Math.sin(seed * 9301 + 49297) * 233280;
  return s - Math.floor(s);
}

const SVG_NS = 'http://www.w3.org/2000/svg';

type Tpl = {
  rotate: number;
  template: SVGGElement;
};

type Inst = {
  el: SVGGElement;
  baseX: number;
  baseY: number;
  rotate: number;
  offsetX: number;
  offsetY: number;
};

export default function DoodleBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    let cancelled = false;
    let rafId = 0;
    let resizeListener: (() => void) | null = null;

    let mouseX = -10000;
    let mouseY = -10000;
    let scrollY = 0;
    let instances: Inst[] = [];

    const onMouseMove = (e: MouseEvent) => {
      mouseX = e.clientX;
      mouseY = e.clientY;
    };
    const onMouseLeave = () => {
      mouseX = -10000;
      mouseY = -10000;
    };
    const onScroll = () => {
      scrollY = window.scrollY;
    };

    fetch('/doodle-bg.svg')
      .then((r) => r.text())
      .then((text) => {
        if (cancelled) return;

        const parser = new DOMParser();
        const doc = parser.parseFromString(text, 'image/svg+xml');
        const tpls: Tpl[] = Array.from(doc.querySelectorAll('svg > g > g')).map((g) => {
          const transform = g.getAttribute('transform') || '';
          const m = /rotate\(([\d.-]+)\)/.exec(transform);
          const tpl = g.cloneNode(true) as SVGGElement;
          tpl.removeAttribute('transform');
          return {
            rotate: parseFloat(m?.[1] || '0'),
            template: tpl,
          };
        });

        // Pre-compute jittered cell positions — same offsets every tile for seamless repetition.
        // Each shape gets its own cell in a COLS×ROWS grid with ±28% random nudge.
        const cellPositions = tpls.map((_, i) => {
          const col = i % COLS;
          const row = Math.floor(i / COLS);
          const jx = (stableRand(i * 2 + 3) - 0.5) * CELL_W * 0.56;
          const jy = (stableRand(i * 2 + 4) - 0.5) * CELL_H * 0.56;
          return {
            x: (col + 0.5) * CELL_W + jx,
            // Shift rows up by CELL_H/2 so row-0 icons start near y=0 instead of y≈37.
            // Tile boundaries remain spaced CELL_H apart (uniform distribution preserved).
            y: row * CELL_H + jy,
          };
        });

        const buildSVG = () => {
          const w = window.innerWidth;
          const h = window.innerHeight;
          const tilesX = Math.ceil(w / TILE_SIZE) + 1;
          const tilesY = Math.ceil(h / TILE_SIZE) + 1;

          const svg = document.createElementNS(SVG_NS, 'svg');
          svg.setAttribute('width', String(w));
          svg.setAttribute('height', String(h));
          svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
          svg.setAttribute('overflow', 'visible');
          svg.style.opacity = '0.15';
          svg.style.display = 'block';

          const rootG = document.createElementNS(SVG_NS, 'g');
          rootG.setAttribute('fill', 'none');
          rootG.setAttribute('stroke', '#475569');
          rootG.setAttribute('stroke-width', '1.6');
          rootG.setAttribute('stroke-linecap', 'round');
          rootG.setAttribute('stroke-linejoin', 'round');
          svg.appendChild(rootG);

          const newInstances: Inst[] = [];
          for (let ty = 0; ty < tilesY; ty++) {
            for (let tx = 0; tx < tilesX; tx++) {
              tpls.forEach((tpl, i) => {
                const g = tpl.template.cloneNode(true) as SVGGElement;
                rootG.appendChild(g);
                newInstances.push({
                  el: g,
                  baseX: tx * TILE_SIZE + cellPositions[i].x,
                  baseY: ty * TILE_SIZE + cellPositions[i].y,
                  rotate: tpl.rotate,
                  offsetX: 0,
                  offsetY: 0,
                });
              });
            }
          }

          container.replaceChildren(svg);
          instances = newInstances;
        };

        buildSVG();
        resizeListener = () => buildSVG();
        window.addEventListener('resize', resizeListener);

        const animate = () => {
          const scrollOffsetY = -scrollY * SCROLL_PARALLAX;
          for (const inst of instances) {
            const liveX = inst.baseX + inst.offsetX;
            const liveY = inst.baseY + scrollOffsetY + inst.offsetY;
            const dx = liveX - mouseX;
            const dy = liveY - mouseY;
            const dist = Math.hypot(dx, dy);

            let targetX = 0;
            let targetY = 0;
            if (dist < REPEL_RADIUS && dist > 0.01) {
              // Closer to mouse = stronger push, away from mouse direction
              const force = (1 - dist / REPEL_RADIUS) * REPEL_STRENGTH;
              targetX = (dx / dist) * force;
              targetY = (dy / dist) * force;
            }

            inst.offsetX += (targetX - inst.offsetX) * LERP_FACTOR;
            inst.offsetY += (targetY - inst.offsetY) * LERP_FACTOR;

            const finalX = inst.baseX + inst.offsetX;
            const finalY = inst.baseY + scrollOffsetY + inst.offsetY;
            inst.el.setAttribute(
              'transform',
              `translate(${finalX} ${finalY}) rotate(${inst.rotate}) scale(${DOODLE_SCALE})`
            );
          }
          rafId = requestAnimationFrame(animate);
        };
        rafId = requestAnimationFrame(animate);
      })
      .catch(() => {
        // Silently ignore — background is purely decorative
      });

    window.addEventListener('mousemove', onMouseMove, { passive: true });
    document.addEventListener('mouseleave', onMouseLeave);
    window.addEventListener('scroll', onScroll, { passive: true });

    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
      window.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseleave', onMouseLeave);
      window.removeEventListener('scroll', onScroll);
      if (resizeListener) window.removeEventListener('resize', resizeListener);
    };
  }, []);

  return (
    <div
      ref={containerRef}
      aria-hidden="true"
      className="fixed inset-0 pointer-events-none overflow-hidden"
      style={{ zIndex: 0 }}
    />
  );
}
