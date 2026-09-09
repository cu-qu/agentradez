import Link from "next/link";

import { Wordmark } from "@/components/ui";

export default function NotFound() {
  return (
    <div className="flex min-h-full flex-col items-center justify-center gap-4 px-4">
      <Link href="/">
        <Wordmark />
      </Link>
      <p className="text-sm text-muted">That page does not exist.</p>
      <Link href="/" className="text-sm hover:underline">
        Go home
      </Link>
    </div>
  );
}
