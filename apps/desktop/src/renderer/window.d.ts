export {};

declare global {
  interface Window {
    backend: {
      send: (message: Record<string, unknown>) => void;
      on: (channel: string, callback: (message: unknown) => void) => () => void;
    };
  }
}
