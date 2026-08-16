import { useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import ProtectedRoute from "./routes/ProtectedRoute";
import RoleRoute from "./routes/RoleRoute";
import LoginPage from "./pages/LoginPage";
import DictionaryPage from "./pages/learner/DictionaryPage";
import LearnerHomePage from "./pages/learner/LearnerHomePage";
import LearnerListDetailPage from "./pages/learner/LearnerListDetailPage";
import LearnerWordListsPage from "./pages/learner/LearnerWordListsPage";
import DailyChallengePage from "./pages/learner/DailyChallengePage";
import DictationPage from "./pages/learner/DictationPage";
import ChallengePage from "./pages/learner/ChallengePage";
import ReviewPage from "./pages/learner/ReviewPage";
import StatsPage from "./pages/learner/StatsPage";
import LearnerWordsPage from "./pages/learner/LearnerWordsPage";
import QuestsPage from "./pages/learner/QuestsPage";
import DashboardPage from "./pages/parent/DashboardPage";
import LearnersPage from "./pages/parent/LearnersPage";
import WordListDetailPage from "./pages/parent/WordListDetailPage";
import WordListsPage from "./pages/parent/WordListsPage";
import WordBankPage from "./pages/parent/WordBankPage";
import ParentQuestsPage from "./pages/parent/ParentQuestsPage";
import { useAuthStore } from "./stores/authStore";

const queryClient = new QueryClient();

function AppRoutes() {
  const restoreSession = useAuthStore((state) => state.restoreSession);

  useEffect(() => {
    void restoreSession();
  }, [restoreSession]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<RoleRoute role="parent" />}>
          <Route path="/parent/dashboard" element={<DashboardPage />} />
          <Route path="/parent/learners" element={<LearnersPage />} />
          <Route path="/parent/word-lists" element={<WordListsPage />} />
          <Route path="/parent/word-bank" element={<WordBankPage />} />
          <Route path="/parent/quests" element={<ParentQuestsPage />} />
          <Route path="/parent/word-lists/:id" element={<WordListDetailPage />} />
        </Route>
        <Route element={<RoleRoute role="learner" />}>
          <Route path="/app/home" element={<LearnerHomePage />} />
          <Route path="/app/dictionary" element={<DictionaryPage />} />
          <Route path="/app/dictionary/:word" element={<DictionaryPage />} />
          <Route path="/app/lists" element={<LearnerWordListsPage />} />
          <Route path="/app/lists/:id" element={<LearnerListDetailPage />} />
          <Route path="/app/review" element={<ReviewPage />} />
          <Route path="/app/challenge" element={<DailyChallengePage />} />
          <Route path="/app/dictation" element={<DictationPage mode="typed" />} />
          <Route path="/app/dictation/pick" element={<DictationPage mode="choice" />} />
          <Route path="/app/challenges" element={<ChallengePage />} />
          <Route path="/app/quests" element={<QuestsPage />} />
          <Route path="/app/stats" element={<StatsPage />} />
          <Route path="/app/words" element={<LearnerWordsPage />} />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
