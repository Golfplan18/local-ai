import { ItemView, Notice, WorkspaceLeaf } from "obsidian";
import type OraPlugin from "./main";
import { resolveOutputDestination } from "./settings";

export const VIEW_TYPE_INPUT = "ora-input";

export class InputView extends ItemView {
  private plugin: OraPlugin;
  private textarea!: HTMLTextAreaElement;
  private statusEl!: HTMLElement;
  private privateToggle!: HTMLInputElement;
  private stealthToggle!: HTMLInputElement;
  private submitBtn!: HTMLButtonElement;

  constructor(leaf: WorkspaceLeaf, plugin: OraPlugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType(): string {
    return VIEW_TYPE_INPUT;
  }

  getDisplayText(): string {
    return "Ora — Input";
  }

  getIcon(): string {
    return "send";
  }

  async onOpen(): Promise<void> {
    const container = this.contentEl;
    container.empty();
    container.addClass("ora-input-view");

    const header = container.createEl("div", { cls: "ora-input-header" });
    header.createEl("h3", { text: "Ora" });
    this.statusEl = header.createEl("div", { cls: "ora-input-status" });

    this.textarea = container.createEl("textarea", {
      cls: "ora-input-textarea",
      attr: { placeholder: "What's on your mind?" },
    });

    const toggleRow = container.createEl("div", { cls: "ora-input-toggles" });

    const privateLabel = toggleRow.createEl("label", { cls: "ora-toggle" });
    this.privateToggle = privateLabel.createEl("input", {
      attr: { type: "checkbox" },
    });
    privateLabel.createSpan({ text: "Private" });

    const stealthLabel = toggleRow.createEl("label", { cls: "ora-toggle" });
    this.stealthToggle = stealthLabel.createEl("input", {
      attr: { type: "checkbox" },
    });
    stealthLabel.createSpan({ text: "Stealth" });

    // Mutually exclusive — you can't be both private and stealth.
    this.privateToggle.addEventListener("change", () => {
      if (this.privateToggle.checked) this.stealthToggle.checked = false;
    });
    this.stealthToggle.addEventListener("change", () => {
      if (this.stealthToggle.checked) this.privateToggle.checked = false;
    });

    const submitRow = container.createEl("div", { cls: "ora-input-submit-row" });
    this.submitBtn = submitRow.createEl("button", {
      text: "Send to Ora",
      cls: "mod-cta",
    });
    this.submitBtn.addEventListener("click", () => this.submit());

    this.textarea.addEventListener("keydown", (ev) => {
      if (
        (ev.key === "Enter" && (ev.metaKey || ev.ctrlKey)) ||
        (ev.key === "Enter" && !ev.shiftKey && !ev.altKey && this.textarea.value.trim() === this.textarea.value && ev.metaKey)
      ) {
        ev.preventDefault();
        this.submit();
      }
    });

    this.updateStatus();
    this.registerEvent(
      // @ts-ignore — custom plugin event
      this.plugin.events.on("status-change", () => this.updateStatus()),
    );
  }

  async onClose(): Promise<void> {
    this.contentEl.empty();
  }

  private updateStatus(): void {
    const status = this.plugin.lastStatus;
    if (!status) {
      this.statusEl.setText("Connecting...");
      this.submitBtn.disabled = true;
      return;
    }
    switch (status.state) {
      case "ready":
        this.statusEl.setText(`Ready (port ${status.port})`);
        this.submitBtn.disabled = false;
        break;
      case "starting":
        this.statusEl.setText("Starting Ora...");
        this.submitBtn.disabled = true;
        break;
      case "down":
        this.statusEl.setText("Ora is not running. Start Ora and reconnect.");
        this.submitBtn.disabled = true;
        break;
      case "not-installed":
        this.statusEl.setText(
          `Ora not found at ${status.oraHome}. Install Ora, or update the path in plugin settings.`,
        );
        this.submitBtn.disabled = true;
        break;
      case "error":
        this.statusEl.setText(`Error: ${status.message}`);
        this.submitBtn.disabled = true;
        break;
    }
  }

  private async submit(): Promise<void> {
    const status = this.plugin.lastStatus;
    if (!status || status.state !== "ready") {
      new Notice("Ora is not ready.");
      return;
    }
    const message = this.textarea.value.trim();
    if (!message) return;

    const tag = this.stealthToggle.checked
      ? "stealth"
      : this.privateToggle.checked
        ? "private"
        : "";

    const vaultBase = this.plugin.getVaultBasePath();
    const output_destination = resolveOutputDestination(
      this.plugin.settings,
      vaultBase,
    );

    const panel_id = `obsidian-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`;

    this.submitBtn.disabled = true;
    this.statusEl.setText("Sending...");
    try {
      const resp = await this.plugin.client.chat(status.port, {
        message,
        panel_id,
        is_main_feed: true,
        tag,
        output_destination,
      });
      if (resp.status === "ok") {
        new Notice(`Sent to Ora. Conversation ${resp.conversation_id}.`);
        this.textarea.value = "";
        this.statusEl.setText(`Ready (port ${status.port})`);
      } else {
        new Notice(`Ora returned error: ${resp.failure_summary ?? "unknown"}`);
        this.statusEl.setText(`Error: ${resp.failure_summary ?? "unknown"}`);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      new Notice(`Send failed: ${msg}`);
      this.statusEl.setText(`Error: ${msg}`);
    } finally {
      this.submitBtn.disabled = false;
    }
  }
}
