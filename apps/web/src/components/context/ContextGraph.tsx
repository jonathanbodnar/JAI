"use client";
import useSWR from "swr";
import { api } from "@/lib/api";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  type Node,
  type Edge,
  type NodeProps,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationNodeDatum,
} from "d3-force";
import { useEffect, useMemo, useRef, useState } from "react";
import { RefreshCw, X, Trash2, Pencil, Check } from "lucide-react";

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

const BASE_RADIUS = 14;          // smallest node = single belief / leaf
const MAX_RADIUS = 32;           // most-connected node
const LINK_DIST = 90;
const CHARGE = -260;

function truncate(s: string, n: number): string {
  s = (s || "").trim();
  return s.length > n ? s.slice(0, n - 1).trimEnd() + "…" : s;
}

function nodeDisplay(d: GraphNode): string {
  const limit = d.label === "Belief" ? 28 : 20;
  return truncate(d.name || d.id, limit);
}

/**
 * Custom node: a colored neuron with the label printed *underneath* the
 * circle so the graph reads like a mind-map / synapse diagram.
 */
type NeuronData = {
  label: string;
  color: string;
  radius: number;
};

function NeuronNode({ data, selected }: NodeProps<Node<NeuronData>>) {
  const { label, color, radius } = data;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 4,
        pointerEvents: "auto",
      }}
    >
      <div
        style={{
          width: radius * 2,
          height: radius * 2,
          borderRadius: "9999px",
          background: `radial-gradient(circle at 30% 30%, ${color}EE 0%, ${color}88 60%, ${color}22 100%)`,
          border: `1px solid ${selected ? "#fff" : color}`,
          boxShadow: selected
            ? `0 0 24px ${color}, 0 0 8px #fff`
            : `0 0 14px ${color}66, inset 0 0 8px ${color}33`,
          transition: "box-shadow 120ms ease",
        }}
      />
      <div
        style={{
          fontSize: 9,
          color: "#e4e4e7",
          maxWidth: 110,
          lineHeight: 1.1,
          textAlign: "center",
          textShadow: "0 0 4px #000, 0 0 4px #000",
          padding: "0 2px",
          pointerEvents: "none",
        }}
      >
        {label}
      </div>
      {/* Hidden handles so ReactFlow knows where to anchor edges. */}
      <Handle type="source" position={Position.Right} style={{ opacity: 0, top: radius, left: radius * 2 }} />
      <Handle type="target" position={Position.Left}  style={{ opacity: 0, top: radius, left: 0 }} />
    </div>
  );
}

const nodeTypes = { neuron: NeuronNode };

/**
 * Force-directed (neural-network style) layout via d3-force.
 *
 * - Nodes are circular and sized by degree (how connected they are).
 * - Edges are straight lines so the graph reads like a synapse map rather
 *   than the previous tidy left-to-right Dagre layout.
 * - Layout runs once per data/filter change with 240 ticks (synchronous —
 *   instant for graphs up to a few hundred nodes).
 */
