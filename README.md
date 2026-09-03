# Accessibility Mouse Tracking

Control your mouse with your head, without using your hands.

![FaceMesh Mouse Demo](docs/media/demo.gif)

## Why it exists

This project was created to help people with motor limitations affecting their hands or arms use a computer. By tracking the face through the webcam, the app moves the cursor based on head movements and turns facial expressions (blinking, raising an eyebrow, opening your mouth) into clicks. You can use the entire mouse without touching anything.

## How it works

* Move your head → the cursor moves (just like a real mouse, with adjustable sensitivity).
* Make a facial gesture (e.g., blink your left eye) → triggers a click. Nine gestures are available, each configurable to any action (left click, right click, double click, scroll) or disabled.
* Each gesture requires you to hold the expression for a short period before triggering, preventing a natural blink from accidentally becoming a click.
* Once configured, the app saves your settings and runs in the background with a system tray icon. No window needs to remain open.
* A floating circle provides quick access to the Windows virtual keyboard and voice typing, for users who also need to type without their hands.
* If you use a physical mouse, the app immediately gives control back to it and resumes head control when you stop.

Global shortcuts: `Ctrl+Alt+P` pauses/resumes head control, and `Ctrl+Alt+O` reopens the configuration window.

## Requirements

* Windows
* Webcam with camera permissions enabled

## Usage

```powershell
pnpm install

pnpm dev
```

The configuration window opens on the first run: camera preview on the left, with configuration tabs on the right (Movement, Gestures, Extras, Help).

Adjust the sensitivity and gestures, click **"Save Settings"**, and then click **"Start Mouse Control"**.

## Tests

```powershell
pnpm test
```

## Build the Installer (.exe)

```powershell
pnpm dist
```

The installer will be generated at:

`apps/desktop/release/FaceMesh Mouse Setup <version>.exe`

* The first launch is slower because the facial tracking model needs to load.
* The installer is unsigned, so Windows SmartScreen may display a warning on first use.
* The app needs camera permission the first time it runs.

## Open Source

This is an open-source project released under the [MIT](LICENSE) license. Feel free to use, modify, and contribute.
