import { Navigate, Outlet, useLocation } from "react-router-dom";

import PageShell from "../components/PageShell";
import { useAuthStore } from "../stores/authStore";

export default function ProtectedRoute() {
  const user = useAuthStore((state) => state.user);
  const initialized = useAuthStore((state) => state.initialized);
  const location = useLocation();

  if (!initialized) {
    return (
      <PageShell>
        <main className="flex min-h-screen items-center justify-center p-8">
          <div className="warm-card px-8 py-6 text-center">
            <p className="animate-float text-4xl">📚</p>
            <p className="mt-3 font-bold text-warm-brown">Getting your books ready…</p>
            <p className="text-sm text-warm-muted">Just a moment ✨</p>
          </div>
        </main>
      </PageShell>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return <Outlet />;
}
