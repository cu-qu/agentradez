import type { Metadata } from "next";
import Link from "next/link";
import { Instrument_Serif } from "next/font/google";

import { HomePreviewSwitcher } from "@/components/home-preview-switcher";

const instrument = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Home page 5 — Quiet",
  description: "Draft homepage: Your broker. Your limits. An agent in between.",
  robots: { index: false, follow: false },
};

export default function HomePage5() {
  return (
    <div className="min-h-full bg-[#0a0908] text-[#ece7dc]">
      <HomePreviewSwitcher />
      <header className="mx-auto flex max-w-lg items-center justify-between px-4 py-8">
        <Link
          href="/home-page-5"
          className="text-[11px] uppercase tracking-[0.28em] text-[#ece7dc]/55"
        >
          Agentradez
        </Link>
        <Link href="/login" className="text-[11px] uppercase tracking-[0.18em] text-[#ece7dc]/45 hover:text-[#ece7dc]">
          Sign in
        </Link>
      </header>

      <main className="mx-auto flex max-w-lg flex-col items-center px-4 pb-24 pt-12 text-center sm:pt-24">
        <h1
          className={`${instrument.className} text-[2.6rem] leading-[1.15] sm:text-5xl`}
        >
          Your broker. Your limits.{" "}
          <span className="italic text-[#c4a574]">An agent in between.</span>
        </h1>
        <p className="mt-8 text-sm leading-7 text-[#ece7dc]/55">
          Agentradez copy-trades options into a connected account. A strategy
          finds the idea. A tier decides size and exit. You can pause new
          entries without closing what is already open.
        </p>

        <dl className="mt-14 w-full border-y border-[#ece7dc]/12">
          {[
            ["Connect", "Robinhood Agentic"],
            ["Choose", "One strategy, one tier"],
            ["Pause", "The account switch"],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex items-baseline justify-between gap-4 border-b border-[#ece7dc]/12 py-4 last:border-b-0"
            >
              <dt className="text-[11px] uppercase tracking-[0.2em] text-[#ece7dc]/40">
                {label}
              </dt>
              <dd className={`${instrument.className} text-xl`}>{value}</dd>
            </div>
          ))}
        </dl>

        <Link
          href="/register"
          className="mt-12 inline-flex h-12 items-center rounded-full border border-[#c4a574] px-8 text-[11px] uppercase tracking-[0.22em] text-[#c4a574] hover:bg-[#c4a574] hover:text-[#0a0908]"
        >
          Create account
        </Link>
        <Link
          href="/how-it-works"
          className="mt-5 text-[11px] uppercase tracking-[0.18em] text-[#ece7dc]/35 hover:text-[#ece7dc]/70"
        >
          How it works
        </Link>
        <p className="mt-16 text-[11px] leading-5 text-[#ece7dc]/30">
          Not a broker. Not advice. Not a guarantee.
          <br />
          <Link href="/terms" className="underline decoration-[#ece7dc]/20 hover:text-[#ece7dc]/60">
            Terms
          </Link>
        </p>
      </main>
    </div>
  );
}
