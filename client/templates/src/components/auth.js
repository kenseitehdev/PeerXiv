/** Authentication view-model placeholders for the PeerXiv researcher account flow. */
export const authState = {
  actor: null,
  authenticated: false,
  pending: false
};

export function setAuthenticatedResearcher(researcher) {
  authState.actor = researcher;
  authState.authenticated = Boolean(researcher);
}
