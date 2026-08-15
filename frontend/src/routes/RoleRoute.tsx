import { Navigate, Outlet } from "react-router-dom";

import { useAuthStore } from "../stores/authStore";

type RoleRouteProps = {
  role: "parent" | "learner";
};

export default function RoleRoute({ role }: RoleRouteProps) {
  const user = useAuthStore((state) => state.user);

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  if (user.role !== role) {
    return <Navigate to={user.role === "parent" ? "/parent/dashboard" : "/app/home"} replace />;
  }

  return <Outlet />;
}
