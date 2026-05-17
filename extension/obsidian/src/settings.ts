import { App, PluginSettingTab, Setting, normalizePath } from "obsidian";
import type OraPlugin from "./main";
import { defaultOraHome } from "./ora-client";

export type DestinationMode = "vault-folder" | "ora-default" | "custom";

export interface OraPluginSettings {
  oraHome: string;
  destinationMode: DestinationMode;
  vaultFolder: string;
  customFolder: string;
  defaultViewType: "input" | "full" | "qa";
  showRibbonIcon: boolean;
}

export const DEFAULT_SETTINGS: OraPluginSettings = {
  oraHome: defaultOraHome(),
  destinationMode: "vault-folder",
  vaultFolder: "Ora Conversations",
  customFolder: "",
  defaultViewType: "input",
  showRibbonIcon: true,
};

export class OraSettingTab extends PluginSettingTab {
  plugin: OraPlugin;

  constructor(app: App, plugin: OraPlugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display(): void {
    const { containerEl } = this;
    containerEl.empty();

    containerEl.createEl("h2", { text: "Connection" });

    new Setting(containerEl)
      .setName("Ora installation path")
      .setDesc(
        "Where Ora is installed on disk. The plugin reads <path>/server/.port " +
          "to find the running server.",
      )
      .addText((text) =>
        text
          .setPlaceholder(defaultOraHome())
          .setValue(this.plugin.settings.oraHome)
          .onChange(async (value) => {
            this.plugin.settings.oraHome = value.trim() || defaultOraHome();
            await this.plugin.saveSettings();
            this.plugin.client.setOraHome(this.plugin.settings.oraHome);
          }),
      );

    new Setting(containerEl)
      .setName("Reconnect")
      .setDesc("Re-check whether Ora is running and refresh views.")
      .addButton((btn) =>
        btn.setButtonText("Reconnect").onClick(async () => {
          await this.plugin.refreshStatus();
        }),
      );

    containerEl.createEl("h2", { text: "Output destination" });

    new Setting(containerEl)
      .setName("Where Ora writes conversation files")
      .setDesc(
        "Each query from the input view produces a markdown file. Choose " +
          "where it lands. Falls back to Ora's default folder if the path " +
          "is invalid.",
      )
      .addDropdown((drop) => {
        drop
          .addOption("vault-folder", "In this vault")
          .addOption("ora-default", "Ora's default (~/Documents/conversations/)")
          .addOption("custom", "Custom folder")
          .setValue(this.plugin.settings.destinationMode)
          .onChange(async (value) => {
            this.plugin.settings.destinationMode = value as DestinationMode;
            await this.plugin.saveSettings();
            this.display();
          });
      });

    if (this.plugin.settings.destinationMode === "vault-folder") {
      new Setting(containerEl)
        .setName("Vault folder")
        .setDesc("Folder name inside this vault. Created if it doesn't exist.")
        .addText((text) =>
          text
            .setPlaceholder("Ora Conversations")
            .setValue(this.plugin.settings.vaultFolder)
            .onChange(async (value) => {
              this.plugin.settings.vaultFolder = value.trim() || "Ora Conversations";
              await this.plugin.saveSettings();
            }),
        );
    } else if (this.plugin.settings.destinationMode === "custom") {
      new Setting(containerEl)
        .setName("Custom folder (absolute path)")
        .setDesc(
          "Any absolute path on disk. The plugin only honors absolute " +
            "paths; relative paths fall back to Ora's default.",
        )
        .addText((text) =>
          text
            .setPlaceholder("/Users/you/Documents/conversations")
            .setValue(this.plugin.settings.customFolder)
            .onChange(async (value) => {
              this.plugin.settings.customFolder = value.trim();
              await this.plugin.saveSettings();
            }),
        );
    }

    containerEl.createEl("h2", { text: "Interface" });

    new Setting(containerEl)
      .setName("Default view when opening Ora")
      .setDesc("The view used when you run the 'Open Ora' command.")
      .addDropdown((drop) =>
        drop
          .addOption("input", "Input only")
          .addOption("full", "Full V3")
          .addOption("qa", "Q&A")
          .setValue(this.plugin.settings.defaultViewType)
          .onChange(async (value) => {
            this.plugin.settings.defaultViewType = value as
              | "input"
              | "full"
              | "qa";
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl)
      .setName("Show ribbon icon")
      .setDesc("Adds a sidebar button for opening the input view.")
      .addToggle((toggle) =>
        toggle
          .setValue(this.plugin.settings.showRibbonIcon)
          .onChange(async (value) => {
            this.plugin.settings.showRibbonIcon = value;
            await this.plugin.saveSettings();
            this.plugin.applyRibbon();
          }),
      );

    containerEl.createEl("h2", { text: "Diagnostics" });
    this.renderDiagnostics(containerEl);
  }

  private renderDiagnostics(containerEl: HTMLElement): void {
    const block = containerEl.createDiv({ cls: "ora-diagnostics" });
    const status = this.plugin.lastStatus;
    const line = block.createDiv();
    if (!status) {
      line.setText("Status: unknown — click Reconnect.");
      return;
    }
    switch (status.state) {
      case "ready":
        line.setText(`Status: ready (port ${status.port})`);
        break;
      case "starting":
        line.setText("Status: starting...");
        break;
      case "down":
        line.setText(`Status: down (Ora at ${status.oraHome})`);
        break;
      case "not-installed":
        line.setText(`Status: not installed at ${status.oraHome}`);
        break;
      case "error":
        line.setText(`Status: error — ${status.message}`);
        break;
    }
  }
}

export function resolveOutputDestination(
  settings: OraPluginSettings,
  vaultBasePath: string | null,
): string {
  switch (settings.destinationMode) {
    case "vault-folder":
      if (!vaultBasePath) return "";
      return normalizePathJoin(vaultBasePath, settings.vaultFolder);
    case "ora-default":
      return "";
    case "custom":
      return settings.customFolder;
  }
}

function normalizePathJoin(base: string, sub: string): string {
  const cleanSub = normalizePath(sub).replace(/^\/+/, "");
  if (base.endsWith("/")) return base + cleanSub;
  return base + "/" + cleanSub;
}
