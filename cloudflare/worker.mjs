import { Container } from "@cloudflare/containers";

export class PeerXivContainer extends Container {
  defaultPort = 8080;
  sleepAfter = "10m";
}

export default {
  async fetch(request, env) {
    const container = env.PEERXIV_CONTAINER.getByName("peerxiv-main");
    return container.fetch(request);
  }
};