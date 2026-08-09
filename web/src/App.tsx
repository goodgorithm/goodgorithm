import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import styles from "./App.module.css";
import { Feed } from "./components/Feed";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <main className={styles.main}>
        <h1 className={styles.heading}>Goodgorithm</h1>
        <Feed />
      </main>
    </QueryClientProvider>
  );
}
