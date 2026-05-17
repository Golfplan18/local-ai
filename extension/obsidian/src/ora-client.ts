import { spawn } from "child_process";
import { readFile } from "fs/promises";
import { existsSync } from "fs";
import { homedir } from "os";
import { join } from "path";

export type OraStatus =
  | { state: "ready"; port: number; version?: string }
  | { state: "starting"; port?: number }
  | { state: "not-installed"; oraHome: string }
  | { state: "down"; oraHome: string }
  | { state: "error"; message: string };

export interface ChatPayload {
  message: string;
  panel_id?: string;
  is_main_feed?: boolean;
  tag?: "" | "private" | "stealth";
  output_destination?: string;
}

export interface ChatResponse {
  status: "ok" | "errored";
  conversation_id: string;
  chunk_id?: string;
  failure_summary?: string;
}

export class OraClient {
  constructor(private oraHome: string) {}

  setOraHome(oraHome: string): void {
    this.oraHome = oraHome;
  }

  private portFile(): string {
    return join(this.oraHome, "server", ".port");
  }

  private startupScript(): string {
    return process.platform === "win32"
      ? join(this.oraHome, "start.bat")
      : join(this.oraHome, "start.sh");
  }

  async readPort(): Promise<number | null> {
    try {
      const raw = await readFile(this.portFile(), "utf-8");
      const port = parseInt(raw.trim(), 10);
      return Number.isFinite(port) ? port : null;
    } catch {
      return null;
    }
  }

  async pingHealth(port: number, timeoutMs = 1500): Promise<boolean> {
    try {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), timeoutMs);
      const resp = await fetch(`http://localhost:${port}/health`, {
        signal: ctrl.signal,
      });
      clearTimeout(timer);
      return resp.ok;
    } catch {
      return false;
    }
  }

  async status(): Promise<OraStatus> {
    if (!existsSync(this.oraHome)) {
      return { state: "not-installed", oraHome: this.oraHome };
    }
    const port = await this.readPort();
    if (port === null) {
      return { state: "down", oraHome: this.oraHome };
    }
    const ok = await this.pingHealth(port);
    return ok
      ? { state: "ready", port }
      : { state: "down", oraHome: this.oraHome };
  }

  spawnOra(): void {
    const script = this.startupScript();
    if (!existsSync(script)) {
      throw new Error(`Ora startup script not found at ${script}`);
    }
    spawn(script, [], {
      cwd: this.oraHome,
      detached: true,
      stdio: "ignore",
    }).unref();
  }

  async waitForReady(timeoutMs = 60_000, pollMs = 1000): Promise<number> {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const port = await this.readPort();
      if (port !== null && (await this.pingHealth(port))) {
        return port;
      }
      await new Promise((r) => setTimeout(r, pollMs));
    }
    throw new Error(
      `Timed out waiting for Ora to respond on /health after ${timeoutMs}ms`,
    );
  }

  async chat(port: number, payload: ChatPayload): Promise<ChatResponse> {
    const resp = await fetch(`http://localhost:${port}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const text = await resp.text();
      throw new Error(`Ora /chat returned ${resp.status}: ${text}`);
    }
    return (await resp.json()) as ChatResponse;
  }
}

export function defaultOraHome(): string {
  return join(homedir(), "ora");
}