function layout(
  data: GraphDump | undefined,
  hidden: Set<string>,
): { nodes: Node[]; edges: Edge[]; nodeIndex: Map<string, GraphNode> } {
  const empty = { nodes: [] as Node[], edges: [] as Edge[], nodeIndex: new Map() };
  if (!data) return empty;

  const visibleNodes = data.nodes.filter((n) => !hidden.has(n.label || "Topic"));
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = data.edges.filter(
    (e) => visibleIds.has(e.src) && visibleIds.has(e.dst),
  );
  if (visibleNodes.length === 0) return empty;

  // Compute node degree → radius scale.
  const degree = new Map<string, number>();
  for (const e of visibleEdges) {
    degree.set(e.src, (degree.get(e.src) ?? 0) + 1);
    degree.set(e.dst, (degree.get(e.dst) ?? 0) + 1);
  }
  const maxDeg = Math.max(1, ...Array.from(degree.values()));

  type Sim = SimulationNodeDatum & { id: string };
  const simNodes: Sim[] = visibleNodes.map((n) => ({ id: n.id }));
  const idToIdx = new Map(simNodes.map((n, i) => [n.id, i]));
  const simLinks = visibleEdges.map((e) => ({
    source: idToIdx.get(e.src)!,
    target: idToIdx.get(e.dst)!,
  }));

  // Spread nodes initially on a circle so the simulation has somewhere to go.
  const r0 = Math.max(120, Math.sqrt(simNodes.length) * 40);
  simNodes.forEach((n, i) => {
    const angle = (i / simNodes.length) * 2 * Math.PI;
    n.x = Math.cos(angle) * r0;
    n.y = Math.sin(angle) * r0;
  });

  const sim = forceSimulation(simNodes)
    .force("charge", forceManyBody().strength(CHARGE))
    .force("center", forceCenter(0, 0))
    .force(
      "link",
      forceLink(simLinks).distance(LINK_DIST).strength(0.7),
    )
    .force(
      "collide",
      forceCollide()
        .radius((d) => {
          const id = (d as Sim).id;
          const deg = degree.get(id) ?? 0;
          return BASE_RADIUS + (MAX_RADIUS - BASE_RADIUS) * (deg / maxDeg) + 6;
        })
        .iterations(2),
    )
    .stop();

  for (let i = 0; i < 240; i++) sim.tick();

  const idx = new Map<string, GraphNode>();
  const nodes: Node[] = visibleNodes.map((d, i) => {
    idx.set(d.id, d);
    const sn = simNodes[i];
    const deg = degree.get(d.id) ?? 0;
    const radius =
      BASE_RADIUS + (MAX_RADIUS - BASE_RADIUS) * (deg / maxDeg);
    const display = nodeDisplay(d);
    const color = labelColors[d.label] || "#3f3f46";
    return {
      id: d.id,
      type: "neuron",
      data: { label: display, color, radius } as NeuronData,
      position: { x: (sn.x ?? 0) - radius, y: (sn.y ?? 0) - radius },
    } as Node;
  });

  const edges: Edge[] = visibleEdges.map((e, i) => ({
    id: `e${i}`,
    source: e.src,
    target: e.dst,
    label: e.rel,
    type: "straight",
    animated: false,
    style: { stroke: "#52525b", strokeWidth: 0.8, opacity: 0.55 },
    labelStyle: { fontSize: 8, fill: "#71717a" },
    labelBgStyle: { fill: "transparent" },
    labelShowBg: false,
  }));

  return { nodes, edges, nodeIndex: idx };
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
        nodeTypes={nodeTypes}
        onNodeClick={(_, n) => {
          const orig = nodeIndex.get(n.id);
          if (orig) setSelected(orig);
        }}
        minZoom={0.1}
        maxZoom={3}
        nodesDraggable
        nodesConnectable={false}
        elementsSelectable
        fitView
        fitViewOptions={{ padding: 0.25 }}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: "straight" }}
        style={{ background: "#06060a" }}
      >
        <Background gap={28} color="#0f0f14" />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(0,0,0,.7)"
          nodeColor={(n) => {
            const orig = nodeIndex.get(n.id);
            return orig ? (labelColors[orig.label] || "#3f3f46") : "#3f3f46";
          }}
          style={{ background: "#06060a" }}
        />
      </ReactFlow>

      {selected && (
        <NodeDetail
          node={selected}
          onClose={() => setSelected(null)}
          onMutate={async () => {
            await mutate();
            setSelected(null);
          }}
        />
      )}
    </div>
  );
}

function NodeDetail({
  node,
  onClose,
  onMutate,
}: {
  node: GraphNode;
  onClose: () => void;
  onMutate: () => void | Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(node.name);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const props = Object.entries(node.props || {})
    .filter(([k]) => !["id", "user_id", "name"].includes(k))
    .filter(([, v]) => v !== null && v !== undefined && v !== "");

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === node.name) {
      setEditing(false);
      setName(node.name);
      return;
    }
    setBusy(true);
    try {
      await api(`/context/graph/node/${node.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: trimmed }),
      });
      await onMutate();
    } catch (e) {
      alert(`Rename failed: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      setEditing(false);
    }
  };

  const del = async () => {
    if (!confirm(`Delete "${node.name}" from your identity graph? This removes the node and all its connections.`)) {
      return;
    }
    setBusy(true);
    try {
      await api(`/context/graph/node/${node.id}`, { method: "DELETE" });
      await onMutate();
    } catch (e) {
      alert(`Delete failed: ${(e as Error).message}`);
      setBusy(false);
    }
  };

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
        <div className="flex-1 min-w-0">
          {editing ? (
            <input
              ref={inputRef}
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void save();
                if (e.key === "Escape") { setEditing(false); setName(node.name); }
              }}
              disabled={busy}
              className="w-full bg-transparent border-b border-[var(--accent)] text-sm font-medium leading-snug outline-none disabled:opacity-50"
            />
          ) : (
            <div className="text-sm font-medium leading-snug break-words">{node.name}</div>
          )}
        </div>
        <div className="flex items-center gap-0.5 shrink-0">
          {editing ? (
            <button
              onClick={() => void save()}
              disabled={busy}
              className="p-1 text-emerald-400 hover:text-white disabled:opacity-40"
              title="Save"
              aria-label="Save"
            >
              <Check size={14} />
            </button>
          ) : (
            <button
              onClick={() => setEditing(true)}
              disabled={busy}
              className="p-1 text-[var(--fg-mute)] hover:text-white disabled:opacity-40"
              title="Rename"
              aria-label="Rename"
            >
              <Pencil size={13} />
            </button>
          )}
          <button
            onClick={() => void del()}
            disabled={busy}
            className="p-1 text-[var(--fg-mute)] hover:text-red-400 disabled:opacity-40"
            title="Delete node + its edges"
            aria-label="Delete"
          >
            <Trash2 size={13} />
          </button>
          <button
            onClick={onClose}
            className="p-1 text-[var(--fg-mute)] hover:text-white shrink-0"
            aria-label="Close"
          >
            <X size={14} />
          </button>
        </div>
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
