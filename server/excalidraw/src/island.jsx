import React from "react";
import { createRoot } from "react-dom/client";
import {
  Excalidraw,
  convertToExcalidrawElements,
  exportToBlob,
  loadFromBlob,
  serializeAsJSON,
} from "@excalidraw/excalidraw";

const WHITE = "#ffffff";
const MAX_SIDE = 4096;
const PADDING = 16;

class IslandErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error) {
    this.props.onFailure?.(error);
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

function cleanAppState(appState) {
  return {
    ...appState,
    theme: "light",
    viewBackgroundColor: WHITE,
    exportBackground: true,
    exportEmbedScene: false,
    exportWithDarkMode: false,
    collaborators: new Map(),
  };
}

async function canonicalPng(snapshot) {
  if (!snapshot.elements.some((element) => !element.isDeleted)) {
    const canvas = document.createElement("canvas");
    canvas.width = PADDING * 2;
    canvas.height = PADDING * 2;
    const context = canvas.getContext("2d");
    context.fillStyle = WHITE;
    context.fillRect(0, 0, canvas.width, canvas.height);
    return new Promise((resolve, reject) => canvas.toBlob(
      (blob) => blob ? resolve(blob) : reject(new Error("Could not export empty visual")),
      "image/png",
    ));
  }
  return exportToBlob({
    elements: snapshot.elements,
    appState: cleanAppState(snapshot.appState),
    files: snapshot.files,
    mimeType: "image/png",
    exportPadding: PADDING,
    getDimensions(width, height) {
      const scale = Math.min(1, MAX_SIDE / Math.max(width, height, 1));
      return {
        width: Math.max(1, Math.round(width * scale)),
        height: Math.max(1, Math.round(height * scale)),
        scale,
      };
    },
  });
}

function serialize(snapshot) {
  return new Blob([
    serializeAsJSON(
      snapshot.elements,
      cleanAppState(snapshot.appState),
      snapshot.files,
      "local",
    ),
  ], { type: "application/vnd.excalidraw+json" });
}

async function load(blob) {
  return loadFromBlob(blob, null, null);
}

function freshId(prefix) {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
  return `${prefix}-${random.replace(/[^a-zA-Z0-9_-]/g, "")}`;
}

function readDimensions(dataURL) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve({ width: image.naturalWidth || 1, height: image.naturalHeight || 1 });
    image.onerror = () => reject(new Error("Could not decode flattened visual PNG"));
    image.src = dataURL;
  });
}

function blobToDataURL(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error || new Error("Could not read visual PNG"));
    reader.readAsDataURL(blob);
  });
}

async function imageBackedScene(pngBlob, locked = true, customData = null) {
  const dataURL = await blobToDataURL(pngBlob);
  const { width, height } = await readDimensions(dataURL);
  const fileId = freshId("ora-image");
  const now = Date.now();
  const files = {
    [fileId]: {
      id: fileId,
      dataURL,
      mimeType: "image/png",
      created: now,
      lastRetrieved: now,
    },
  };
  const [element] = convertToExcalidrawElements([{
    type: "image",
    id: freshId("ora-element"),
    x: 0,
    y: 0,
    width,
    height,
    fileId,
    locked,
    status: "saved",
    scale: [1, 1],
    customData: customData || undefined,
  }], { regenerateIds: false });
  return {
    elements: [element],
    appState: { theme: "light", viewBackgroundColor: WHITE },
    files,
  };
}

async function insertPng(api, pngBlob, locked = true, customData = null) {
  const scene = await imageBackedScene(pngBlob, locked, customData);
  api.addFiles(Object.values(scene.files));
  const existing = api.getSceneElements().filter((element) => !element.isDeleted);
  const maxX = existing.reduce((value, element) => Math.max(value, element.x + element.width), 0);
  const [image] = scene.elements;
  const placed = existing.length ? { ...image, x: maxX + PADDING * 2 } : image;
  api.updateScene({ elements: [...existing, placed] });
  api.scrollToContent(placed, { fitToContent: true });
  return placed;
}

function mount(host, options = {}) {
  if (!host) throw new Error("Excalidraw host is required");
  let api = null;
  const root = createRoot(host);
  const onChange = (elements, appState, files) => options.onChange?.(elements, appState, files);

  function Island() {
    return React.createElement(Excalidraw, {
      initialData: options.initialData || undefined,
      theme: "light",
      excalidrawAPI(nextApi) {
        if (!nextApi || nextApi === api) return;
        api = nextApi;
        options.onReady?.(api);
      },
      onChange,
      UIOptions: { canvasActions: { export: false, loadScene: false, saveToActiveFile: false } },
    });
  }

  root.render(React.createElement(
    IslandErrorBoundary,
    { onFailure: options.onFailure },
    React.createElement(Island),
  ));
  return {
    unmount() { root.unmount(); },
    getApi() { return api; },
  };
}

window.OraExcalidrawIsland = {
  mount,
  serialize,
  load,
  canonicalPng,
  imageBackedScene,
  insertPng,
  constants: { background: WHITE, maxSide: MAX_SIDE, padding: PADDING },
};
