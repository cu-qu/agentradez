import type { Metadata } from "next";
import Link from "next/link";

import { HomePreviewSwitcher } from "@/components/home-preview-switcher";

export const metadata: Metadata = {
  title: "Home page 4 — Plain talk",
  description: "Draft homepage: Know what it will do before it does it.",
  robots: { index: false, follow: false },
};

const questions = [
  {
    q: "What is Agentradez?",
    a: "Software that copy-trades options into a brokerage account you connect. You pick the source of ideas and the risk rules. The agent either takes the trade or writes down why it did not.",
  },
  {
    q: "What do I have to decide?",
    a: "Three things. Which broker to connect. Which strategy to copy. Which investment tier sets size, daily loss pause, stop, and exit. That is the whole setup.",
  },
  {
    q: "Does it copy their dollar amount?",
    a: "No. Size is a percent of your Agentic-account equity, in whole contracts. If that percent is below one contract, it still buys one when the premium fits. If one contract is too expensive, it passes.",
  },
  {
    q: "How do I stop it?",
    a: "Turn the Agentic account off. New entries pause. Open positions still follow the tier — take-profit, hard stop, force exit. You can also change strategy or tier later.",
  },
  {
    q: "Is this advice? Will I make money?",
    a: "No and not necessarily. Agentradez is not a broker or an adviser. Options can expire worthless. Automation can place trades you later wish it hadn’t. You stay responsible for the account.",
  },
];

export default function HomePage4() {
  return (
    <div className="min-h-full bg-[#e8edf2] text-[#15202b]">
      <HomePreviewSwitcher />
      <header className="bg-white/70 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-4">
          <Link href="/home-page-4" className="text-sm font-semibold tracking-tight">
            Agentradez
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-[#15202b]/55 hover:text-[#15202b]">
              Sign in
            </Link>
            <Link
              href="/register"
              className="rounded-lg bg-[#1d4e89] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#163a66]"
            >
              Create account
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-16 sm:py-20">
        <p className="text-sm font-medium text-[#1d4e89]">A straight explanation</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight sm:text-[2.75rem] sm:leading-tight">
          Know what it will do before it does it.
        </h1>
        <p className="mt-5 text-lg leading-relaxed text-[#15202b]/70">
          If you cannot explain the product in a few answers, it is too clever.
          Agentradez is a copy-trade agent with a pause switch.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/register"
            className="inline-flex h-11 items-center rounded-lg bg-[#1d4e89] px-5 text-sm font-medium text-white hover:bg-[#163a66]"
          >
            Create account
          </Link>
          <Link
            href="/how-it-works"
            className="inline-flex h-11 items-center rounded-lg bg-white px-5 text-sm font-medium text-[#15202b] ring-1 ring-[#15202b]/10 hover:ring-[#15202b]/25"
          >
            Full walkthrough
          </Link>
        </div>

        <ol className="mt-14 overflow-hidden rounded-2xl bg-white ring-1 ring-[#15202b]/10">
          {questions.map((item, index) => (
            <li
              key={item.q}
              className={
                index === 0
                  ? "px-6 py-6"
                  : "border-t border-[#15202b]/10 px-6 py-6"
              }
            >
              <h2 className="text-base font-semibold tracking-tight">{item.q}</h2>
              <p className="mt-2 text-sm leading-relaxed text-[#15202b]/70">{item.a}</p>
            </li>
          ))}
        </ol>

        <p className="mt-10 text-center text-sm text-[#15202b]/45">
          <Link href="/terms" className="hover:text-[#15202b]">
            Terms and Conditions
          </Link>
        </p>
      </main>
    </div>
  );
}
