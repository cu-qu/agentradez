import type { Metadata } from "next";
import Link from "next/link";
import { Syne } from "next/font/google";

import { HomePreviewSwitcher } from "@/components/home-preview-switcher";

const syne = Syne({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Home page 3 — Bold",
  description: "Draft homepage: Same trade. Your rules.",
  robots: { index: false, follow: false },
};

export default function HomePage3() {
  return (
    <div className="min-h-full overflow-x-hidden bg-black text-white">
      <HomePreviewSwitcher />
      <header>
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-4">
          <Link href="/home-page-3" className={`${syne.className} text-lg font-semibold`}>
            Agentradez
          </Link>
          <nav className="flex items-center gap-3 text-sm">
            <Link href="/login" className="px-3 py-2 text-white/60 hover:text-white">
              Sign in
            </Link>
            <Link
              href="/register"
              className="rounded-full bg-[#c8f542] px-4 py-2 font-medium text-black hover:bg-[#d4ff6a]"
            >
              Start
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 pb-20">
        <section className="py-10 sm:py-16">
          <h1
            className={`${syne.className} text-[14vw] font-semibold leading-[0.85] tracking-[-0.05em] sm:text-[9rem]`}
          >
            Same
            <br />
            trade.
          </h1>
          <div className="mt-6 flex flex-col gap-8 sm:flex-row sm:items-end sm:justify-between">
            <h2
              className={`${syne.className} text-[14vw] font-semibold leading-[0.85] tracking-[-0.05em] text-[#c8f542] sm:text-[9rem]`}
            >
              Your rules.
            </h2>
            <p className="max-w-xs pb-3 text-sm leading-relaxed text-white/60">
              Someone posts an options idea. Agentradez only takes it if your
              strategy and your risk tier both say yes — then sizes it for your
              account.
            </p>
          </div>
        </section>

        <section className="grid gap-3 md:grid-cols-4">
          <Tile className="md:col-span-2 bg-[#141414]" title="Connect">
            Robinhood Agentic today. One account on. Everything else stays out.
          </Tile>
          <Tile className="bg-[#c8f542] text-black" title="Strategy">
            Where the idea comes from. Copy Trade watches a source. You pick one.
          </Tile>
          <Tile className="bg-[#141414]" title="Tier">
            How large, when to stop, when to get out. This is your risk, not theirs.
          </Tile>
          <Tile className="md:col-span-2 bg-[#141414]" title="The log">
            If it skips a trade, you see why: not enough cash, too much slippage,
            daily loss pause. No mystery fills.
          </Tile>
          <Tile className="md:col-span-2 border border-white/15 bg-transparent" title="Kill switch">
            Turn the Agentic account off. New entries stop. Open trades keep
            following the tier.
          </Tile>
        </section>

        <div className="mt-10 flex flex-wrap items-center gap-6">
          <Link
            href="/register"
            className={`${syne.className} rounded-full bg-white px-8 py-4 text-lg text-black hover:bg-[#c8f542]`}
          >
            Create account
          </Link>
          <Link href="/how-it-works" className="text-sm text-white/50 hover:text-white">
            How it works
          </Link>
          <Link href="/terms" className="text-sm text-white/50 hover:text-white">
            Terms
          </Link>
        </div>
      </main>
    </div>
  );
}

function Tile({
  title,
  children,
  className,
}: {
  title: string;
  children: React.ReactNode;
  className: string;
}) {
  return (
    <article className={`rounded-3xl p-6 ${className}`}>
      <h3 className={`${syne.className} text-2xl tracking-tight`}>{title}</h3>
      <p className="mt-3 text-sm leading-relaxed opacity-70">{children}</p>
    </article>
  );
}
