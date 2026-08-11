/** Shared PeerXiv domain state for future modular views. */
export const peerXivStore = {
  state: {
    appName: "PeerXiv",
    activeWorkspace: "home",
    activeResearchRecordId: null,
    activeConversationId: null,
    searchQuery: "",
    selectedField: "All fields",
    sortOrder: "Recent",
    submissionDraft: null,
    researchRecords: [],
    researchers: [],
    connections: [],
    savedRecordIds: [],
    conversations: []
  },

  setWorkspace(workspace) {
    this.state.activeWorkspace = workspace;
    this.state.activeResearchRecordId = null;
  },

  selectResearchRecord(recordId) {
    this.state.activeResearchRecordId = recordId;
  },

  setSearch(query) {
    this.state.searchQuery = query;
  },

  toggleSavedRecord(recordId) {
    const saved = new Set(this.state.savedRecordIds);
    saved.has(recordId) ? saved.delete(recordId) : saved.add(recordId);
    this.state.savedRecordIds = [...saved];
  }
};
