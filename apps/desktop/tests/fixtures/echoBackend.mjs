// Test double standing in for facemesh_mouse.backend: echoes each
// incoming command back out, prefixed, so backendProcess.test.ts can
// assert round-trip wiring without spawning Python or touching a camera.
process.stdin.setEncoding("utf8");
let buffer = "";
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  const lines = buffer.split("\n");
  buffer = lines.pop() ?? "";
  for (const line of lines) {
    if (!line.trim()) continue;
    const command = JSON.parse(line);
    process.stdout.write(JSON.stringify({ type: "echo", received: command }) + "\n");
  }
});
