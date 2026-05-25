"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { useEffect, useMemo, useState } from "react";
import { RefreshCw, X } from "lucide-react";

type GraphNode = {
  id: string;
  label: string;
  name: string;
  props: Record<string, unknown>;
};
type GraphEdge = { src: string; dst: string; rel: string };
type GraphDump = { nodes: GraphNode[]; edges: GraphEdge[] };

const ALL_TYPES = [
  "Person",
  "Company",
  "Project",
  "Belief",
  "Topic",
  "Decision",
  "Pattern",
  "Skill",
  "Conversation",
] as const;

const labelColors: Record<string, string> = {
  Person: "#7c5cff",
  Company: "#22c55e",
  Project: "#f59e0b",
  Decision: "#ef4444",
  Belief: "#06b6d4",
  Pattern: "#a855f7",
  Skill: "#84cc16",
  Topic: "#94a3b8",
  Conversation: "#475569",
};

const NODE_W = 180;
const NODE_H = 44;

function truncate(s: string, n: number): string {
  s = (s || "").trim();
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}

function nodeDisplay(d: GraphNode): string {
  // Beliefs use the full sentence as name; truncate hard so they don't tower
  // over the rest of the graph.
  const limit = d.label === "Belief" ? 36 : 28;
  return truncate(d.name || d.id, limit);
}

