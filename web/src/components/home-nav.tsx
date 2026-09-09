"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth/provider";

export function HomeNav() {
  const { status } = useAuth();
  const signedIn = status === "authenticated";

  return (
    <nav className="flex items-center gap-4 text-sm">
      <Link href="/how-it-works" className="text-[#8b919c] hover:text-white">
        How it works
      </Link>
      <Link href="/strategies" className="text-[#8b919c] hover:text-white">
        Strategies
      </Link>
      {signedIn ? (
        <Link
          href="/dashboard"
          className="rounded-md bg-[#3d9a7a] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#34856a]"
        >
          Dashboard
        </Link>
      ) : (
        <>
          <Link href="/login" className="text-[#8b919c] hover:text-white">
            Sign in
          </Link>
          <Link
            href="/register"
            className="rounded-md bg-[#3d9a7a] px-3 py-1.5 text-sm font-medium text-white hover:bg-[#34856a]"
          >
            Create account
          </Link>
        </>
      )}
    </nav>
  );
}
