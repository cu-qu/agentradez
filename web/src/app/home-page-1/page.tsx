import type { Metadata } from "next";
import Link from "next/link";
import { Newsreader } from "next/font/google";

import { HomePreviewSwitcher } from "@/components/home-preview-switcher";

const newsreader = Newsreader({
  subsets: ["latin"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Home page 1 — Editorial",
  description:
    "Draft homepage: You set the risk. The agent copies the rest.",
  robots: { index: false, follow: false },
};

export default function HomePage1() {
  return (
    <div className="min-h-full bg-[#f3eee6] text-[#1c1916]">
      <HomePreviewSwitcher />
      <header className="border-b border-[#1c1916]/10">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4">
          <Link href="/home-page-1" className="text-sm font-medium tracking-tight">
            Agentradez
          </Link>
          <nav className="flex items-center gap-6 text-sm">
            <Link href="/how-it-works" className="text-[#1c1916]/60 hover:text-[#1c1916]">
              How it works
            </Link>
            <Link href="/login" className="text-[#1c1916]/60 hover:text-[#1c1916]">
              Sign in
            </Link>
            <Link
              href="/register"
              className="border-b border-[#1c1916] pb-0.5 font-medium"
            >
              Get started
            </Link>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4">
        <section className="border-b border-[#1c1916]/10 py-20 sm:py-28">
          <p className="text-xs uppercase tracking-[0.22em] text-[#1c1916]/50">
            Issue 01 · Copy trade
          </p>
          <h1
            className={`${newsreader.className} mt-6 max-w-3xl text-5xl leading-[1.05] tracking-tight sm:text-7xl`}
          >
            You set the risk.{" "}
            <span className="italic text-[#1f6b52]">The agent copies the rest.</span>
          </h1>
          <p className="mt-8 max-w-xl text-lg leading-relaxed text-[#1c1916]/70">
            Agentradez is software that watches a strategy, then copies option
            trades into your brokerage account — sized, stopped, and exited by
            the tier you chose. Not the source’s dollar amount. Yours.
          </p>
          <div className="mt-10 flex flex-wrap items-center gap-6">
            <Link
              href="/register"
              className="bg-[#1c1916] px-5 py-3 text-sm font-medium text-[#f3eee6]"
            >
              Create an account
            </Link>
            <Link href="/how-it-works" className="text-sm text-[#1c1916]/70 hover:text-[#1c1916]">
              Read how it works →
            </Link>
          </div>
        </section>

        <section className="grid gap-0 py-4 sm:grid-cols-3">
          {[
            {
              n: "01",
              title: "Connect",
              body: "Link one broker. Robinhood is live. Only an Agentic account receives copy trades.",
            },
            {
              n: "02",
              title: "Choose",
              body: "Pick one strategy (where ideas come from) and one tier (how much risk, when to exit).",
            },
            {
              n: "03",
              title: "Leave it on",
              body: "The agent enters or records why it passed. Flip the account off to pause new trades.",
            },
          ].map((step, index) => (
            <article
              key={step.n}
              className={
                index === 0
                  ? "py-12 sm:pr-10"
                  : "border-[#1c1916]/10 py-12 sm:border-l sm:px-10"
              }
            >
              <p className={`${newsreader.className} text-3xl italic text-[#1f6b52]`}>
                {step.n}
              </p>
              <h2 className="mt-4 text-sm font-medium uppercase tracking-[0.16em]">
                {step.title}
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-[#1c1916]/65">
                {step.body}
              </p>
            </article>
          ))}
        </section>

        <blockquote
          className={`${newsreader.className} border-y border-[#1c1916]/10 py-16 text-center text-2xl leading-snug italic text-[#1c1916]/80 sm:text-3xl`}
        >
          “It is not a broker, not advice, and not a promise of profit.
          <br className="hidden sm:block" />
          It is a set of rules you can turn off.”
        </blockquote>

        <p className="py-12 text-center text-sm text-[#1c1916]/50">
          Options can expire worthless.{" "}
          <Link href="/terms" className="underline decoration-[#1c1916]/30 hover:text-[#1c1916]">
            Terms
          </Link>
        </p>
      </main>
    </div>
  );
}
