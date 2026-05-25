import type { Metadata, Viewport } from "next";
import "./globals.css";
import "@xyflow/react/dist/style.css";
import { BottomNav } from "@/components/nav/BottomNav";
import { AuthGate } from "@/lib/auth-gate";
import { OnboardingGate } from "@/components/onboarding/Onboarding";

export const metadata: Metadata = {
  title: "JAI",
  description: "Your second brain. One living conversation.",
  manifest: "/manifest.json",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "JAI",
  },
};

export const viewport: Viewport = {
  themeColor: "#0b0b0c",
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="flex flex-col h-dvh overflow-hidden">
        <AuthGate>
          <OnboardingGate>
            <main className="flex-1 overflow-hidden relative">{children}</main>
            <BottomNav />
          </OnboardingGate>
        </AuthGate>
      </body>
    </html>
  );
}
