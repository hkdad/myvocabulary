type BrandMarkProps = {
  size?: "sm" | "lg";
};

export default function BrandMark({ size = "lg" }: BrandMarkProps) {
  const isLarge = size === "lg";

  return (
    <div className={`flex items-center gap-3 ${isLarge ? "" : "gap-2"}`}>
      <span
        className={`animate-wiggle inline-flex items-center justify-center rounded-2xl bg-gradient-to-br from-amber-200 to-orange-300 shadow-md ${
          isLarge ? "text-4xl h-16 w-16" : "text-2xl h-10 w-10"
        }`}
        role="img"
        aria-label="Books"
      >
        📚
      </span>
      <div>
        <p
          className={`font-extrabold tracking-tight text-warm-brown ${
            isLarge ? "text-3xl" : "text-xl"
          }`}
        >
          Grow Your Words!
        </p>
        {isLarge && (
          <p className="text-sm font-semibold text-warm-muted">Learn words, have fun! ✨</p>
        )}
      </div>
    </div>
  );
}