export function ContextGraph() {
  const { data, error, isLoading, mutate } = useSWR<GraphDump>(
    "/context/graph?limit=500",
    (k: string) => api(k),
  );
  const [rebuilding, setRebuilding] = useState(false);
  const [rebuildMsg, setRebuildMsg] = useState<string | null>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());

  const toggleType = (t: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(t)) next.delete(t);
      else next.add(t);
      return next;
    });
  };

  const presentTypes = useMemo(() => {
    if (!data) return [] as string[];
    const set = new Set<string>();
    for (const n of data.nodes) set.add(n.label || "Topic");
    return ALL_TYPES.filter((t) => set.has(t));
  }, [data]);

  const { nodes, edges, nodeIndex } = useMemo(
    () => layout(data, hidden),
    [data, hidden],
  );

  const rebuild = async () => {
    if (rebuilding) return;
    setRebuilding(true);
    setRebuildMsg(null);
    try {
      let totalNodes = 0;
      let totalEdges = 0;
      let totalDocs = 0;
      let scannedChunks = 0;
      for (let i = 0; i < 6; i++) {
        const r = (await api("/context/graph/rebuild", { method: "POST" })) as {
          docs_processed: number;
          docs_total: number;
          chunks_scanned: number;
          nodes_written: number;
          edges_written: number;
          remaining: number;
          skipped: string[];
        };
        totalNodes += r.nodes_written || 0;
        totalEdges += r.edges_written || 0;
        totalDocs += r.docs_processed || 0;
        scannedChunks = Math.max(scannedChunks, r.chunks_scanned || 0);
        await mutate();
        if (!r.remaining) break;
      }
      if (scannedChunks === 0) {
        setRebuildMsg(
          "No embedded chunks found yet. Upload a document under Context → Upload first.",
        );
      } else if (totalNodes === 0) {
        setRebuildMsg(
          `Scanned ${scannedChunks} chunks but the model couldn't pull any entities.`,
        );
      } else {
        setRebuildMsg(
          `Added ${totalNodes} nodes / ${totalEdges} edges from ${totalDocs} docs.`,
        );
      }
    } catch (err) {
      setRebuildMsg(`Rebuild failed: ${(err as Error).message}`);
    } finally {
      setRebuilding(false);
    }
  };

  if (error) return <Empty msg={`Graph unavailable: ${(error as Error).message}`} />;
  if (isLoading) return <Empty msg="Loading graph…" />;
  if (!data || data.nodes.length === 0)
    return (
      <Empty
        msg="Your identity graph is empty."
        action={
          <div className="flex flex-col items-center gap-2 mt-3">
            <button
              onClick={rebuild}
              disabled={rebuilding}
              className="text-xs px-3 py-1.5 rounded-full bg-[var(--accent)] text-white disabled:opacity-50 flex items-center gap-1.5"
            >
              <RefreshCw size={12} className={rebuilding ? "animate-spin" : ""} />
              {rebuilding ? "Extracting entities…" : "Build from ingested docs"}
            </button>
            {rebuildMsg && (
              <div className="text-[11px] text-[var(--fg-mute)] max-w-xs">
                {rebuildMsg}
              </div>
            )}
          </div>
        }
        hint="Or have a conversation — entities will populate as you talk."
      />
    );

  return (
    <div className="h-full w-full relative">
      {/* Top-right action stack */}
      <div className="absolute top-2 right-2 z-10 flex flex-col items-end gap-1">
        <button
          onClick={rebuild}
          disabled={rebuilding}
          className="text-[11px] px-2.5 py-1 rounded-full bg-[var(--bg-elev2)] border border-[var(--line)] text-[var(--fg-mute)] hover:text-white disabled:opacity-50 flex items-center gap-1.5"
          title="Re-run entity extraction over all ingested docs"
        >
          <RefreshCw size={11} className={rebuilding ? "animate-spin" : ""} />
          {rebuilding ? "Rebuilding…" : "Rebuild"}
        </button>
        {rebuildMsg && (
          <div className="text-[10px] text-[var(--fg-mute)] bg-[var(--bg-elev2)] border border-[var(--line)] rounded px-2 py-1 max-w-[220px] text-right">
            {rebuildMsg}
          </div>
        )}
      </div>

      {/* Type-filter legend (top-left, scrollable on small screens) */}
      <div className="absolute top-2 left-2 z-10 flex flex-wrap gap-1 max-w-[60%]">
        {presentTypes.map((t) => {
          const off = hidden.has(t);
          return (
            <button
              key={t}
              onClick={() => toggleType(t)}
              className="text-[10px] px-2 py-0.5 rounded-full border flex items-center gap-1 transition-opacity"
              style={{
                background: off ? "transparent" : `${labelColors[t]}33`,
                borderColor: labelColors[t] || "#3f3f46",
                color: off ? "var(--fg-mute)" : "white",
                opacity: off ? 0.5 : 1,
              }}
              title={off ? `Show ${t}` : `Hide ${t}`}
            >
              <span
                className="w-2 h-2 rounded-full"
                style={{ background: labelColors[t] || "#3f3f46" }}
              />
              {t}
            </button>
          );
        })}
      </div>

      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodeClick={(_, n) => {
          const orig = nodeIndex.get(n.id);
          if (orig) setSelected(orig);
        }}
        minZoom={0.1}
        maxZoom={2}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.18 }}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} color="#1f1f23" />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(0,0,0,.55)"
          nodeColor={(n) => (n.style?.background as string) || "#3f3f46"}
          style={{ background: "#0a0a0c" }}
        />
      </ReactFlow>

      {selected && (
        <NodeDetail node={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}

function layout(
  data: GraphDump | undefined,
  hidden: Set<string>,
): { nodes: Node[]; edges: Edge[]; nodeIndex: Map<string, GraphNode> } {
  const empty = { nodes: [] as Node[], edges: [] as Edge[], nodeIndex: new Map() };
  if (!data) return empty;

  // Filter out hidden types and orphan edges.
  const visibleNodes = data.nodes.filter((n) => !hidden.has(n.label || "Topic"));
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = data.edges.filter(
    (e) => visibleIds.has(e.src) && visibleIds.has(e.dst),
  );

  if (visibleNodes.length === 0) return empty;

  // Dagre layout — left-to-right reads better for a knowledge graph.
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({
    rankdir: "LR",
    nodesep: 28,
    ranksep: 80,
    edgesep: 16,
    marginx: 40,
    marginy: 40,
  });
  for (const n of visibleNodes) {
    g.setNode(n.id, { width: NODE_W, height: NODE_H });
  }
  for (const e of visibleEdges) {
    g.setEdge(e.src, e.dst);
  }
  dagre.layout(g);

  const idx = new Map<string, GraphNode>();
  const nodes: Node[] = visibleNodes.map((d) => {
    idx.set(d.id, d);
    const p = g.node(d.id);
    const display = nodeDisplay(d);
    return {
      id: d.id,
      data: { label: display },
      position: { x: (p?.x ?? 0) - NODE_W / 2, y: (p?.y ?? 0) - NODE_H / 2 },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      style: {
        background: labelColors[d.label] || "#3f3f46",
        color: "white",
        border: "1px solid rgba(255,255,255,.12)",
        borderRadius: 10,
        padding: "6px 10px",
        fontSize: 11,
        lineHeight: "1.2",
        width: NODE_W,
        height: NODE_H,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        fontWeight: 500,
        boxShadow: "0 1px 2px rgba(0,0,0,.4)",
        cursor: "pointer",
      },
    };
  });

  const edges: Edge[] = visibleEdges.map((e, i) => ({
    id: `e${i}`,
    source: e.src,
    target: e.dst,
    label: e.rel,
    type: "smoothstep",
    style: { stroke: "#3f3f46", strokeWidth: 1 },
    labelStyle: { fontSize: 9, fill: "#a1a1aa" },
    labelBgStyle: { fill: "#0a0a0c", fillOpacity: 0.9 },
    labelBgPadding: [4, 2],
  }));

  return { nodes, edges, nodeIndex: idx };
}

function NodeDetail({
  node,
  onClose,
}: {
  node: GraphNode;
  onClose: () => void;
}) {
  // Close on escape.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const props = Object.entries(node.props || {})
    .filter(([k]) => !["id", "user_id", "name"].includes(k))
    .filter(([, v]) => v !== null && v !== undefined && v !== "");

  return (
    <div className="absolute bottom-3 left-3 right-3 sm:right-auto sm:bottom-3 sm:max-w-md z-20 rounded-xl border border-[var(--line)] bg-[var(--bg-elev2)] shadow-2xl overflow-hidden">
      <div
        className="px-3 py-2 flex items-start gap-2 border-b border-[var(--line)]"
        style={{ background: `${labelColors[node.label] || "#3f3f46"}22` }}
      >
        <div
          className="text-[10px] px-1.5 py-0.5 rounded uppercase tracking-wider font-semibold mt-0.5"
          style={{
            background: labelColors[node.label] || "#3f3f46",
            color: "white",
          }}
        >
          {node.label}
        </div>
        <div className="flex-1 text-sm font-medium leading-snug">
          {node.name}
        </div>
        <button
          onClick={onClose}
          className="text-[var(--fg-mute)] hover:text-white shrink-0"
          aria-label="Close"
        >
          <X size={14} />
        </button>
      </div>
      {props.length > 0 && (
        <div className="px-3 py-2 text-xs space-y-1 max-h-48 overflow-auto">
          {props.map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <div className="text-[var(--fg-mute)] uppercase text-[10px] tracking-wider w-16 shrink-0 pt-0.5">
                {k}
              </div>
              <div className="text-[var(--fg)] flex-1 break-words">
                {String(v)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Empty({
  msg,
  hint,
  action,
}: {
  msg: string;
  hint?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="h-full flex flex-col items-center justify-center text-center text-sm text-[var(--fg-mute)] px-8">
      <div>{msg}</div>
      {hint && <div className="text-xs mt-1 opacity-80">{hint}</div>}
      {action}
    </div>
  );
}
