import type { Metadata } from "next";
import Link from "next/link";

import { HomeNav } from "@/components/home-nav";

export const metadata: Metadata = {
  title: "Agentradez",
  description:
    "AI agent trading made easy. Connect your broker, set up your strategies, and Agentradez submits the orders for you.",
};

export default function HomePage() {
  return (
    <div className="min-h-full bg-[#0b0d12] text-[#e7e9ee]">
      <header className="border-b border-white/10">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <Link href="/" className="flex items-center gap-2">
            <span className="h-2 w-2 rounded-full bg-[#3d9a7a]" />
            <span className="text-sm font-semibold tracking-tight">Agentradez</span>
          </Link>
          <HomeNav />
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl items-center gap-12 px-4 py-16 lg:grid-cols-2 lg:py-24">
        <section>
          <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-[#3d9a7a]">
            Automatic Agent Trading
          </p>
          <h1 className="mt-4 text-4xl font-semibold tracking-tight sm:text-5xl">
            Connect your broker.
            <br />
            We submit the orders.
          </h1>
          <p className="mt-5 max-w-md text-base leading-relaxed text-[#8b919c]">
            Set up your strategies, then Agentradez places the trades for you.
            One place to connect and have trade with agents.
          </p>
          <ul className="mt-8 flex flex-col gap-3 text-sm text-[#c4c8d0]">
            <Li>Connect your broker</Li>
            <Li>
              Pick your{" "}
              <Link
                href="/strategies"
                className="text-[#3d9a7a] underline decoration-[#3d9a7a]/40 underline-offset-2 hover:text-[#4eb08c]"
              >
                strategy
              </Link>
            </Li>
            <Li>Agentradez submits the orders for you</Li>
          </ul>
          <div className="mt-10 flex flex-wrap gap-3">
            <Link
              href="/register"
              className="inline-flex h-11 items-center rounded-md bg-[#3d9a7a] px-5 text-sm font-medium text-white hover:bg-[#34856a]"
            >
              Create account
            </Link>
            <Link
              href="/how-it-works"
              className="inline-flex h-11 items-center rounded-md border border-white/15 px-5 text-sm text-[#c4c8d0] hover:border-white/25"
            >
              See the steps
            </Link>
          </div>
        </section>

        <section className="rounded-xl border border-white/10 bg-[#12151c] p-4 shadow-[0_24px_80px_rgba(0,0,0,0.45)]">
          <div className="flex items-center justify-between px-2 py-1">
            <p className="text-[11px] uppercase tracking-wide text-[#8b919c]">
              Dashboard
            </p>
          </div>
          <div className="mt-4 rounded-lg bg-[#0b0d12] p-5">
            <p className="text-[11px] uppercase tracking-[0.16em] text-[#8b919c]">
              Lifetime P&amp;L
            </p>
            <p className="tabular mt-2 text-3xl font-medium tracking-tight text-gain">
              +$1,240.50
            </p>
            <div className="mt-5 grid grid-cols-3 gap-2 text-xs">
              <Stat label="Today" value="+$86.25" tone="gain" />
              <Stat label="Open" value="2" />
              <Stat label="Closed" value="14" />
            </div>
          </div>
          <div className="mt-3 overflow-hidden rounded-lg border border-white/10">
            <div className="flex items-center justify-between px-4 py-2">
              <p className="text-[11px] uppercase tracking-wide text-[#8b919c]">
                Open positions
              </p>
            </div>
            <Position
              contract="NVDA 140 Call · Aug 28"
              pnl="+$62.40"
              tone="gain"
            />
            <Position
              contract="SPY 520 Put · Aug 22"
              pnl="−$18.10"
              tone="loss"
            />
          </div>
          <div className="mt-3 rounded-lg border border-white/10 px-4 py-3">
            <p className="text-[11px] uppercase tracking-wide text-[#8b919c]">
              Last activity
            </p>
            <p className="mt-2 text-sm text-[#c4c8d0]">
              Filled · NVDA 140 Call · 1 contract
            </p>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-8 text-xs text-[#8b919c] sm:flex-row sm:justify-between">
          <p>Agentradez is software, not a broker, adviser, and Not Financial Advice.</p>
          <Link href="/terms" className="hover:text-white">
            Terms
          </Link>
        </div>
      </footer>
    </div>
  );
}

function Li({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#3d9a7a]" />
      <span>{children}</span>
    </li>
  );
}

function Stat({
  label,
  value = "—",
  tone,
}: {
  label: string;
  value?: string;
  tone?: "gain" | "loss";
}) {
  const color =
    tone === "gain"
      ? "text-gain"
      : tone === "loss"
        ? "text-loss"
        : "text-[#e7e9ee]";
  return (
    <div className="rounded-md border border-white/10 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[#8b919c]">{label}</p>
      <p className={`tabular mt-1 text-sm ${color}`}>{value}</p>
    </div>
  );
}

function Position({
  contract,
  pnl,
  tone,
}: {
  contract: string;
  pnl: string;
  tone: "gain" | "loss";
}) {
  return (
    <div className="flex items-center justify-between gap-3 border-t border-white/10 px-4 py-2.5">
      <p className="text-sm text-[#c4c8d0]">{contract}</p>
      <p
        className={`tabular shrink-0 text-sm ${tone === "gain" ? "text-gain" : "text-loss"}`}
      >
        {pnl}
      </p>
    </div>
  );
}
