"use client";
import { useState } from "react";
import Link from "next/link";
import * as Tabs from "@radix-ui/react-tabs";
import { ChevronLeft } from "lucide-react";
import { Connections } from "./Connections";
import { Credentials } from "./Credentials";
import { DataSources } from "./DataSources";
import { Models } from "./Models";
import { Audit } from "./Audit";
import { Status } from "./Status";
import { Automations } from "./Automations";
import { cn } from "@/lib/cn";

export function SettingsView() {
  const [tab, setTab] = useState("status");
  return (
    <div className="flex flex-col h-full">
      <header className="header-safe-pt px-4 pb-3 border-b border-[var(--line)] flex items-center gap-3">
        <Link href="/" className="text-[var(--fg-mute)]" aria-label="Back">
          <ChevronLeft size={20} />
        </Link>
        <div>
          <h1 className="text-base font-semibold tracking-tight">Settings</h1>
          <p className="text-xs text-[var(--fg-mute)] mt-0.5">
            Status, connections, credentials, models.
          </p>
        </div>
      </header>
      <Tabs.Root value={tab} onValueChange={setTab} className="flex flex-col flex-1 overflow-hidden">
        <Tabs.List className="flex border-b border-[var(--line)] px-3 overflow-x-auto">
          <T value="status"       active={tab==="status"}>Status</T>
          <T value="automations"  active={tab==="automations"}>Automations</T>
          <T value="connections"  active={tab==="connections"}>Connections</T>
          <T value="data"         active={tab==="data"}>Data sources</T>
          <T value="credentials"  active={tab==="credentials"}>Credentials</T>
          <T value="models"       active={tab==="models"}>Models</T>
          <T value="audit"        active={tab==="audit"}>Audit</T>
        </Tabs.List>
        <Tabs.Content value="status"       className="flex-1 overflow-auto"><Status /></Tabs.Content>
        <Tabs.Content value="automations"  className="flex-1 overflow-auto"><Automations /></Tabs.Content>
        <Tabs.Content value="connections"  className="flex-1 overflow-auto"><Connections /></Tabs.Content>
        <Tabs.Content value="data"         className="flex-1 overflow-auto"><DataSources /></Tabs.Content>
        <Tabs.Content value="credentials"  className="flex-1 overflow-auto"><Credentials /></Tabs.Content>
        <Tabs.Content value="models"       className="flex-1 overflow-auto"><Models /></Tabs.Content>
        <Tabs.Content value="audit"        className="flex-1 overflow-auto"><Audit /></Tabs.Content>
      </Tabs.Root>
    </div>
  );
}

function T({ value, active, children }: { value: string; active: boolean; children: React.ReactNode }) {
  return (
    <Tabs.Trigger
      value={value}
      className={cn(
        "px-4 py-3 text-sm border-b-2 -mb-px",
        active ? "text-white border-[var(--accent)]" : "text-[var(--fg-mute)] border-transparent"
      )}
    >
      {children}
    </Tabs.Trigger>
  );
}
