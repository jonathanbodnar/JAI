"use client";
import { useState } from "react";
import * as Tabs from "@radix-ui/react-tabs";
import { ContextGraph } from "./ContextGraph";
import { ContextDocs } from "./ContextDocs";
import { ContextSkills } from "./ContextSkills";
import { ContextUpload } from "./ContextUpload";
import { cn } from "@/lib/cn";

export function ContextView() {
  const [tab, setTab] = useState("graph");
  return (
    <div className="flex flex-col h-full">
      <header className="header-safe-pt px-4 pb-3 border-b border-[var(--line)]">
        <h1 className="text-base font-semibold tracking-tight">Context</h1>
        <p className="text-xs text-[var(--fg-mute)] mt-0.5">
          Everything JAI knows about you. Edit anything.
        </p>
      </header>
      <Tabs.Root value={tab} onValueChange={setTab} className="flex flex-col flex-1 overflow-hidden">
        <Tabs.List className="flex border-b border-[var(--line)] px-3 overflow-x-auto">
          <TabTrigger value="graph"  active={tab==="graph"}>Graph</TabTrigger>
          <TabTrigger value="docs"   active={tab==="docs"}>Docs</TabTrigger>
          <TabTrigger value="upload" active={tab==="upload"}>Upload</TabTrigger>
          <TabTrigger value="skills" active={tab==="skills"}>Skills</TabTrigger>
        </Tabs.List>
        <Tabs.Content value="graph"  className="flex-1 overflow-hidden"><ContextGraph /></Tabs.Content>
        <Tabs.Content value="docs"   className="flex-1 overflow-auto"><ContextDocs /></Tabs.Content>
        <Tabs.Content value="upload" className="flex-1 overflow-auto"><ContextUpload /></Tabs.Content>
        <Tabs.Content value="skills" className="flex-1 overflow-auto"><ContextSkills /></Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function TabTrigger({
  value, active, children,
}: { value: string; active: boolean; children: React.ReactNode }) {
  return (
    <Tabs.Trigger
      value={value}
      className={cn(
        "px-4 py-3 text-sm border-b-2 -mb-px",
        active
          ? "text-white border-[var(--accent)]"
          : "text-[var(--fg-mute)] border-transparent"
      )}
    >
      {children}
    </Tabs.Trigger>
  );
}
