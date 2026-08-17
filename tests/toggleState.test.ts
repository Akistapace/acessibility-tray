import { describe, expect, it } from "vitest";
import { computeToggleState } from "../src/renderer/config/toggleState";

const STOPPED = { control_enabled: false, paused: false, no_face: false, yielded: false };
const PAUSED = { control_enabled: true, paused: true, no_face: false, yielded: false };
const ACTIVE = { control_enabled: true, paused: false, no_face: false, yielded: false };

describe("computeToggleState", () => {
  it("shows Iniciar when control is stopped", () => {
    expect(computeToggleState(STOPPED)).toEqual({
      statusText: "Controle parado",
      buttonText: "Iniciar controle do mouse",
      nextCommand: "start",
    });
  });

  it("shows Retomar when paused", () => {
    expect(computeToggleState(PAUSED)).toEqual({
      statusText: "Controle pausado",
      buttonText: "Retomar controle do mouse",
      nextCommand: "resume",
    });
  });

  it("shows Parar when active", () => {
    expect(computeToggleState(ACTIVE)).toEqual({
      statusText: "Controle ativo",
      buttonText: "Parar controle do mouse",
      nextCommand: "stop",
    });
  });
});
