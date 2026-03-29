'use client';

import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { forceCollide } from 'd3-force';
import {
  Network,
  RefreshCw,
  ExternalLink,
  X,
  Search,
  ArrowUpRight,
  ArrowDownLeft,
  Expand,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { getCitationGraph, expandCitationNode } from '@/lib/api';
import type { CitationGraphData, CitationGraphNode, CitationExpandData, Article } from '@/lib/types';

const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full">
      <div className="animate-spin h-8 w-8 border-2 border-emerald-500 rounded-full border-t-transparent" />
    </div>
  ),
});

// Root → turuncu/amber, diğerleri → yeşil heatmap
function nodeColor(node: CitationGraphNode, maxCount: number): string {
  if (node.is_root) return '#f59e0b'; // amber-400
  const count = node.cited_by_count ?? 0;
  if (maxCount === 0) return '#d1fae5';
  const t = Math.min(Math.log1p(count) / Math.log1p(maxCount), 1);
  const r = Math.round(209 - t * (209 - 6));
  const g = Math.round(250 - t * (250 - 95));
  const b = Math.round(229 - t * (229 - 70));
  return `rgb(${r},${g},${b})`;
}

// ─── ArticleSelector ─────────────────────────────────────────────────────────

function ArticleSelector({ onSelect }: { onSelect: (article: Article) => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Article[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) { setResults([]); setOpen(false); return; }
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ q, search_type: 'title', page_size: '8' });
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'}/articles/search?${params}`
        );
        if (res.ok) {
          const data = await res.json();
          setResults(data.items ?? []);
          setOpen(true);
        }
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 350);
  }, []);

  return (
    <div className="relative flex-1 min-w-0 max-w-lg">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={query}
          onChange={e => { setQuery(e.target.value); search(e.target.value); }}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Makale başlığıyla ara..."
          className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white"
        />
        {loading && (
          <div className="absolute right-3 top-1/2 -translate-y-1/2">
            <div className="animate-spin h-4 w-4 border-2 border-emerald-500 rounded-full border-t-transparent" />
          </div>
        )}
      </div>
      {open && results.length > 0 && (
        <div className="absolute z-50 w-full mt-1 bg-white border border-slate-200 rounded-lg shadow-lg max-h-64 overflow-y-auto">
          {results.map(article => (
            <button
              key={article.id}
              onClick={() => { setQuery(article.title); setOpen(false); onSelect(article); }}
              className="w-full text-left px-4 py-2.5 hover:bg-slate-50 border-b border-slate-100 last:border-0"
            >
              <p className="text-sm font-medium text-slate-800 line-clamp-1">{article.title}</p>
              <p className="text-xs text-slate-400 mt-0.5">
                {article.publication_year}
                {article.citation_count != null && ` · ${article.citation_count} atıf`}
              </p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── GraphControls ───────────────────────────────────────────────────────────

function GraphControls({
  depth, onDepthChange, onRefresh, disabled,
}: { depth: number; onDepthChange: (d: number) => void; onRefresh: () => void; disabled: boolean }) {
  return (
    <div className="flex items-center gap-4 flex-shrink-0">
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-slate-500 whitespace-nowrap">Derinlik:</label>
        <select
          value={depth}
          onChange={e => onDepthChange(Number(e.target.value))}
          disabled={disabled}
          className="text-sm border border-slate-200 rounded-lg px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-emerald-500 bg-white disabled:opacity-50"
        >
          {[1, 2, 3, 4, 5].map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      </div>
      <Button onClick={onRefresh} disabled={disabled} className="flex items-center gap-1.5 text-sm">
        <RefreshCw className="h-3.5 w-3.5" />
        Yenile
      </Button>
    </div>
  );
}

// ─── ColorLegend ─────────────────────────────────────────────────────────────

function ColorLegend() {
  return (
    <div className="flex items-center gap-3 text-xs text-slate-500 flex-shrink-0">
      <span className="flex items-center gap-1">
        <span className="inline-block w-3 h-3 rounded-full bg-amber-400 border border-amber-500" />
        Seçili makale
      </span>
      <span>Az atıf</span>
      <div className="flex h-3 w-20 rounded overflow-hidden">
        {Array.from({ length: 12 }).map((_, i) => {
          const t = i / 11;
          const r = Math.round(209 - t * 203);
          const g = Math.round(250 - t * 155);
          const b = Math.round(229 - t * 159);
          return <div key={i} style={{ flex: 1, backgroundColor: `rgb(${r},${g},${b})` }} />;
        })}
      </div>
      <span>Çok atıf</span>
    </div>
  );
}

// ─── NodeDetailPanel (bottom slide-up) ───────────────────────────────────────

function RelationList({
  title,
  icon,
  nodes,
  onHover,
  onClick,
}: {
  title: string;
  icon: React.ReactNode;
  nodes: CitationGraphNode[];
  onHover: (nodeId: string | null) => void;
  onClick: (nodeId: string) => void;
}) {
  // Atıf sayısına göre azalan sıra
  const sorted = [...nodes].sort((a, b) => (b.cited_by_count ?? 0) - (a.cited_by_count ?? 0));

  return (
    <div className="w-64">
      <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1">
        {icon}
        {title} ({nodes.length})
      </p>
      {sorted.length === 0 ? (
        <p className="text-xs text-slate-400 italic">Yok</p>
      ) : (
        <ul className="space-y-0.5 max-h-36 overflow-y-auto pr-1">
          {sorted.map(n => (
            <li
              key={n.id}
              onMouseEnter={() => onHover(n.id)}
              onMouseLeave={() => onHover(null)}
              onClick={() => onClick(n.id)}
              className="group flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer transition-colors hover:bg-emerald-50"
            >
              <span
                className="w-2 h-2 rounded-full flex-shrink-0 transition-transform group-hover:scale-150"
                style={{ backgroundColor: n.is_root ? '#f59e0b' : '#34d399' }}
              />
              <span className="flex-1 min-w-0">
                <span className="text-xs text-slate-700 line-clamp-1 group-hover:text-emerald-700 transition-colors">
                  {n.title ?? n.id}
                </span>
                <span className="text-[10px] text-slate-400 ml-1">
                  {n.cited_by_count ?? 0}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function NodeDetailPanel({
  node,
  graphData,
  onClose,
  onNavigate,
  onHoverRelation,
  onClickRelation,
  onExpand,
  expanding,
}: {
  node: CitationGraphNode;
  graphData: CitationGraphData;
  onClose: () => void;
  onNavigate: (articleId: string) => void;
  onHoverRelation: (nodeId: string | null) => void;
  onClickRelation: (nodeId: string) => void;
  onExpand: (openalexId: string) => void;
  expanding: boolean;
}) {
  // Bu düğümü cite edenler (grafın içinde)
  const incomingNodes = graphData.edges
    .filter(e => e.target === node.id)
    .map(e => graphData.nodes.find(n => n.id === e.source))
    .filter(Boolean) as CitationGraphNode[];

  // Bu düğümün cite ettiği düğümler (grafın içinde)
  const outgoingNodes = graphData.edges
    .filter(e => e.source === node.id)
    .map(e => graphData.nodes.find(n => n.id === e.target))
    .filter(Boolean) as CitationGraphNode[];

  const doiClean = node.doi?.replace(/^https?:\/\/doi\.org\//, '');

  return (
    <div className="border-t border-slate-200 bg-white rounded-b-xl">
      <div className="flex items-start gap-4 p-4">
        {/* Sol: Temel bilgiler */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2 mb-3">
            <div className="flex items-center gap-2">
              {node.is_root && (
                <span className="text-[10px] font-bold uppercase tracking-wider bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full">
                  Kök
                </span>
              )}
              {!node.is_internal && (
                <span className="text-[10px] font-bold uppercase tracking-wider bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full">
                  Harici
                </span>
              )}
            </div>
            <button onClick={onClose} className="text-slate-400 hover:text-slate-600 flex-shrink-0">
              <X className="h-4 w-4" />
            </button>
          </div>

          <h3 className="text-sm font-semibold text-slate-800 leading-snug mb-3 line-clamp-2">
            {node.title ?? 'Başlık yok'}
          </h3>

          <div className="grid grid-cols-2 gap-x-6 gap-y-1.5 text-xs mb-3">
            {node.publication_year && (
              <>
                <span className="text-slate-400">Yayın yılı</span>
                <span className="font-medium">{node.publication_year}</span>
              </>
            )}
            <span className="text-slate-400">Toplam atıf</span>
            <span className="font-medium text-emerald-700">{node.cited_by_count ?? 0}</span>
            <span className="text-slate-400">Graf derinliği</span>
            <span className="font-medium">{node.depth}</span>
            {node.id && (
              <>
                <span className="text-slate-400">OpenAlex ID</span>
                <span className="font-mono text-slate-600 truncate">{node.id}</span>
              </>
            )}
            {doiClean && (
              <>
                <span className="text-slate-400">DOI</span>
                <a
                  href={`https://doi.org/${doiClean}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-emerald-600 hover:text-emerald-700 truncate"
                >
                  <ExternalLink className="h-3 w-3 flex-shrink-0" />
                  <span className="truncate">{doiClean}</span>
                </a>
              </>
            )}
          </div>

          <div className="flex items-center gap-2">
            {node.is_internal && node.internal_article_id && (
              <button
                onClick={() => onNavigate(node.internal_article_id!)}
                className="text-xs bg-emerald-50 hover:bg-emerald-100 text-emerald-700 font-medium py-1.5 px-3 rounded-lg transition-colors"
              >
                Bu makalenin grafiğini gör →
              </button>
            )}
            {!node.is_root && (
              <button
                onClick={() => onExpand(node.id)}
                disabled={expanding}
                className="flex items-center gap-1.5 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 font-medium py-1.5 px-3 rounded-lg transition-colors disabled:opacity-50"
              >
                {expanding ? (
                  <div className="animate-spin h-3 w-3 border-2 border-blue-500 rounded-full border-t-transparent" />
                ) : (
                  <Expand className="h-3 w-3" />
                )}
                Genişlet
              </button>
            )}
          </div>
        </div>

        {/* Sağ: Graf içi bağlantılar */}
        <div className="flex gap-4 flex-shrink-0" onMouseLeave={() => onHoverRelation(null)}>
          <RelationList
            title="Grafta atıf yapanlar"
            icon={<ArrowDownLeft className="h-3 w-3" />}
            nodes={incomingNodes}
            onHover={onHoverRelation}
            onClick={onClickRelation}
          />
          <RelationList
            title="Grafta atıf aldıkları"
            icon={<ArrowUpRight className="h-3 w-3" />}
            nodes={outgoingNodes}
            onHover={onHoverRelation}
            onClick={onClickRelation}
          />
        </div>
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export default function CitationMapPage() {
  const [selectedArticle, setSelectedArticle] = useState<Article | null>(null);
  const [graphData, setGraphData] = useState<CitationGraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState(2);
  const [selectedNode, setSelectedNode] = useState<CitationGraphNode | null>(null);
  const selectedNodeIdRef = useRef<string | null>(null);
  const hoveredRelNodeIdRef = useRef<string | null>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [containerWidth, setContainerWidth] = useState(0);

  // Container genişliğini takip et
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width);
      }
    });
    ro.observe(el);
    setContainerWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const maxCitationCount = graphData
    ? Math.max(...graphData.nodes.map(n => n.cited_by_count ?? 0), 1)
    : 1;

  const fgData = useMemo(() => graphData
    ? {
        nodes: graphData.nodes.map(n => ({
          ...n,
          val: Math.max(3, Math.log1p(n.cited_by_count ?? 0) * 2.5),
          color: nodeColor(n, maxCitationCount),
        })),
        links: graphData.edges.map(e => ({ source: e.source, target: e.target })),
      }
    : { nodes: [], links: [] }, [graphData, maxCitationCount]);

  // Graf yüklenince force parametrelerini ayarla (mesafe + itme + collision)
  // requestAnimationFrame ile ref hazır olana kadar dene
  useEffect(() => {
    if (!graphData) return;
    let cancelled = false;
    const applyForces = () => {
      if (cancelled) return;
      const fg = fgRef.current;
      if (!fg) {
        requestAnimationFrame(applyForces);
        return;
      }
      const n = graphData.node_count;
      const linkDist = n > 200 ? 80 : n > 50 ? 120 : 160;
      fg.d3Force('link')?.distance(linkDist);
      const chargeStrength = n > 200 ? -400 : n > 50 ? -500 : -600;
      fg.d3Force('charge')?.strength(chargeStrength);
      fg.d3Force('center')?.strength(0.03);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      fg.d3Force('collide', forceCollide()
        .radius((node: any) => (node.val ?? 3) + 6)
        .strength(1)
        .iterations(4)
      );
      fg.d3ReheatSimulation();
    };
    requestAnimationFrame(applyForces);
    return () => { cancelled = true; };
  }, [graphData]);

  const loadGraph = useCallback(async (article: Article, d: number, refresh = false) => {
    setLoading(true);
    setError(null);
    setSelectedNode(null);
    selectedNodeIdRef.current = null;
    try {
      const data = await getCitationGraph(article.id, d, refresh);
      setGraphData(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Bilinmeyen hata');
      setGraphData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleArticleSelect = useCallback((article: Article) => {
    setSelectedArticle(article);
    loadGraph(article, depth);
  }, [depth, loadGraph]);

  const handleDepthChange = useCallback((d: number) => {
    setDepth(d);
    if (selectedArticle) loadGraph(selectedArticle, d);
  }, [selectedArticle, loadGraph]);

  const handleNavigate = useCallback((articleId: string) => {
    getCitationGraph(articleId, depth)
      .then(data => { setGraphData(data); setSelectedNode(null); selectedNodeIdRef.current = null; })
      .catch(() => setError('Makale grafiği yüklenemedi.'));
  }, [depth]);

  const handleHoverRelation = useCallback((nodeId: string | null) => {
    hoveredRelNodeIdRef.current = nodeId;
  }, []);

  const handleClickRelation = useCallback((nodeId: string) => {
    // Grafta bu node'u bul
    const fg = fgRef.current;
    if (!fg) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const gNode = fgData.nodes.find((n: any) => n.id === nodeId);
    if (!gNode) return;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const n = gNode as any;
    // Node'a zoom + odaklan
    fg.centerAt(n.x, n.y, 600);
    fg.zoom(4, 600);
    // Seçili node olarak ayarla
    hoveredRelNodeIdRef.current = null;
    selectedNodeIdRef.current = nodeId;
    setSelectedNode(gNode as unknown as CitationGraphNode);
  }, [fgData.nodes]);

  const [expanding, setExpanding] = useState(false);

  const handleExpandNode = useCallback(async (openalexId: string) => {
    if (!graphData) return;
    setExpanding(true);
    try {
      const result: CitationExpandData = await expandCitationNode(openalexId, depth);
      // Mevcut node ID'leri
      const existingNodeIds = new Set(graphData.nodes.map(n => n.id));
      const existingEdgeKeys = new Set(
        graphData.edges.map(e => `${e.source}→${e.target}`)
      );
      // Yeni node'ları filtrele (zaten varsa ekleme)
      const newNodes = result.nodes.filter(n => !existingNodeIds.has(n.id));
      // Yeni edge'leri filtrele
      const newEdges = result.edges.filter(
        e => !existingEdgeKeys.has(`${e.source}→${e.target}`)
      );
      // Merge
      setGraphData({
        ...graphData,
        nodes: [...graphData.nodes, ...newNodes],
        edges: [...graphData.edges, ...newEdges],
        node_count: graphData.node_count + newNodes.length,
        edge_count: graphData.edge_count + newEdges.length,
      });
    } catch {
      setError('Düğüm genişletilemedi.');
    } finally {
      setExpanding(false);
    }
  }, [graphData, depth]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-slate-900">Atıf Haritası</h1>
        <p className="mt-1 text-slate-500">
          Makale atıf ağını keşfedin — turuncu düğüm seçili makale, yeşil ton atıf yoğunluğu
        </p>
      </div>

      <div className="flex flex-wrap items-end gap-4">
        <ArticleSelector onSelect={handleArticleSelect} />
        <GraphControls
          depth={depth}
          onDepthChange={handleDepthChange}
          onRefresh={() => selectedArticle && loadGraph(selectedArticle, depth, true)}
          disabled={!selectedArticle || loading}
        />
        <ColorLegend />
      </div>

      {graphData && !loading && (
        <div className="flex gap-4 text-sm text-slate-500">
          <span><span className="font-medium text-slate-700">{graphData.node_count}</span> düğüm</span>
          <span><span className="font-medium text-slate-700">{graphData.edge_count}</span> bağlantı</span>
          <span>· Derinlik {graphData.max_depth}</span>
        </div>
      )}

      {/* Graf Kartı: canvas + alt panel */}
      <Card className="overflow-hidden">
        {/* Canvas alanı */}
        <div ref={containerRef} className="h-[580px] bg-slate-50 overflow-hidden">
          {loading ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-400">
              <div className="animate-spin h-10 w-10 border-2 border-emerald-500 rounded-full border-t-transparent" />
              <p className="text-sm">Atıf grafiği hesaplanıyor…</p>
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full gap-3 p-8 text-center">
              <Network className="h-12 w-12 text-slate-300" />
              <p className="text-sm text-red-500">{error}</p>
              <p className="text-xs text-slate-400">
                Bu makale için OpenAlex verisi yok. Önce{' '}
                <a href="/scrapers" className="text-emerald-600 underline">OpenAlex taramasını</a>{' '}
                çalıştırın.
              </p>
            </div>
          ) : graphData ? (
            <ForceGraph2D
              ref={fgRef}
              graphData={fgData}
              nodeVal="val"
              nodeColor="color"
              nodeLabel={(node: Record<string, unknown>) =>
                `${node.title ?? node.id} (${node.cited_by_count ?? 0} atıf)`
              }
              onNodeClick={(node: Record<string, unknown>) => {
                selectedNodeIdRef.current = node.id as string;
                setSelectedNode(node as unknown as CitationGraphNode);
              }}
              linkDirectionalArrowLength={5}
              linkDirectionalArrowRelPos={1}
              linkColor={(link: Record<string, unknown>) => {
                const hId = hoveredRelNodeIdRef.current;
                const sId = selectedNodeIdRef.current;
                if (hId && sId) {
                  const srcId = typeof link.source === 'object' ? (link.source as Record<string, unknown>).id : link.source;
                  const tgtId = typeof link.target === 'object' ? (link.target as Record<string, unknown>).id : link.target;
                  if ((srcId === hId && tgtId === sId) || (srcId === sId && tgtId === hId)) {
                    return '#f59e0b';
                  }
                }
                return '#cbd5e1';
              }}
              linkWidth={(link: Record<string, unknown>) => {
                const hId = hoveredRelNodeIdRef.current;
                const sId = selectedNodeIdRef.current;
                if (hId && sId) {
                  const srcId = typeof link.source === 'object' ? (link.source as Record<string, unknown>).id : link.source;
                  const tgtId = typeof link.target === 'object' ? (link.target as Record<string, unknown>).id : link.target;
                  if ((srcId === hId && tgtId === sId) || (srcId === sId && tgtId === hId)) {
                    return 2.5;
                  }
                }
                return 0.8;
              }}
              autoPauseRedraw={false}
              backgroundColor="#f8fafc"
              width={containerWidth || undefined}
              height={580}
              nodeCanvasObject={(
                node: Record<string, unknown>,
                ctx: CanvasRenderingContext2D,
                globalScale: number,
              ) => {
                const x = node.x as number;
                const y = node.y as number;
                const val = node.val as number;
                const color = node.color as string;
                const isRoot = node.is_root as boolean;
                const nodeId = node.id as string;
                const isSelected = selectedNodeIdRef.current === nodeId;
                const isHoveredRel = hoveredRelNodeIdRef.current === nodeId;

                ctx.beginPath();
                ctx.arc(x, y, val, 0, 2 * Math.PI);
                ctx.fillStyle = isHoveredRel ? '#fbbf24' : color;
                ctx.fill();

                // Seçili, hover veya root: belirgin halka
                if (isHoveredRel || isSelected || isRoot) {
                  ctx.strokeStyle = isHoveredRel ? '#d97706' : isRoot ? '#d97706' : '#3b82f6';
                  ctx.lineWidth = (isHoveredRel ? 3 : isSelected ? 3 : 2) / globalScale;
                  ctx.stroke();
                }

                // Etiket: root'ta her zaman, diğerlerinde zoom > 2'de
                if (isRoot || globalScale > 2) {
                  const label = ((node.title as string) ?? (node.id as string)).slice(0, 35);
                  const fontSize = Math.min(5, 14 / globalScale);
                  ctx.font = `${isRoot ? 'bold ' : ''}${fontSize}px Sans-Serif`;
                  ctx.textAlign = 'center';
                  ctx.textBaseline = 'top';
                  ctx.fillStyle = '#1e293b';
                  ctx.fillText(label, x, y + val + 1.5 / globalScale);
                }
              }}
            />
          ) : (
            <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-300">
              <Network className="h-20 w-20" />
              <p className="text-slate-400 text-sm">Yukarıdan bir makale seçin</p>
            </div>
          )}
        </div>

        {/* Alt detay paneli — node seçilince kayar */}
        {selectedNode && graphData && (
          <NodeDetailPanel
            node={selectedNode}
            graphData={graphData}
            onClose={() => { setSelectedNode(null); selectedNodeIdRef.current = null; hoveredRelNodeIdRef.current = null; }}
            onNavigate={handleNavigate}
            onHoverRelation={handleHoverRelation}
            onClickRelation={handleClickRelation}
            onExpand={handleExpandNode}
            expanding={expanding}
          />
        )}
      </Card>
    </div>
  );
}
