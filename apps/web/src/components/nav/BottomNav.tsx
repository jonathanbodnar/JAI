"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageSquareCode, ListTodo, StickyNote, Network, Settings } from "lucide-react";
import { cn } from "@/lib/cn";

const items = [
  { href: "/",        label: "Chat",    Icon: MessageSquareCode },
  { href: "/tasks",   label: "Tasks",   Icon: ListTodo },
  { href: "/notes",   label: "Notes",   Icon: StickyNote },
  { href: "/context", label: "Context", Icon: Network },
  { href: "/settings",label: "Settings", Icon: Settings },
] as const;

export function BottomNav() {
  const pathname = usePathname();

  return (
    <nav className="fixed bottom-5 left-1/2 -translate-x-1/2 bg-[#1e1f20]/90 backdrop-blur-xl border border-[#2d2f31] rounded-full px-4 py-1.5 shadow-[0_12px_36px_rgba(0,0,0,0.7)] z-40 max-w-md w-[calc(100%-2.5rem)] flex md:hidden items-center justify-around">
      <ul className="flex items-center justify-around w-full">
        {items.map(({ href, label, Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <li key={href} className="flex-1">
              <Link
                href={href}
                className={cn(
                  "flex flex-col items-center gap-0.5 py-1.5 text-[10px] font-medium transition-all duration-200",
                  active ? "text-[#fff]" : "text-[#8e918f] hover:text-[#e3e3e3]"
                )}
              >
                <div className={cn(
                  "p-1 rounded-full transition-all duration-200",
                  active ? "bg-[var(--accent)]/15 scale-105" : "bg-transparent"
                )}>
                  <Icon
                    size={20}
                    strokeWidth={active ? 2.3 : 1.8}
                    className={cn(active ? "text-[var(--accent)]" : "text-[#8e918f]")}
                  />
                </div>
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
