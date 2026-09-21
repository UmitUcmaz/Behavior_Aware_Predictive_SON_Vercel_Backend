import { PlatformSessionHeartbeat } from "@/components/PlatformActivity";
import type { Metadata } from "next";
import "./globals.css";
import Navbar from "@/components/Navbar";

export const metadata: Metadata = {
  title: "Behavior-Aware Predictive SON",
  description:
    "AI-driven cellular traffic forecasting, validation and autonomous SON decision platform.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <PlatformSessionHeartbeat />
        <Navbar />
        <main>{children}</main>
      </body>
    </html>
  );
}
