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
  Brain,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { supabase } from "@/lib/supabase";

const navItems = [
  { href: "/",        label: "Chat",    Icon: MessageSquareCode },
  { href: "/tasks",   label: "Tasks",   Icon: ListTodo },
  { href: "/notes",   label: "Notes",   Icon: StickyNote },
  { href: "/context", label: "Context", Icon: Network },
  { href: "/settings",label: "Settings", Icon: Settings },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const [email, setEmail] = useState("");

  useEffect(() => {
    supabase()
      .auth.getUser()
      .then(({ data }) => {
        setEmail(data.user?.email || "");
      });
  }, []);

  const handleLogout = async () => {
    await supabase().auth.signOut();
    window.location.reload();
  };

  return (
    <aside className="hidden md:flex flex-col w-64 bg-[#131314] border-r border-[#2d2f31] h-full shrink-0 select-none">
      {/* Brand Logo */}
      <div className="p-6 flex items-center gap-2.5">
        <div className="relative flex items-center justify-center w-8 h-8 rounded-xl bg-gradient-to-tr from-[#7c5cff] to-[#f43f5e] shadow-[0_0_20px_rgba(124,92,255,0.4)] animate-pulse">
          <Brain size={18} className="text-white" />
        </div>
        <span className="text-lg font-bold tracking-tight bg-gradient-to-r from-white via-zinc-200 to-zinc-400 bg-clip-text text-transparent">
          JAI
        </span>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-3 space-y-1.5">
        {navItems.map(({ href, label, Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3.5 px-4 py-3 rounded-2xl text-sm font-medium transition-all duration-200 group",
                active
                  ? "bg-[#1e1f20] text-white shadow-inner border border-[#2d2f31]"
                  : "text-[#c4c7c5] hover:bg-[#1e1f20]/60 hover:text-white"
              )}
            >
              <Icon
                size={20}
                strokeWidth={active ? 2.3 : 1.8}
                className={cn(
                  "transition-transform duration-200 group-hover:scale-105",
                  active ? "text-[var(--accent)]" : "text-[#8e918f] group-hover:text-white"
                )}
              />
              <span>{label}</span>
            </Link>
          );
        })}
      </nav>

      {/* User Session / Logout */}
      {email && (
        <div className="p-4 border-t border-[#2d2f31] space-y-3">
          <div className="flex items-center gap-3 px-2">
            <div className="w-8 h-8 rounded-full bg-[var(--accent)]/15 flex items-center justify-center font-bold text-sm text-[var(--accent)] shrink-0 border border-[var(--accent)]/30">
              {email[0].toUpperCase()}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-xs text-[#8e918f] truncate font-medium">Session</p>
              <p className="text-xs text-[#e3e3e3] truncate font-medium">{email}</p>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center gap-3 px-4 py-2.5 rounded-xl text-xs font-semibold text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/25 transition-all duration-200"
          >
            <LogOut size={14} />
            <span>Sign Out</span>
          </button>
        </div>
      )}
    </aside>
  );
}
