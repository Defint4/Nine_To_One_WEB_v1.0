import { avatarParts } from "@/lib/avatars";

const SIZES = {
  sm: "size-8 text-base",
  md: "size-11 text-xl",
  lg: "size-16 text-3xl",
  xl: "size-20 text-4xl",
} as const;

export default function Avatar({
  id,
  size = "md",
  dimmed = false,
}: {
  id: string;
  size?: keyof typeof SIZES;
  dimmed?: boolean;
}) {
  const { emoji, coin } = avatarParts(id);
  return (
    <span
      className={`${SIZES[size]} inline-flex shrink-0 items-center justify-center rounded-full ring-2 ring-black/25 ${dimmed ? "opacity-40 saturate-50" : ""}`}
      style={{ background: `radial-gradient(circle at 35% 30%, ${coin}dd, ${coin})` }}
      aria-hidden
    >
      {emoji}
    </span>
  );
}
