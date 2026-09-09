"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { HOME_PREVIEWS } from "@/components/home-previews";

export function HomePreviewSwitcher() {
  const pathname = usePathname();

  return (
    <div className="sticky top-0 z-30 border-b border-white/10 bg-[#111214] text-[#e8eaed]">
      <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-2.5 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[11px] uppercase tracking-[0.14em] text-[#8b909a]">
          Design drafts — pick a favorite
          <span className="mx-2 hidden text-white/20 sm:inline">·</span>
          <Link href="/home-pages" className="normal-case tracking-normal text-[#c9a227] hover:underline">
            All versions
          </Link>
        </p>
        <nav className="flex flex-wrap items-center gap-1.5">
          {HOME_PREVIEWS.map((preview) => {
            const active = pathname === preview.href;
            return (
              <Link
                key={preview.href}
                href={preview.href}
                className={
                  active
                    ? "rounded-full bg-white px-3 py-1 text-xs font-medium text-[#111214]"
                    : "rounded-full px-3 py-1 text-xs text-[#8b909a] hover:bg-white/10 hover:text-white"
                }
              >
                {preview.id} {preview.name}
              </Link>
            );
          })}
        </nav>
      </div>
    </div>
  );
}
