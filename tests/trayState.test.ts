import { describe, expect, it } from "vitest";
import { computeTrayState } from "../src/modules/trayState";

describe("computeTrayState", () => {
  it("paused overrides everything else", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: true, no_face: true, yielded: true })
    ).toEqual({ icon: "paused", title: "FaceMesh Mouse -- Pausado" });
  });

  it("yielded overrides no-face and running", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: false, no_face: true, yielded: true })
    ).toEqual({ icon: "yielded", title: "FaceMesh Mouse -- Controle pelo mouse físico" });
  });

  it("no-face overrides running", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: false, no_face: true, yielded: false })
    ).toEqual({ icon: "no_face", title: "FaceMesh Mouse -- Rosto não detectado" });
  });

  it("running when nothing else applies", () => {
    expect(
      computeTrayState({ control_enabled: true, paused: false, no_face: false, yielded: false })
    ).toEqual({ icon: "running", title: "FaceMesh Mouse" });
  });
});
