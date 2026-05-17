import { Events, FileSystemAdapter, Plugin, WorkspaceLeaf } from "obsidian";
import { OraClient, OraStatus, defaultOraHome } from "./ora-client";
import {
  DEFAULT_SETTINGS,
  OraPluginSettings,
  OraSettingTab,
} from "./settings";
import { InputView, VIEW_TYPE_INPUT } from "./input-view";

export default class OraPlugin extends Plugin {
  settings!: OraPluginSettings;
  client!: OraClient;
  lastStatus: OraStatus | null = null;
  events: Events = new Events();
  private statusPollHandle: number | null = null;
  private ribbonEl: HTMLElement | null = null;

  async onload(): Promise<void> {
    await this.loadSettings();
    this.client = new OraClient(this.settings.oraHome);

    this.registerView(
      VIEW_TYPE_INPUT,
      (leaf: WorkspaceLeaf) => new InputView(leaf, this),
    );

    this.addSettingTab(new OraSettingTab(this.app, this));

    this.addCommand({
      id: "open-input",
      name: "Open Ora — Input",
      callback: () => this.activateView(VIEW_TYPE_INPUT),
    });

    this.addCommand({
      id: "reconnect",
      name: "Reconnect to Ora",
      callback: () => this.refreshStatus(),
    });

    this.applyRibbon();

    // First status check after layout is ready so the InputView (if
    // restored from a previous session) is mounted and listening.
    this.app.workspace.onLayoutReady(() => {
      this.refreshStatus();
      this.statusPollHandle = window.setInterval(() => {
        this.refreshStatus().catch(() => {});
      }, 30_000);
    });
  }

  async onunload(): Promise<void> {
    if (this.statusPollHandle !== null) {
      window.clearInterval(this.statusPollHandle);
      this.statusPollHandle = null;
    }
  }

  async loadSettings(): Promise<void> {
    const stored = (await this.loadData()) as Partial<OraPluginSettings> | null;
    this.settings = { ...DEFAULT_SETTINGS, ...(stored ?? {}) };
    if (!this.settings.oraHome) this.settings.oraHome = defaultOraHome();
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  getVaultBasePath(): string | null {
    const adapter = this.app.vault.adapter;
    if (adapter instanceof FileSystemAdapter) {
      return adapter.getBasePath();
    }
    return null;
  }

  applyRibbon(): void {
    if (this.ribbonEl) {
      this.ribbonEl.remove();
      this.ribbonEl = null;
    }
    if (this.settings.showRibbonIcon) {
      this.ribbonEl = this.addRibbonIcon("send", "Open Ora — Input", () => {
        this.activateView(VIEW_TYPE_INPUT);
      });
    }
  }

  async activateView(viewType: string): Promise<void> {
    const { workspace } = this.app;
    const existing = workspace.getLeavesOfType(viewType);
    if (existing.length > 0) {
      workspace.revealLeaf(existing[0]);
      return;
    }
    const leaf = workspace.getRightLeaf(false) ?? workspace.getLeaf(true);
    await leaf.setViewState({ type: viewType, active: true });
    workspace.revealLeaf(leaf);
  }

  async refreshStatus(): Promise<void> {
    try {
      const status = await this.client.status();
      // If Ora is installed but down, try to bring it up exactly once per
      // refresh cycle. The user can disable this implicitly by uninstalling
      // Ora; we don't currently expose an explicit toggle.
      if (status.state === "down") {
        this.lastStatus = { state: "starting" };
        // @ts-ignore — custom event
        this.events.trigger("status-change", this.lastStatus);
        try {
          this.client.spawnOra();
          const port = await this.client.waitForReady();
          this.lastStatus = { state: "ready", port };
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          this.lastStatus = { state: "error", message: msg };
        }
      } else {
        this.lastStatus = status;
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      this.lastStatus = { state: "error", message: msg };
    }
    // @ts-ignore — custom event
    this.events.trigger("status-change", this.lastStatus);
  }
}
