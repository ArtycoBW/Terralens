"use client";
import { Button } from "@/components/ui/button";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, ApiError, setCsrf, type Session } from "@/lib/api";
const Context = createContext<{
  session: Session;
  reset: () => Promise<void>;
} | null>(null);
export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw new Error("Workspace context unavailable");
  return value;
}
export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15000,
            refetchOnWindowFocus: true,
            retry: (n, e) =>
              n < 2 &&
              (!(e instanceof ApiError) || e.status >= 500 || e.status === 0),
          },
          mutations: { retry: false },
        },
      }),
  );
  const [session, setSession] = useState<Session | null>(null),
    [error, setError] = useState<Error | null>(null),
    [expired, setExpired] = useState(false);
  const connect = useCallback(async () => {
    try {
      let s: Session;
      try {
        s = await api<Session>("session");
      } catch (e) {
        if (!(e instanceof ApiError) || e.status !== 401) throw e;
        s = await api<Session>("session", { method: "POST", body: "{}" });
      }
      setCsrf(s.csrf_token);
      setSession(s);
      setExpired(false);
      setError(null);
    } catch (e) {
      setError(e as Error);
    }
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => void connect(), 0);
    const expire = () => {
      setExpired(true);
      client.cancelQueries();
      client.clear();
      setCsrf("");
    };
    window.addEventListener("session-expired", expire);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("session-expired", expire);
    };
  }, [connect, client]);
  async function reset() {
    await api("session", { method: "DELETE" });
    await client.cancelQueries();
    client.clear();
    setSession(null);
    setCsrf("");
    await connect();
  }
  if (error)
    return (
      <main
        id="main"
        className="mx-auto my-[15dvh] grid max-w-xl gap-5 px-6 [&_h1]:text-3xl"
      >
        <h1>Не удалось открыть пространство</h1>
        <p role="alert">{error.message}</p>
        <Button variant="ghost" className="mt-3 w-fit" onClick={connect}>
          Повторить подключение
        </Button>
      </main>
    );
  if (expired && session)
    return (
      <main
        id="main"
        className="mx-auto my-[15dvh] grid max-w-xl gap-5 px-6 [&_h1]:text-3xl"
      >
        <h1>Сессия истекла</h1>
        <p>Данные предыдущего пространства скрыты. Начните новую сессию.</p>
        <Button
          variant="ghost"
          className="mt-3 w-fit"
          onClick={() => {
            setSession(null);
            void connect();
          }}
        >
          Создать новое пространство
        </Button>
      </main>
    );
  if (!session)
    return (
      <main
        id="main"
        className="mx-auto my-[15dvh] grid max-w-xl gap-5 px-6 [&_h1]:text-3xl"
        aria-busy="true"
      >
        Подключаем рабочее пространство…
      </main>
    );
  return (
    <QueryClientProvider client={client}>
      <Context.Provider value={{ session, reset }}>{children}</Context.Provider>
    </QueryClientProvider>
  );
}
