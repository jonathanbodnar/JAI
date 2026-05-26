"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  MessageSquareCode,
  ListTodo,
  StickyNote,
  Network,
  Settings,
  LogOut,
  Menu,
  Plus,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { supabase } from "@/lib/supabase";

const navItems = [
  { href: "/",        label: "Chat",    Icon: MessageSquareCode },
  { href: "/tasks",   label: "Tasks",   Icon: ListTodo },
  { href: "/notes",   label: "Notes",   Icon: StickyNote },
  { href: "/context", label: "Context", Icon: Network },
] as const;

const SIDEBAR_KEY = "jai.sidebar.expanded";

export function Sidebar() {
  const pathname = usePathname();
  const [email, setEmail] = useState("");
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    try {
      const v = localStorage.getItem(SIDEBAR_KEY);
      if (v === "1") setExpanded(true);
    } catch { /* ignore */ }
    supabase()
      .auth.getUser()
      .then(({ data }) => {
        setEmail(data.user?.email || "");
      });
  }, []);

  const toggle = () => {
    setExpanded((v) => {
      const next = !v;
      try { localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0"); } catch { /* ignore */ }
      return next;
    });
  };

  const handleLogout = async () => {
    await supabase().auth.signOut();
    window.location.reload();
  };

  const resetChat = async () => {
    // Clear the chat thread storage and dispatch a window event for ChatView
    try { localStorage.removeItem("jai.chat.messages.v1"); } catch { /* ignore */ }
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("jai:new-chat"));
      if (pathname !== "/") {
        window.location.href = "/";
      } else {
        window.location.reload();
      }
    }
  };

  return (
    <aside
      className={cn(
        "hidden md:flex flex-col bg-[#1e1f20] h-full shrink-0 select-none transition-[width] duration-300 ease-out overflow-hidden",
        expanded ? "w-64" : "w-[72px]"
      )}
    >
      {/* Top: hamburger toggle */}
      <div className="pt-3 px-3">
        <button
          onClick={toggle}
          className="h-11 w-11 rounded-full flex items-center justify-center text-[#c4c7c5] hover:bg-[#2d2f31] transition-colors"
          aria-label={expanded ? "Collapse sidebar" : "Expand sidebar"}
          title={expanded ? "Collapse menu" : "Expand menu"}
        >
          <Menu size={20} />
        </button>
      </div>

      {/* New chat pill */}
      <div className="px-3 mt-4">
        <button
          onClick={resetChat}
          className={cn(
            "flex items-center gap-3 rounded-full bg-[#2d2f31] hover:bg-[#3c3d3f] text-[#e3e3e3] transition-colors h-11",
            expanded ? "px-4 w-full justify-start" : "w-11 justify-center"
          )}
          title="New chat"
        >
          <Plus size={18} className="shrink-0" />
          {expanded && <span className="text-sm font-medium whitespace-nowrap">New chat</span>}
        </button>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 mt-6 space-y-1 overflow-y-auto overflow-x-hidden">
        {navItems.map(({ href, label, Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-4 rounded-full h-11 transition-colors group whitespace-nowrap",
                expanded ? "px-4" : "w-11 justify-center px-0",
                active
                  ? "bg-[#3c4043] text-white"
                  : "text-[#c4c7c5] hover:bg-[#2d2f31] hover:text-white"
              )}
              title={!expanded ? label : undefined}
            >
              <Icon size={20} strokeWidth={1.7} className="shrink-0" />
              {expanded && <span className="text-sm font-medium">{label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Bottom: settings + user */}
      <div className="px-3 pb-4 pt-2 space-y-1 border-t border-[#2d2f31]/40">
        <Link
          href="/settings"
          className={cn(
            "flex items-center gap-4 rounded-full h-11 transition-colors whitespace-nowrap",
            expanded ? "px-4" : "w-11 justify-center px-0",
            pathname.startsWith("/settings")
              ? "bg-[#3c4043] text-white"
              : "text-[#c4c7c5] hover:bg-[#2d2f31] hover:text-white"
          )}
          title={!expanded ? "Settings" : undefined}
        >
          <Settings size={20} strokeWidth={1.7} className="shrink-0" />
          {expanded && <span className="text-sm font-medium">Settings</span>}
        </Link>

        {email && (
          <button
            onClick={handleLogout}
            className={cn(
              "flex items-center gap-4 rounded-full h-11 transition-colors w-full whitespace-nowrap text-[#c4c7c5] hover:bg-[#2d2f31] hover:text-white",
              expanded ? "px-3" : "justify-center px-0"
            )}
            title={!expanded ? `Sign out (${email})` : undefined}
          >
            <div className="h-8 w-8 rounded-full bg-[var(--accent)]/15 flex items-center justify-center font-semibold text-[13px] text-[var(--accent)] border border-[var(--accent)]/30 shrink-0">
              {email[0]?.toUpperCase() || "U"}
            </div>
            {expanded && (
              <div className="min-w-0 flex-1 text-left">
                <p className="text-[12px] text-[#e3e3e3] truncate font-medium leading-tight">{email}</p>
                <p className="text-[11px] text-[#8e918f] truncate flex items-center gap-1 leading-tight mt-0.5">
                  <LogOut size={10} /> Sign out
                </p>
              </div>
            )}
          </button>
        )}
      </div>
    </aside>
  );
}
