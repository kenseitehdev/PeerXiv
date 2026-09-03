const STORAGE_KEY = "peerxiv.alpha.v1";
const LEGACY_KEYS = ["peerxiv.prototype.v1"];

export function loadPrototype() {
  try {
    for (const key of LEGACY_KEYS) window.localStorage.removeItem(key);
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (error) {
    console.warn("PeerXiv local state could not be loaded", error);
    return {};
  }
}

export function savePrototype(snapshot) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
    return true;
  } catch (error) {
    console.warn("PeerXiv local state could not be saved", error);
    return false;
  }
}

export function clearPrototype() {
  window.localStorage.removeItem(STORAGE_KEY);
  for (const key of LEGACY_KEYS) window.localStorage.removeItem(key);
}
