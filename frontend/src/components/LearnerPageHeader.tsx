import LearnerAvatar from "./LearnerAvatar";
import LearnerTopNav from "./LearnerTopNav";
import { useAuthStore } from "../stores/authStore";

type LearnerPageHeaderProps = {
  eyebrow: string;
  title: string;
  subtitle?: string;
  showHome?: boolean;
};

export default function LearnerPageHeader({
  eyebrow,
  title,
  subtitle,
  showHome = true,
}: LearnerPageHeaderProps) {
  const learner = useAuthStore((state) => state.user?.learner);

  return (
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div className="flex items-start gap-4">
        <LearnerAvatar learner={learner} size="lg" className="bg-purple-100" />
        <div>
          <p className="text-sm font-bold text-warm-muted">{eyebrow}</p>
          <h1 className="text-3xl font-extrabold text-warm-brown">{title}</h1>
          {subtitle && <p className="mt-1 font-semibold text-warm-brown-soft">{subtitle}</p>}
        </div>
      </div>
      <LearnerTopNav showHome={showHome} />
    </header>
  );
}
