import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "AI Content Factory", description: "Your local production studio" };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="en"><body>{children}</body></html>; }
