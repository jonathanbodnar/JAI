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
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";

type GraphDump = {
  nodes: { id: string; label: string; name: string; props: Record<string, unknown> }[];
  edges: { src: string; dst: string; rel: string }[];
};

const labelColors: Record<string, string> = {
  Person:       "#7c5cff",
  Company:      "#22c55e",
  Project:      "#f59e0b",
  Decision:     "#ef4444",
  Belief:       "#06b6d4",
  Pattern:      "#a855f7",
  Skill:        "#84cc16",
  Topic:        "#94a3b8",
  Conversation: "#475569",
};

export function ContextGraph() {
  const { data, error, isLoading } = useSWR<GraphDump>("/skills/_context/graph", (k: string) => api(k));

  const { nodes, edges } = useMemo(() => layout(data), [data]);

  if (error) return <Empty msg={`Graph unavailable: ${(error as Error).message}`} />;
  if (isLoading) return <Empty msg="Loading graph…" />;
  if (!data || data.nodes.length === 0)
    return <Empty msg="Your identity graph is empty. Have a conversation — entities, people, decisions and beliefs will appear here." />;

  return (
    <div className="h-full w-full">
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background gap={20} />
        <Controls position="bottom-right" />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}

function layout(data?: GraphDump): { nodes: Node[]; edges: Edge[] } {
  if (!data) return { nodes: [], edges: [] };
  const cx = 0, cy = 0, R = 220;
  const n = Math.max(1, data.nodes.length);
  const nodes: Node[] = data.nodes.map((d, i) => {
    const a = (i / n) * Math.PI * 2;
    return {
      id: d.id,
      data: { label: `${d.label}: ${d.name || d.id.slice(0,6)}` },
      position: { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) },
      style: {
        background: labelColors[d.label] || "#3f3f46",
        color: "white",
        border: "1px solid rgba(255,255,255,.15)",
        borderRadius: 12,
        padding: 8,
        fontSize: 12,
      },
    };
  });
  const edges: Edge[] = data.edges.map((e, i) => ({
    id: `e${i}`,
    source: e.src,
    target: e.dst,
    label: e.rel,
    style: { stroke: "#52525b" },
    labelStyle: { fontSize: 10, fill: "#a1a1aa" },
  }));
  return { nodes, edges };
}

function Empty({ msg }: { msg: string }) {
  return (
    <div className="h-full flex items-center justify-center text-center text-sm text-[var(--fg-mute)] px-8">
      {msg}
    </div>
  );
}
