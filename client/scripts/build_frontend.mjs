import { copyFile, mkdir } from "node:fs/promises";

const destinationDirectory = "client/templates/vendor";
await mkdir(destinationDirectory, { recursive: true });
await copyFile(
  "node_modules/socket.io-client/dist/socket.io.esm.min.js",
  `${destinationDirectory}/socket.io.esm.min.js`,
);

