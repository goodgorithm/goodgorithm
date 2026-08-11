import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import styles from "./App.module.css";
import { Feed } from "./components/Feed";
import { Wordmark } from "./components/Wordmark";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <main className={styles.main}>
        <header className={styles.header}>
          <Wordmark />
        </header>
        <Feed />
      </main>
    </QueryClientProvider>
  );
}
