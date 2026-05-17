"use client";

import { useRouter } from "next/navigation";
import { CommandPalette } from "@/components/ui/command-palette";

export function CommandShell() {
  const router = useRouter();
  return (
    <CommandPalette
      onTriggerBrief={() => {
        router.push("/dashboard?run=1");
      }}
    />
  );
}
