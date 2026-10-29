import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "SIAS Hub | Predictive Maintenance", description: "Industrial machine health and maintenance intelligence" };
export default function Layout({ children }: { children: React.ReactNode }) { return <html lang="en"><body>{children}</body></html>; }
