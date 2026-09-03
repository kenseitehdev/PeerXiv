import assert from "node:assert/strict";

const url = process.env.PEERXIV_SOCKET_URL;
if (!url) throw new Error("PEERXIV_SOCKET_URL is required");

const socket = new WebSocket(url);
let namespaceConnected = false;
let readyReceived = false;

const timeout = setTimeout(() => {
  socket.close();
  throw new Error("Socket.IO network smoke test timed out");
}, 8_000);

await new Promise((resolve, reject) => {
  socket.addEventListener("error", () => reject(new Error("WebSocket connection failed")));
  socket.addEventListener("message", (event) => {
    const packet = String(event.data);
    if (packet.startsWith("0{")) {
      socket.send("40/social,");
      return;
    }
    if (packet === "2") {
      socket.send("3");
      return;
    }
    if (packet.startsWith('42/social,["server.ready"')) {
      readyReceived = true;
      return;
    }
    if (packet.startsWith("40/social,")) {
      namespaceConnected = true;
      socket.send('42/social,1["paper.watch",{"paper_id":"px:network.smoke"}]');
      return;
    }
    if (packet.startsWith("43/social,1")) {
      const acknowledgement = JSON.parse(packet.slice("43/social,1".length));
      assert.deepEqual(acknowledgement, [
        { ok: true, room: "paper:px:network.smoke" },
      ]);
      resolve();
    }
  });
});

clearTimeout(timeout);
assert.equal(namespaceConnected, true);
// server.ready may arrive immediately before or after the namespace connect ACK.
await new Promise((resolve) => setTimeout(resolve, 20));
assert.equal(readyReceived, true);
socket.close();
console.log("live WebSocket smoke: namespace=/social room-ack=pass");
