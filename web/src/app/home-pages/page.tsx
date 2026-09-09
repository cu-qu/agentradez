import type { Metadata } from "next";
import Link from "next/link";

import { HOME_PREVIEWS } from "@/components/home-previews";
import { HomePreviewSwitcher } from "@/components/home-preview-switcher";

export const metadata: Metadata = {
  title: "Home page drafts",
  description: "Five Agentradez homepage drafts for review.",
  robots: { index: false, follow: false },
};

export default function HomePagesIndex() {
  return (
    <div className="min-h-full bg-[#111214] text-[#e8eaed]">
      <HomePreviewSwitcher />
      <main className="mx-auto max-w-3xl px-4 py-16">
        <p className="text-xs uppercase tracking-[0.16em] text-[#8b909a]">
          Review set
        </p>
        <h1 className="mt-3 text-3xl font-semibold tracking-tight">
          Five homepage drafts
        </h1>
        <p className="mt-3 max-w-xl text-sm leading-relaxed text-[#8b909a]">
          Same product, different look and slogan. Open each URL, then vote on
          the one that feels clearest. These are drafts — they are not the live
          home at{" "}
          <Link href="/" className="text-[#e8eaed] hover:underline">
            /
          </Link>
          .
        </p>
        <ul className="mt-10 flex flex-col gap-3">
          {HOME_PREVIEWS.map((preview) => (
            <li key={preview.href}>
              <Link
                href={preview.href}
                className="block rounded-xl border border-white/10 bg-[#181a1f] p-5 hover:border-white/25"
              >
                <p className="text-[11px] uppercase tracking-[0.16em] text-[#8b909a]">
                  Home page {preview.id}
                </p>
                <h2 className="mt-1 text-lg font-medium tracking-tight">
                  {preview.name}
                </h2>
                <p className="mt-2 text-sm text-[#e8eaed]/90">{preview.slogan}</p>
                <p className="mt-1 text-sm text-[#8b909a]">{preview.blurb}</p>
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
