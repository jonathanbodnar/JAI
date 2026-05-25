"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessageCircle, ListTodo, StickyNote, Network } from "lucide-react";
import { cn } from "@/lib/cn";

const items = [
  { href: "/",        label: "Chat",    Icon: MessageCircle },
  { href: "/tasks",   label: "Tasks",   Icon: ListTodo },
  { href: "/notes",   label: "Notes",   Icon: StickyNote },
  { href: "/context", label: "Context", Icon: Network },
] as const;

export function BottomNav() {
  const pathname = usePathname();
  return (
    <nav
      className="safe-bottom border-t border-[var(--line)] bg-[var(--bg-elev)]"
      style={{ paddingBottom: "max(env(safe-area-inset-bottom), 0px)" }}
    >
      <ul className="grid grid-cols-4">
        {items.map(({ href, label, Icon }) => {
          const active = pathname === href || (href !== "/" && pathname.startsWith(href));
          return (
            <li key={href}>
              <Link
                href={href}
                className={cn(
                  "flex flex-col items-center gap-1 py-2.5 text-xs",
                  active ? "text-white" : "text-[var(--fg-mute)]"
                )}
              >
                <Icon
                  size={22}
                  strokeWidth={active ? 2.4 : 1.8}
                  className={cn(active && "text-[var(--accent)]")}
                />
                <span>{label}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
