import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import styles from "./App.module.css";
import { Feed } from "./components/Feed";
import { MissionPage } from "./components/MissionPage";
import { Wordmark } from "./components/Wordmark";
import { useLocation } from "./lib/useLocation";

const queryClient = new QueryClient();

export default function App() {
  const [path, navigate] = useLocation();
  const onMissionPage = path === "/mission";

  return (
    <QueryClientProvider client={queryClient}>
      <main className={styles.main}>
        <header className={styles.header}>
          <Wordmark />
          {!onMissionPage && (
            <button type="button" className={styles.missionLink} onClick={() => navigate("/mission")}>
              Our mission
            </button>
          )}
        </header>
        {onMissionPage ? <MissionPage onBack={() => navigate("/")} /> : <Feed />}
      </main>
    </QueryClientProvider>
  );
}
