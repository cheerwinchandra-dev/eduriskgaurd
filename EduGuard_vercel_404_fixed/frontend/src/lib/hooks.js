import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** Load a path from the backend. Pass null to skip. `reload()` refreshes without flashing a spinner. */
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: Boolean(path) });
  const latest = useRef(0);

  const load = useCallback(
    async (silent = false) => {
      const ticket = ++latest.current;
      if (!path) {
        setState({ data: null, error: null, loading: false });
        return;
      }
      if (!silent) setState((s) => ({ ...s, loading: true, error: null }));
      try {
        const data = await api.get(path);
        if (ticket === latest.current) setState({ data, error: null, loading: false });
      } catch (error) {
        if (ticket === latest.current) setState({ data: null, error, loading: false });
      }
    },
    [path]
  );

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: () => load(true) };
}
