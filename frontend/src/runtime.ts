import { useEffect, useState } from "react";
import { ProotRuntime, watchRuntime, type RuntimeStatus } from "capacitor-proot-runtime";

/** Estado do Ubuntu/servidor: idle → installing → starting → ready (ou failed). */
export const useRuntime = (): RuntimeStatus => {
  const [status, setStatus] = useState<RuntimeStatus>({ state: "idle" });
  useEffect(() => watchRuntime(setStatus), []);
  return status;
};

export const restartRuntime = () => ProotRuntime.restart();
export const fetchLogs = () => ProotRuntime.getLogs({ lines: 200 }).then((r) => r.backend);
