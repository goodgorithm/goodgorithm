import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { Feed } from "./components/Feed";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <main>
        <h1>Goodgorithm</h1>
        <Feed />
      </main>
    </QueryClientProvider>
  );
}
