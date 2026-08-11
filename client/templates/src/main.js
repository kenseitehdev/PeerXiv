import { loadPrototype, savePrototype } from "./persistence.js";
import { io } from "../vendor/socket.io.esm.min.js";

// Alpha records are loaded from the backend. Keep these collections empty so a
// newly migrated deployment starts as a genuinely empty archive.
const papers = [];

const topics = [
  ["Artificial Intelligence","cs.AI"], ["Machine Learning","cs.LG"], ["Distributed Systems","cs.DC"],
  ["Mathematics","math"], ["Physics","physics"], ["Quantitative Biology","q-bio"], ["Open Science","meta"]
];

const discussions = [];
const conversations = [];
const researchers = [];
const presentations = [];
const workspaces = [];
const conferences = [];
const journals = [];

const persisted = loadPrototype();

const state = {
  page:"home", query:"", topic:"All topics", sort:persisted.preferences?.sort||"new",
  selectedPaper:null, selectedDiscussion:null, selectedWorkspace:null, selectedPresentation:null,
  selectedConference:null, selectedJournal:null, workspaceTab:"overview", conversation:0,
  uploadOpen:false, workflowModal:null, integrationModal:null, notificationOpen:false,
  citationPaper:null, citationStyle:"apa", shareTarget:null, discussionFilter:"active", discussionContext:null,
  mobileNavOpen:false, mobileConversationOpen:false, exploreOpen:true, spacesOpen:true,
  discussionsOpen:true, expandedAbstracts:new Set(), votes:new Map(persisted.votes||[]),
  integrations:persisted.integrations||{
    orcid:{status:"disconnected", identifier:"", visibility:"public"},
    overleaf:{status:"disconnected", projectName:"", projectUrl:"", sync:"manual"},
    git:{status:"disconnected", provider:"GitHub", remoteUrl:"", branch:"main"}
  },
  profile:persisted.profile||{name:"", initials:"PX", role:"", bio:""},
  collections:persisted.collections||[],
  messages:{},
  notifications:[],
  journalModel:persisted.journalModel||{title:"",scope:"",reviewModel:"Open post-publication review",governance:""},
  journalTab:"published", registrationMode:"open",
  auth:{ready:false,authenticated:false,user:null,csrfToken:null}, authModal:null,
  people:[], activities:[], backendDiscussions:new Set(), backendSpaces:new Set(),
  toast:null
};
const app = document.getElementById("app");
let realtimeSocket=null;

function persistPrototype(){
  savePrototype({
    votes:[...state.votes], integrations:state.integrations,
    profile:state.profile, collections:state.collections, journalModel:state.journalModel,
    preferences:{sort:state.sort}
  });
}

function showToast(message, tone="success"){
  state.toast={message,tone};
  render();
  window.clearTimeout(showToast.timer);
  showToast.timer=window.setTimeout(()=>{state.toast=null;render()},2600);
}

function esc(value){return String(value??"").replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#39;")}
function icon(name){return `<i class="fa-solid fa-${name}" aria-hidden="true"></i>`}

async function apiRequest(path,options={}){
  const headers=new Headers(options.headers||{});
  const method=(options.method||"GET").toUpperCase();
  if(!["GET","HEAD","OPTIONS"].includes(method)&&state.auth.csrfToken&&!headers.has("X-CSRF-Token")){
    headers.set("X-CSRF-Token",state.auth.csrfToken);
  }
  const response=await fetch(`/api/v1${path}`,{credentials:"same-origin",...options,headers});
  let payload={};
  try{payload=await response.json()}catch{payload={}}
  if(!response.ok){
    const error=payload?.error;
    const exception=new Error(error?.message||error?.code||`Request failed with status ${response.status}`);
    exception.code=error?.code;exception.status=response.status;
    throw exception;
  }
  return payload;
}

function initials(name){return String(name||"PX").split(/\s+/).map(part=>part[0]).slice(0,2).join("").toUpperCase()}

function relativeTime(value){
  const elapsed=Math.max(0,Date.now()-new Date(value).getTime());
  const minutes=Math.floor(elapsed/60000);
  if(minutes<1)return "now";if(minutes<60)return `${minutes}m`;
  const hours=Math.floor(minutes/60);if(hours<24)return `${hours}h`;
  const days=Math.floor(hours/24);return `${days}d`;
}

function requireSignedIn(purpose="continue"){
  if(state.auth.authenticated)return true;
  state.authModal="login";
  state.notificationOpen=false;
  showToast(`Sign in to ${purpose}.`,"error");
  return false;
}

function applySession(payload){
  state.auth={
    ready:true,
    authenticated:Boolean(payload?.authenticated),
    user:payload?.user||null,
    csrfToken:payload?.csrf_token||null
  };
  if(payload?.user){
    state.profile={
      name:payload.user.display_name,
      initials:initials(payload.user.display_name),
      role:payload.user.role,
      bio:payload.user.bio||""
    };
  }
}

function messageFromBackend(record){
  return {
    id:record.id,
    direction:record.author_id===state.auth.user?.id?"outgoing":"incoming",
    content:record.body,
    createdAt:record.created_at
  };
}

function conversationFromBackend(record){
  const other=(record.participants||[]).find(person=>person.id!==state.auth.user?.id);
  return {
    id:record.id,
    name:other?.display_name||record.title||"Research conversation",
    preview:record.last_message?.body||"No messages yet",
    time:record.last_message?.created_at?relativeTime(record.last_message.created_at):relativeTime(record.created_at),
    unread:Number(record.unread_count)||0
  };
}

function upsertConversation(record){
  const mapped=conversationFromBackend(record);
  const index=conversations.findIndex(item=>item.id===mapped.id);
  if(index===-1)conversations.unshift(mapped);else conversations[index]={...conversations[index],...mapped};
  if(record.messages)state.messages[mapped.id]=record.messages.map(messageFromBackend);
  if(!state.conversation)state.conversation=mapped.id;
  return mapped;
}

function appendConversationMessage(record){
  const conversation=conversations.find(item=>item.id===record.conversation_id);
  if(!conversation)return;
  const messages=state.messages[record.conversation_id]||[];
  if(!messages.some(item=>item.id===record.id))messages.push(messageFromBackend(record));
  state.messages[record.conversation_id]=messages;
  conversation.preview=record.body;
  conversation.time=relativeTime(record.created_at);
  if(record.author_id!==state.auth.user?.id&&state.conversation!==record.conversation_id)conversation.unread+=1;
  const index=conversations.findIndex(item=>item.id===conversation.id);
  if(index>0)conversations.unshift(...conversations.splice(index,1));
}

async function loadConversation(conversationId){
  const payload=await apiRequest(`/social/conversations/${encodeURIComponent(conversationId)}/messages`);
  upsertConversation(payload.conversation);
  state.messages[conversationId]=(payload.results||[]).map(messageFromBackend);
  const conversation=conversations.find(item=>item.id===conversationId);
  if(conversation)conversation.unread=0;
  await apiRequest(`/social/conversations/${encodeURIComponent(conversationId)}/read`,{method:"POST"});
  realtimeSocket?.emit("conversation.join",{conversation_id:conversationId});
}

async function refreshConversations(){
  if(!state.auth.authenticated)return;
  const payload=await apiRequest("/social/conversations");
  conversations.splice(0,conversations.length);
  for(const record of payload.results||[])upsertConversation(record);
  if(conversations.length&&!conversations.some(item=>item.id===state.conversation))state.conversation=conversations[0].id;
  for(const conversation of conversations)realtimeSocket?.emit("conversation.join",{conversation_id:conversation.id});
}

function initializeRealtime(){
  realtimeSocket?.disconnect();
  realtimeSocket=null;
  if(!state.auth.authenticated||window.__PEERXIV_DISABLE_REALTIME__)return;
  realtimeSocket=io("/social",{withCredentials:true,transports:["websocket","polling"]});
  realtimeSocket.on("connect",()=>{
    for(const conversation of conversations)realtimeSocket.emit("conversation.join",{conversation_id:conversation.id});
  });
  realtimeSocket.on("conversation.created",record=>{
    const conversation=upsertConversation(record);
    realtimeSocket.emit("conversation.join",{conversation_id:conversation.id});
    render();
  });
  realtimeSocket.on("message.created",record=>{appendConversationMessage(record);render()});
  realtimeSocket.on("connect_error",error=>console.warn("PeerXiv realtime connection failed",error.message));
}

function discussionFromBackend(record){
  return {
    id:record.id,
    title:record.title,
    topic:record.topic,
    author:record.author?.display_name||"PeerXiv researcher",
    body:record.body,
    comments:Number(record.comment_count)||0,
    time:relativeTime(record.created_at),
    score:Number(record.score)||0,
    following:Boolean(record.following),
    saved:Boolean(record.saved),
    userVote:Number(record.viewer_vote)||0,
    linkedPaper:record.paper||null,
    replies:(record.comments||[]).map(comment=>({
      id:comment.id,
      author:comment.author?.display_name||"PeerXiv researcher",
      body:comment.body,
      time:relativeTime(comment.created_at),
      score:1
    }))
  };
}

function upsertDiscussion(record){
  const mapped=discussionFromBackend(record);
  const index=discussions.findIndex(item=>item.id===mapped.id);
  if(index===-1)discussions.unshift(mapped);else discussions[index]=mapped;
  state.backendDiscussions.add(mapped.id);
  if(state.selectedDiscussion?.id===mapped.id)state.selectedDiscussion=discussions.find(item=>item.id===mapped.id);
  return mapped;
}

function spaceFromBackend(record){
  const detail=record.details||{};
  const paper=record.papers?.[0]?.paper?.identifier||detail.paper||null;
  const common={id:record.id,backend:true,status:record.status,paper,updated:relativeTime(record.updated_at)};
  if(record.kind==="workspace")return {...common,name:record.title,members:record.members?.length||1,repository:detail.repository||"",overleaf:detail.overleaf||"",artifacts:record.resources?.length||0,resourceRecords:record.resources||[]};
  if(record.kind==="presentation")return {...common,title:record.title,speaker:detail.speaker||record.owner?.display_name||"PeerXiv researcher",format:detail.format||"Presentation",event:detail.event||"",slides:Number(detail.slides)||1};
  if(record.kind==="conference")return {...common,name:record.title,location:detail.location||"Online",dates:detail.dates||"Dates pending",deadline:detail.deadline||"Pending",topics:detail.topics||record.description,followed:true};
  return {...common,paper:detail.paper_title||record.title,journal:detail.journal||record.title,status:record.status,doi:detail.doi||"Pending"};
}

function upsertSpace(record){
  const mapped=spaceFromBackend(record);
  const collection=record.kind==="workspace"?workspaces:record.kind==="presentation"?presentations:record.kind==="conference"?conferences:journals;
  const index=collection.findIndex(item=>item.id===record.id);
  if(index===-1)collection.unshift(mapped);else collection[index]=mapped;
  state.backendSpaces.add(record.id);
  return mapped;
}

async function refreshAccountData(){
  if(!state.auth.authenticated)return;
  const [notificationPayload,peoplePayload,activityPayload]=await Promise.all([
    apiRequest("/accounts/notifications"),
    apiRequest("/accounts/people/recommendations"),
    apiRequest("/accounts/activity")
  ]);
  state.notifications=(notificationPayload.results||[]).map(item=>({
    ...item,time:relativeTime(item.created_at),
    paper:item.object_type==="paper"?item.object_id:null,
    discussion:item.object_type==="discussion"?item.object_id:null
  }));
  state.people=peoplePayload.results||[];
  state.activities=activityPayload.results||[];
}

async function refreshCommunityData(){
  const [paperPayload,discussionPayload,spacePayload]=await Promise.all([
    apiRequest("/papers"),
    apiRequest(`/social/discussions?filter=${encodeURIComponent(state.discussionFilter)}`),
    apiRequest("/spaces")
  ]);
  for(const record of paperPayload.results||[])upsertPaper(record);
  for(const record of discussionPayload.results||[])upsertDiscussion(record);
  for(const record of spacePayload.results||[])upsertSpace(record);
}

async function initializeFrontend(){
  try{
    const [bootstrapPayload,sessionPayload]=await Promise.all([
      apiRequest("/bootstrap"),
      apiRequest("/accounts/me")
    ]);
    state.registrationMode=bootstrapPayload.registration_mode||"open";
    applySession(sessionPayload);
    await Promise.all([refreshAccountData(),refreshCommunityData(),refreshConversations()]);
    initializeRealtime();
  }catch(error){
    state.auth.ready=true;
    console.warn("PeerXiv account bootstrap failed",error);
  }
  render();
  await routeFromHash();
  if(state.auth.authenticated)void refreshResearchNotifications();
}

function paperFromBackend(record){
  const version=record.versions?.at(-1);
  const metadata=version?.descriptive_metadata;
  const metadataTags=metadata?.tags||[];
  const visibleTags=[
    ...(record.tags||[]),
    ...metadataTags.filter(tag=>["method","concept"].includes(tag.facet)).slice(0,5).map(tag=>tag.label)
  ];
  return {
    id:record.identifier,
    title:record.title,
    authors:(record.authors||[]).join(", "),
    topic:record.subject||"Unclassified",
    code:record.subfield||"px.GEN",
    submitted:new Date(record.created_at).toLocaleDateString(undefined,{day:"numeric",month:"short",year:"numeric"}),
    time:"recently",
    version:`v${record.current_version||1}`,
    score:0,
    comments:0,
    citations:0,
    abstract:record.abstract,
    tags:[...new Set(visibleTags)],
    openReview:record.open_review,
    saved:false,
    status:record.status,
    license:record.license,
    createdAt:record.created_at,
    versions:record.versions||[],
    manuscript:version?.manuscript_uri?{name:`${record.identifier}.pdf`,stored:true}:null,
    pdfAvailable:Boolean(version?.manuscript_uri),
    pdfUrl:`/api/v1/papers/${encodeURIComponent(record.identifier)}/pdf`,
    metadataSummary:metadata?.summary||null,
    metadataTags
  };
}

function upsertPaper(record){
  const mapped=paperFromBackend(record);
  const index=papers.findIndex(item=>item.id===mapped.id);
  if(index===-1)papers.unshift(mapped);else papers[index]=mapped;
  return mapped;
}

function addNotificationMatches(matches=[]){
  let added=0;
  for(const match of matches){
    const sourceId=match.source?.id||"activity";
    const id=`match:${match.kind}:${match.paper}:${sourceId}`;
    if(state.notifications.some(item=>item.id===id)) continue;
    state.notifications.unshift({
      id,
      kind:match.kind,
      text:match.text,
      reason:match.reason,
      time:"now",
      read:false,
      paper:match.paper,
      score:match.score,
      matchedTags:match.matched_tags||[]
    });
    added+=1;
  }
  return added;
}

async function classifyActivityNotifications(sourceKind,title,text,sourceId){
  try{
    const payload=await apiRequest("/discovery/notifications/classify",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        source_kind:sourceKind,
        source_id:sourceId,
        title,
        text,
        exclude_identifiers:papers.filter(p=>p.authors.includes(state.profile.name)).map(p=>p.id),
        exclude_authors:[state.profile.name]
      })
    });
    const added=addNotificationMatches(payload.notifications);
    if(added){persistPrototype();render();showToast(`${added} research match${added===1?"":"es"} found from this ${sourceKind}.`)}
  }catch(error){console.warn("PeerXiv notification classification failed",error)}
}

async function refreshResearchNotifications(){
  const ownPapers=papers.filter(p=>p.authors.includes(state.profile.name)&&p.metadataTags?.length);
  for(const paper of ownPapers){
    try{
      const payload=await apiRequest("/discovery/notifications/matches",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
          source_kind:"research",
          source_id:paper.id,
          source_title:paper.title,
          tags:paper.metadataTags,
          exclude_identifiers:ownPapers.map(item=>item.id),
          exclude_authors:[state.profile.name]
        })
      });
      addNotificationMatches(payload.results);
    }catch(error){console.warn("PeerXiv research notification refresh failed",error)}
  }
  persistPrototype();
  render();
}

function filteredPapers(){
  const q=state.query.trim().toLowerCase();
  const results=papers.filter(p=>p.status!=="draft"&&(state.topic==="All topics"||p.topic===state.topic)&&(!q||[p.title,p.authors,p.abstract,p.topic,p.code,p.id,...p.tags].join(" ").toLowerCase().includes(q)));
  if(state.sort==="top") return [...results].sort((a,b)=>(b.score||0)-(a.score||0));
  if(state.sort==="discussed") return [...results].sort((a,b)=>(b.comments||0)-(a.comments||0));
  return results;
}

function leftNav(){
  return `${state.mobileNavOpen?`<button class="mobile-scrim fixed inset-0 z-40 bg-black/50 xl:hidden" data-action="close-mobile-nav" aria-label="Close navigation"></button>`:""}<aside class="left-nav fixed inset-y-0 left-0 z-50 w-[17rem] overflow-y-auto p-4 xl:sticky xl:top-16 xl:z-10 xl:h-[calc(100vh-4rem)] xl:w-auto ${state.mobileNavOpen?"mobile-open":""}">
    <div class="mobile-nav-heading flex items-center justify-between pb-4 xl:hidden"><strong>Browse PeerXiv</strong><button data-action="close-mobile-nav" aria-label="Close navigation">${icon("xmark")}</button></div>
    <button class="left-home ${state.page==="home"?"active":""}" data-page="home">${icon("house")} Home <small>Recent</small></button>
    <section class="explore-section">
      <button class="tree-root ${state.page==="topic"?"active":""}" data-action="toggle-explore">${icon("compass")}<b>Explore</b><i class="fa-solid fa-chevron-${state.exploreOpen?"down":"right"}"></i></button>
      ${state.exploreOpen?`<div class="tree-branch">
        <div class="tree-label"><span>Topic communities</span><button aria-label="Add topic">${icon("plus")}</button></div>
        <button class="topic-link ${state.topic==="All topics"&&state.page==="topic"?"active":""}" data-topic="All topics"><span class="topic-mark all">PX</span><b>All research</b><small>${papers.filter(p=>p.status!=="draft").length}</small></button>
        ${topics.map(([name,code])=>`<button class="topic-link ${state.topic===name&&state.page==="topic"?"active":""}" data-topic="${name}"><span class="topic-mark">${code.split(".")[0].slice(0,2)}</span><span><b>${name}</b><em>${code}</em></span><small>${papers.filter(p=>p.status!=="draft"&&p.topic===name).length}</small></button>`).join("")}
        <button class="show-more">${icon("ellipsis")} More communities</button>
      </div>`:""}
    </section>
    <section class="spaces-tree">
      <button class="tree-root ${["spaces","workspaces","presentations","conferences","journals"].includes(state.page)?"active":""}" data-action="toggle-spaces">${icon("layer-group")}<b>Research spaces</b><i class="fa-solid fa-chevron-${state.spacesOpen?"down":"right"}"></i></button>
      ${state.spacesOpen?`<div class="tree-branch compact">
        <button class="sub-link ${state.page==="spaces"?"active":""}" data-page="spaces"><span class="branch-line"></span>${icon("table-cells-large")} Overview</button>
        <button class="sub-link ${state.page==="workspaces"?"active":""}" data-page="workspaces"><span class="branch-line"></span>${icon("cubes")} Workspaces</button>
        <button class="sub-link ${state.page==="presentations"?"active":""}" data-page="presentations"><span class="branch-line"></span>${icon("person-chalkboard")} Presentations</button>
        <button class="sub-link ${state.page==="conferences"?"active":""}" data-page="conferences"><span class="branch-line"></span>${icon("calendar-days")} Conferences</button>
        <button class="sub-link ${state.page==="journals"?"active":""}" data-page="journals"><span class="branch-line"></span>${icon("book-open")} Journals</button>
      </div>`:""}
    </section>
    <section class="discussion-tree">
      <button class="tree-root ${state.page==="discussions"?"active":""}" data-action="toggle-discussions">${icon("comments")}<b>Discussions</b><i class="fa-solid fa-chevron-${state.discussionsOpen?"down":"right"}"></i></button>
      ${state.discussionsOpen?`<div class="tree-branch compact">
        <button class="sub-link ${state.page==="discussions"&&state.discussionFilter==="active"?"active":""}" data-discussion-filter="active"><span class="branch-line"></span>${icon("fire")} Active</button>
        <button class="sub-link ${state.page==="discussions"&&state.discussionFilter==="new"?"active":""}" data-discussion-filter="new"><span class="branch-line"></span>${icon("clock")} New</button>
        <button class="sub-link ${state.page==="discussions"&&state.discussionFilter==="following"?"active":""}" data-discussion-filter="following"><span class="branch-line"></span>${icon("star")} Following</button>
        <button class="sub-link ${state.page==="discussions"&&state.discussionFilter==="saved"?"active":""}" data-discussion-filter="saved"><span class="branch-line"></span>${icon("bookmark")} Saved</button>
      </div>`:""}
    </section>
    <section class="utility-links">
      <button class="sub-link ${state.page==="library"?"active":""}" data-page="library">${icon("bookmark")} Library</button>
      <button class="sub-link ${state.page==="connections"?"active":""}" data-page="connections">${icon("user-group")} Connections</button>
    </section>
    <button class="sidebar-submit" data-action="upload">${icon("arrow-up-from-bracket")} Submit research</button>
    <footer><a>About</a><a>Guidelines</a><a>API</a><a>Help</a><span>© 2026 PeerXiv</span></footer>
  </aside>`;
}

function topNav(){
  const unread=state.notifications.filter(item=>!item.read).length;
  const messageUnread=conversations.reduce((total,item)=>total+(item.unread||0),0);
  return `<header class="top-nav sticky top-0 z-30 grid grid-cols-[auto_1fr_auto] items-center gap-2 px-3 py-2 md:h-16 md:grid-cols-[auto_minmax(12rem,1fr)_auto] md:gap-3 md:px-4 md:py-0 xl:grid-cols-[15rem_minmax(18rem,42rem)_auto] xl:gap-5 xl:px-6">
    <div class="brand-group flex items-center gap-2"><button class="mobile-menu inline-grid h-10 w-10 place-items-center rounded-lg xl:hidden" data-action="open-mobile-nav" aria-label="Open navigation">${icon("bars")}</button><button class="wordmark flex items-center gap-2" data-page="home"><span>PX</span><strong>PeerXiv</strong></button></div>
    <label class="site-search order-3 col-span-3 flex h-10 w-full items-center gap-2 rounded-lg px-3 md:order-none md:col-span-1">${icon("magnifying-glass")}<input class="min-w-0 flex-1" value="${esc(state.query)}" placeholder="Search papers, authors, topics, or identifiers"/><kbd class="hidden lg:inline">⌘ K</kbd></label>
    <nav class="user-actions flex items-center justify-end gap-1">
      <button class="submit-button" data-action="upload">${icon("plus")} Submit</button>
      <button class="top-action icon-only ${state.notificationOpen?"active":""}" data-action="toggle-notifications" aria-label="Notifications">${icon("bell")}${unread?`<b>${unread}</b>`:""}</button>
      <button class="top-action ${state.page==="messages"?"active":""}" data-page="messages">${icon("message")}<span>Messages</span>${messageUnread?`<b>${messageUnread}</b>`:""}</button>
      ${state.auth.authenticated?`<button class="user-menu" data-page="profile" aria-label="Open profile"><span class="avatar">${esc(state.profile.initials)}</span>${icon("chevron-down")}</button>`:`<button class="sign-in-button" data-action="open-auth">Sign in</button>`}
    </nav>
    ${state.notificationOpen?notificationPanel():""}
  </header>`;
}

function notificationPanel(){
  if(!state.auth.authenticated)return `<section class="notification-panel signed-out-panel"><header><h2>Notifications</h2></header><p>Sign in to receive relevant papers, replies, followed-researcher updates, and exact-subtopic matches.</p><button class="primary" data-action="open-auth">Sign in</button></section>`;
  return `<section class="notification-panel"><header><h2>Notifications</h2><button data-action="mark-notifications-read">Mark all read</button></header>${state.notifications.map(item=>`<button class="notification-item ${item.read?"":"unread"}" ${item.paper?`data-paper="${esc(item.paper)}"`:item.discussion?`data-notification-discussion="${esc(item.discussion)}"`:""} data-notification="${esc(item.id)}"><span></span><div><strong>${esc(item.text)}</strong>${item.reason?`<em>${esc(item.reason)}</em>`:""}<small>${esc(item.time)}</small></div></button>`).join("")||`<p>No notifications yet. Relevant research and community activity will appear here.</p>`}</section>`
}

function paperCard(p){
  const vote=state.votes.get(p.id)||0;
  const expanded=state.expandedAbstracts.has(p.id);
  return `<article class="paper-card grid grid-cols-[2.75rem_minmax(0,1fr)] overflow-hidden rounded-lg sm:grid-cols-[3.25rem_minmax(0,1fr)]" data-paper="${esc(p.id)}">
    <aside class="vote-rail"><button class="${vote===1?"voted":""}" data-vote="up" data-id="${esc(p.id)}" aria-label="Upvote">${icon("caret-up")}</button><strong>${Number(p.score||0)+vote}</strong><button class="${vote===-1?"voted down":""}" data-vote="down" data-id="${esc(p.id)}" aria-label="Downvote">${icon("caret-down")}</button></aside>
    <div class="paper-body">
      <div class="paper-kicker flex flex-wrap items-center gap-x-2 gap-y-1"><button data-topic="${esc(p.topic)}">${esc(p.code)}</button><span>${p.status==="draft"?"Saved":"Submitted"} ${esc(p.time)}</span><span>${esc(p.version)}</span>${p.status==="draft"?`<span class="draft-status">Draft</span>`:p.openReview?`<span class="review-status">Open review</span>`:""}</div>
      <h2>${esc(p.title)}</h2>
      <p class="authors">${esc(p.authors)}</p>
      <p class="abstract ${expanded?"expanded":""}">${esc(p.abstract)}</p>
      <button class="abstract-toggle" data-expand="${esc(p.id)}">${expanded?"Show less":"Read full abstract"}</button>
      <div class="tag-row">${p.tags.map(tag=>`<span>${esc(tag)}</span>`).join("")}</div>
      <footer class="flex items-center overflow-x-auto whitespace-nowrap">
        <button class="pdf-action" data-pdf="${esc(p.id)}">${icon("file-pdf")} PDF</button>
        <button data-paper="${esc(p.id)}">${icon("comment")} ${Number(p.comments||0)} comments</button>
        <button data-cite="${esc(p.id)}">${icon("quote-right")} ${Number(p.citations||0)} citations</button>
        <button class="${p.saved?"saved":""}" data-save="${esc(p.id)}">${icon("bookmark")} ${p.saved?"Saved":"Save"}</button>
        <button data-share="${esc(p.id)}">${icon("share-nodes")} Share</button>
      </footer>
    </div>
  </article>`;
}

function recentFeed(){
  const list=filteredPapers();
  return `<section class="feed-page">
    <header class="feed-header"><div><span class="eyebrow">PEERXIV FEED</span><h1>${state.topic==="All topics"?"Most recent research":state.topic}</h1><p>New and revised preprints, ordered by submission time.</p></div><div class="feed-controls"><button class="${state.sort==="new"?"active":""}" data-sort="new">New</button><button class="${state.sort==="top"?"active":""}" data-sort="top">Top</button><button class="${state.sort==="discussed"?"active":""}" data-sort="discussed">Discussed</button></div></header>
    <div class="feed-meta"><span><b>${list.length}</b> papers</span><button data-action="filters">${icon("sliders")} Filters</button></div>
    <div class="paper-list">${list.map(paperCard).join("")||`<div class="empty"><h2>No matching papers</h2><p>Try a different topic or search phrase.</p></div>`}</div>
  </section>`;
}

function rightRail(){return `<aside class="right-rail">
  <section class="side-card start-discussion"><h2>Start a discussion</h2><p>Ask a methodological question, challenge a result, or open a topic for collaborative review.</p><button data-action="new-discussion">Create discussion</button></section>
  ${state.auth.authenticated&&state.people.length?`<section class="side-card people-card"><div class="card-heading"><h2>People to follow</h2><button data-page="connections">See all</button></div>${state.people.slice(0,3).map(person=>`<article><span class="avatar">${esc(initials(person.display_name))}</span><div><strong>${esc(person.display_name)}</strong><small>${esc(person.reason)}</small></div><button class="connect ${person.following?"connected":""}" data-follow-person="${esc(person.id)}">${person.following?"Following":"Follow"}</button></article>`).join("")}</section>`:""}
  ${state.auth.authenticated&&state.activities.length?`<section class="side-card activity-card"><div class="card-heading"><h2>Network activity</h2></div>${state.activities.slice(0,4).map(item=>`<article><span class="avatar">${esc(initials(item.actor?.display_name))}</span><div><strong>${esc(item.summary)}</strong><small>${esc(relativeTime(item.created_at))}</small></div></article>`).join("")}</section>`:""}
  <section class="side-card"><div class="card-heading"><h2>Active discussions</h2><button data-page="discussions">See all</button></div>${discussions.slice(0,3).map(d=>`<button class="discussion-preview" data-discussion="${esc(d.id)}"><strong>${esc(d.title)}</strong><span>${esc(d.topic)} · ${d.comments} comments · ${esc(d.time)}</span></button>`).join("")}</section>
  <section class="side-card archive-stats"><h2>Archive status</h2><dl><div><dt>Published records</dt><dd>${papers.filter(p=>p.status!=="draft").length}</dd></div><div><dt>Revisions</dt><dd>${papers.filter(p=>p.version!=="v1").length}</dd></div><div><dt>Open reviews</dt><dd>${papers.filter(p=>p.openReview).length}</dd></div><div><dt>Discussions</dt><dd>${discussions.length}</dd></div></dl></section>
  </aside>`}

function homeLayout(){return `<div class="content-layout grid min-h-[calc(100vh-4rem)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[15rem_minmax(0,1fr)_18rem]">${leftNav()}<main class="center-column min-w-0 px-4 py-5 sm:px-6 md:py-7">${recentFeed()}</main>${rightRail()}</div>`}

function filteredDiscussions(){
  const list=state.discussionFilter==="following"?discussions.filter(d=>d.following):state.discussionFilter==="saved"?discussions.filter(d=>d.saved):[...discussions];
  return state.discussionFilter==="new"?[...list].reverse():[...list].sort((a,b)=>(b.score||0)-(a.score||0));
}

function discussionsPage(){
  const list=filteredDiscussions();
  const labels={active:"Active discussions",new:"Newest discussions",following:"Following",saved:"Saved discussions"};
  return `<div class="content-layout grid min-h-[calc(100vh-4rem)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[15rem_minmax(0,1fr)_18rem]">${leftNav()}<main class="center-column min-w-0 px-4 py-5 sm:px-6 md:py-7"><section class="feed-page"><header class="feed-header"><div><span class="eyebrow">COMMUNITY REVIEW</span><h1>${labels[state.discussionFilter]}</h1><p>Questions, critiques, replications, and open methodological conversations.</p></div><button class="primary" data-action="new-discussion">${icon("plus")} New discussion</button></header><div class="discussion-filter-bar"><button class="${state.discussionFilter==="active"?"active":""}" data-discussion-filter="active">Active</button><button class="${state.discussionFilter==="new"?"active":""}" data-discussion-filter="new">New</button><button class="${state.discussionFilter==="following"?"active":""}" data-discussion-filter="following">Following</button><button class="${state.discussionFilter==="saved"?"active":""}" data-discussion-filter="saved">Saved</button></div><div class="discussion-list">${list.map(d=>`<article data-discussion="${esc(d.id)}"><aside><button data-discussion-vote="${esc(d.id)}" data-direction="up" aria-label="Upvote discussion">${icon("caret-up")}</button><b>${d.score||0}</b><button data-discussion-vote="${esc(d.id)}" data-direction="down" aria-label="Downvote discussion">${icon("caret-down")}</button></aside><div><span>${esc(d.topic)} · ${esc(d.author)} · posted ${esc(d.time)} ago</span><h2>${esc(d.title)}</h2><p>${esc(d.body)}</p><footer><span>${icon("comment")} ${d.comments} comments</span><button data-discussion-follow="${esc(d.id)}">${icon("star")} ${d.following?"Following":"Follow"}</button><button data-discussion-save="${esc(d.id)}">${icon("bookmark")} ${d.saved?"Saved":"Save"}</button></footer></div></article>`).join("")||`<div class="empty"><h2>No discussions here yet</h2><p>Start one or change the current filter.</p></div>`}</div></section></main>${rightRail()}</div>`;
}

function messagesPage(){
  if(!conversations.length){
    return `<div class="messages-page grid min-h-[calc(100dvh-7rem)] grid-cols-1 md:min-h-[calc(100vh-4rem)] md:grid-cols-[22rem_minmax(0,1fr)]"><aside class="conversation-list"><header><span class="eyebrow">MESSAGES</span><h1>Inbox</h1><button data-action="new-message">${icon("pen-to-square")}</button></header><p class="empty-conversation">No conversations yet.</p></aside><section class="message-panel flex"><div class="empty-conversation"><h2>Start a research conversation</h2><p>Create a conversation before sharing papers or discussion links.</p><button class="primary" data-action="new-message">${icon("plus")} New conversation</button></div></section></div>`;
  }
  const active=conversations.find(item=>item.id===state.conversation)||conversations[0];
  const history=state.messages[active.id]||[];
  return `<div class="messages-page grid min-h-[calc(100dvh-7rem)] grid-cols-1 md:min-h-[calc(100vh-4rem)] md:grid-cols-[22rem_minmax(0,1fr)]"><aside class="conversation-list ${state.mobileConversationOpen?"hidden md:block":"block"}"><header><span class="eyebrow">MESSAGES</span><h1>Inbox</h1><button data-action="new-message">${icon("pen-to-square")}</button></header><label>${icon("magnifying-glass")}<input placeholder="Search conversations" data-conversation-search/></label>${conversations.map(c=>`<button class="conversation ${c.id===active.id?"active":""}" data-conversation="${esc(c.id)}"><span class="avatar">${esc(initials(c.name))}</span><span><strong>${esc(c.name)}</strong><small>${esc(c.preview)}</small></span><time>${esc(c.time)}${c.unread?`<b>${Number(c.unread)}</b>`:""}</time></button>`).join("")}</aside><section class="message-panel ${state.mobileConversationOpen?"flex":"hidden md:flex"}"><header><button class="message-back md:hidden" data-action="back-to-inbox" aria-label="Back to inbox">${icon("arrow-left")}</button><span class="avatar">${esc(initials(active.name))}</span><div><h2>${esc(active.name)}</h2><small>Persistent research conversation</small></div><button>${icon("ellipsis")}</button></header><div class="message-history"><div class="day">Messages</div>${history.map(message=>`<p class="bubble ${message.direction==="incoming"?"incoming":"outgoing"}">${esc(message.content)}</p>`).join("")||`<p class="empty-conversation">Start the research conversation.</p>`}</div><form class="message-composer" data-message-form data-conversation-id="${esc(active.id)}"><button type="button">${icon("paperclip")}</button><textarea name="message" required maxlength="10000" placeholder="Message ${esc(active.name)}"></textarea><button class="send" type="submit">${icon("paper-plane")}</button></form></section></div>`
}

function profilePage(){const orcid=state.integrations.orcid;const overleaf=state.integrations.overleaf;const git=state.integrations.git;return `<div class="simple-page mx-auto max-w-5xl px-4 py-7 sm:px-6 md:py-12"><span class="eyebrow">RESEARCHER PROFILE</span><div class="profile-heading"><span class="avatar large">${esc(state.profile.initials)}</span><div><div class="identity-line"><h1>${esc(state.profile.name)}</h1>${orcid.status==="configured"?`<span class="orcid-verified"><i class="fa-brands fa-orcid"></i> ${esc(orcid.identifier)}</span>`:""}</div><p>${esc(state.profile.role)} · ${esc(state.profile.bio)}</p></div><div class="profile-actions"><button data-action="edit-profile">Edit profile</button>${state.auth.authenticated?`<button data-action="logout">Sign out</button>`:""}</div></div><div class="profile-stats grid grid-cols-2 gap-2 md:grid-cols-4"><div><b>${papers.filter(p=>p.authors.includes(state.profile.name)).length}</b><span>Preprints</span></div><div><b>${papers.filter(p=>p.authors.includes(state.profile.name)).reduce((sum,p)=>sum+(p.citations||0),0)}</b><span>Citations</span></div><div><b>${state.people.filter(r=>r.following).length}</b><span>Following</span></div><div><b>${discussions.filter(d=>d.author===state.profile.name).length}</b><span>Discussions</span></div></div><section class="integrations-section"><header><div><span class="eyebrow">CONNECTED SERVICES</span><h2>Research integrations</h2></div><p>These provider settings are still stored in this browser; authenticated OAuth, verification, and synchronization are the next integration phase.</p></header><div class="integration-grid"><article class="${orcid.status}"><span class="integration-logo orcid-logo"><i class="fa-brands fa-orcid"></i></span><div><h3>ORCID</h3><p>${esc(orcid.status==="configured"?(orcid.identifier||"Identity configuration saved locally."):"Verify identity and import authorship records.")}</p></div><button data-integration="orcid">${orcid.status==="configured"?"Manage":"Configure"}</button></article><article class="${overleaf.status}"><span class="integration-logo overleaf-logo">TeX</span><div><h3>Overleaf</h3><p>${esc(overleaf.status==="configured"?(overleaf.projectName||"Project configuration saved locally."):"Import manuscripts and synchronize submission drafts.")}</p></div><button data-integration="overleaf">${overleaf.status==="configured"?"Manage":"Configure"}</button></article><article class="${git.status}"><span class="integration-logo git-logo">${icon("code-branch")}</span><div><h3>Git</h3><p>${esc(git.status==="configured"?(git.remoteUrl||"Repository configuration saved locally."):"Attach repositories, releases, and commit provenance.")}</p></div><button data-integration="git">${git.status==="configured"?"Manage":"Configure"}</button></article></div></section><h2>Network activity</h2><div class="profile-activity">${state.activities.slice(0,8).map(item=>`<article><span class="avatar">${esc(initials(item.actor?.display_name))}</span><div><b>${esc(item.summary)}</b><small>${esc(relativeTime(item.created_at))}</small></div></article>`).join("")||`<p>Your submissions, discussions, follows, and Research Space changes will appear here.</p>`}</div><h2>Recent submissions</h2><div class="paper-list">${papers.filter(p=>p.authors.includes(state.profile.name)&&p.status!=="draft").map(paperCard).join("")}</div></div>`}

function libraryPage(){const saved=papers.filter(p=>p.saved||p.status==="draft");return `<div class="content-layout grid min-h-[calc(100vh-4rem)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[15rem_minmax(0,1fr)_18rem]">${leftNav()}<main class="center-column min-w-0 px-4 py-5 sm:px-6 md:py-7"><section class="feed-page"><header class="feed-header"><div><span class="eyebrow">YOUR LIBRARY</span><h1>Saved research & drafts</h1><p>Papers, submission drafts, and research threads you want to return to.</p></div></header><div class="collection-row">${state.collections.map(name=>`<span>${icon("folder")} ${esc(name)}</span>`).join("")}<button data-action="new-collection">${icon("folder-plus")} New collection</button></div><div class="feed-meta"><span><b>${saved.length}</b> records</span></div><div class="paper-list">${saved.map(paperCard).join("")||`<div class="empty"><h2>Your library is empty</h2><p>Save a paper or create a submission draft to keep it here.</p></div>`}</div></section></main>${rightRail()}</div>`}

function connectionsPage(){
  const visible=state.auth.authenticated&&state.people.length?state.people.map(person=>({id:person.id,name:person.display_name,initials:initials(person.display_name),role:person.role,organization:person.shared_interests?.join(" · ")||"PeerXiv",areas:person.reason,connected:person.following})):researchers;
  return `<div class="content-layout grid min-h-[calc(100vh-4rem)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[15rem_minmax(0,1fr)_18rem]">${leftNav()}<main class="center-column min-w-0 px-4 py-5 sm:px-6 md:py-7"><section class="feed-page"><header class="feed-header"><div><span class="eyebrow">RESEARCH NETWORK</span><h1>People to follow</h1><p>Suggestions are ranked by overlapping CoU-derived topics and methods, then by new researchers.</p></div></header>${!state.auth.authenticated?`<div class="auth-callout"><h2>Build your research network</h2><p>Sign in to get relevant people recommendations and a feed of their actions.</p><button class="primary" data-action="open-auth">Sign in</button></div>`:""}<div class="researcher-grid grid grid-cols-1 gap-3 lg:grid-cols-2">${visible.map(r=>`<article class="researcher-card"><span class="avatar large">${esc(r.initials)}</span><div><h2>${esc(r.name)}</h2><p>${esc(r.role)}</p><small>${esc(r.organization)}</small><span>${esc(r.areas)}</span></div><button class="connect ${r.connected?"connected":""}" ${r.id?`data-follow-person="${esc(r.id)}"`:`data-connect="${esc(r.name)}"`}>${r.connected?"Following":"Follow"}</button></article>`).join("")}</div></section></main>${rightRail()}</div>`
}

function spaceLayout(eyebrow,title,description,content,action="") { return `<div class="content-layout grid min-h-[calc(100vh-4rem)] grid-cols-1 lg:grid-cols-[minmax(0,1fr)_18rem] xl:grid-cols-[15rem_minmax(0,1fr)_18rem]">${leftNav()}<main class="center-column min-w-0 px-4 py-5 sm:px-6 md:py-7"><section class="feed-page"><header class="feed-header"><div><span class="eyebrow">${eyebrow}</span><h1>${title}</h1><p>${description}</p></div>${action}</header>${content}</section></main>${rightRail()}</div>`; }

function spacesHubPage(){
  const cards=[
    ["workspaces","cubes","Workspaces",workspaces.length,"Coordinate papers, source, artifacts, and collaborators."],
    ["presentations","person-chalkboard","Presentations",presentations.length,"Connect talks, posters, and briefings to the research record."],
    ["conferences","calendar-days","Conferences",conferences.length,"Track calls, deadlines, communities, and proceedings."],
    ["journals","book-open","Journals",journals.length,"Preserve relationships between preprints and published versions."]
  ];
  const activity=[
    workspaces[0]&&`<li><b>${esc(workspaces[0].name)}</b><span>Workspace updated ${esc(workspaces[0].updated||"recently")}</span></li>`,
    presentations[0]&&`<li><b>${esc(presentations[0].title)}</b><span>Presentation linked to ${esc(presentations[0].paper||"no paper")}</span></li>`,
    conferences[0]&&`<li><b>${esc(conferences[0].name)}</b><span>Submission deadline ${esc(conferences[0].deadline||"not set")}</span></li>`
  ].filter(Boolean);
  return spaceLayout("CONNECTED SCHOLARSHIP","Research Spaces","Move from a paper into the active work, communication, events, and publication relationships surrounding it.",`<div class="space-hub">${cards.map(([page,iconName,title,count,description])=>`<button data-page="${page}"><span>${icon(iconName)}</span><small>${count} records</small><h2>${title}</h2><p>${description}</p><b>Open ${title.toLowerCase()} ${icon("arrow-right")}</b></button>`).join("")}</div>${activity.length?`<section class="space-activity"><div><span class="eyebrow">RECENT SPACE ACTIVITY</span><h2>Research stays connected to its context</h2></div><ul>${activity.join("")}</ul></section>`:`<div class="empty"><h2>No Research Spaces yet</h2><p>Create a workspace, presentation, conference, or journal relationship to begin.</p></div>`}`);
}

function workspacesPage(){return spaceLayout("CONNECTED RESEARCH","Workspaces","Coordinate the paper, manuscript, code, artifacts, presentations, and collaborators without breaking provenance.",`<div class="workspace-list">${workspaces.map((w,index)=>`<article class="workspace-card"><header><div><span>${esc(w.status)}</span><h2>${esc(w.name)}</h2></div><button>${icon("ellipsis")}</button></header><button class="linked-paper" data-paper="${esc(w.paper)}">${icon("file-lines")} Linked paper <b>${esc(w.paper||"Not linked")}</b>${icon("arrow-right")}</button><div class="workspace-connections"><span>${icon("code-branch")} Git <b>${esc(w.repository||"Not connected")}</b></span><span>${icon("file-pen")} Overleaf <b>${esc(w.overleaf||"Not connected")}</b></span><span>${icon("box-archive")} Artifacts <b>${Number(w.artifacts||0)}</b></span></div><footer><span>${icon("user-group")} ${Number(w.members||1)} collaborators</span><span>Updated ${esc(w.updated||"just now")}</span><button data-workspace="${index}">Open workspace</button></footer></article>`).join("")||`<div class="empty"><h2>No workspaces yet</h2><p>Create the first workspace and connect it to a paper when ready.</p></div>`}</div>`,`<button class="primary" data-action="new-workspace">${icon("plus")} New workspace</button>`)}

function presentationsPage(){return spaceLayout("RESEARCH COMMUNICATION","Presentations","Slide decks, seminars, posters, and recorded talks connected directly to their research records.",`<div class="presentation-grid">${presentations.map((p,index)=>`<article class="presentation-card"><div class="slide-preview"><span>PX</span>${icon("person-chalkboard")}</div><div><span>${esc(p.format)} · ${p.slides} slides</span><h2>${esc(p.title)}</h2><p>${esc(p.speaker)} · ${esc(p.event)}</p><button data-paper="${p.paper}">${icon("link")} ${esc(p.paper)}</button></div><footer><button data-presentation-open="${index}">${icon("play")} Open</button><button data-presentation-export="${index}">${icon("download")} Export metadata</button><button data-action="new-discussion" data-linked-paper="${esc(p.paper)}">${icon("comment")} Discuss</button></footer></article>`).join("")||`<div class="empty"><h2>No presentations yet</h2><p>Add a talk, poster, or briefing when one is ready.</p></div>`}</div>`,`<button class="primary" data-action="new-presentation">${icon("plus")} Add presentation</button>`)}

function conferencesPage(){return spaceLayout("EVENTS & PROCEEDINGS","Conferences","Discover calls for papers, follow event communities, and connect proceedings to PeerXiv research records.",`<div class="conference-list">${conferences.map((c,i)=>`<article class="conference-card"><div class="conference-date"><b>${esc(c.dates.split(" ")[0])}</b><span>${esc(c.dates.split(" ")[1]||"")}</span></div><div><span>SUBMISSIONS CLOSE ${esc(c.deadline.toUpperCase())}</span><h2>${esc(c.name)}</h2><p>${icon("location-dot")} ${esc(c.location)}</p><small>${esc(c.topics)}</small></div><footer><button data-conference-open="${i}">View conference</button><button class="${c.followed?"followed":""}" data-conference-follow="${i}">${icon("bookmark")} ${c.followed?"Following":"Follow"}</button></footer></article>`).join("")||`<div class="empty"><h2>No conferences yet</h2><p>Add an event to track its call, deadline, and related research.</p></div>`}</div>`,`<button class="primary" data-action="new-conference">${icon("plus")} Add conference</button>`)}

function journalsPage(){const directory=`<div class="empty"><h2>No journal directory entries yet</h2><p>Journal records will appear after they are added and verified.</p></div>`;const concept=`<div class="journal-list"><article class="journal-concept"><span>CONCEPT SPACE</span><h2>${esc(state.journalModel.title||"Journal model not defined")}</h2><p>${esc(state.journalModel.scope||"Define the editorial model, review standards, governance, and journal identity before submissions are accepted.")}</p><dl><div><dt>Review model</dt><dd>${esc(state.journalModel.reviewModel)}</dd></div><div><dt>Governance</dt><dd>${esc(state.journalModel.governance||"Not defined")}</dd></div></dl><button data-action="define-journal">Define the journal model</button></article></div>`;const published=`<div class="journal-list">${journals.map((j,index)=>`<article class="journal-card"><span>${esc(j.status)}</span><h2>${esc(j.paper)}</h2><p>${esc(j.journal)}</p><dl><div><dt>DOI</dt><dd>${esc(j.doi)}</dd></div><div><dt>Relationship</dt><dd>Preprint → published record</dd></div></dl><button data-journal-open="${index}">View publication relationship</button></article>`).join("")||`<div class="empty"><h2>No published relationships yet</h2><p>Link a journal version to a PeerXiv paper when one exists.</p></div>`}</div>`;return spaceLayout("PUBLISHED RESEARCH","Journals","Connect preprints to peer-reviewed versions, browse journal destinations, and preserve the publication relationship.",`<div class="journal-tabs"><button class="${state.journalTab==="published"?"active":""}" data-journal-tab="published">Published versions</button><button class="${state.journalTab==="directory"?"active":""}" data-journal-tab="directory">Journal directory</button><button class="${state.journalTab==="concept"?"active":""}" data-journal-tab="concept">PeerXiv Journal <small>Concept</small></button></div>${state.journalTab==="directory"?directory:state.journalTab==="concept"?concept:published}`,`<button class="primary" data-action="link-publication">${icon("link")} Link published version</button>`)}

function paperDetail(p){
  const metadata=(p.metadataTags||[]).filter(tag=>tag.facet!=="concept").slice(0,10);
  const linkedDiscussions=discussions.filter(d=>d.linkedPaper===p.id);
  const threadCount=linkedDiscussions.length;
  const versionHistory=(p.versions||[{number:Number(String(p.version||"v1").replace(/^v/,""))||1,created_at:p.createdAt||null}])
    .slice().reverse();
  return `<div class="paper-detail mx-auto max-w-6xl px-4 py-7 sm:px-6 md:py-10">
    <button class="back" data-action="back">${icon("arrow-left")} Back to feed</button>
    <div class="detail-grid grid grid-cols-1 gap-7 xl:grid-cols-[minmax(0,1fr)_18rem] xl:gap-12">
      <main class="min-w-0">
        <div class="paper-kicker flex flex-wrap gap-2"><button data-topic="${esc(p.topic)}">${esc(p.code)}</button><span>${esc(p.id)}</span><span>${esc(p.version)}</span><span>${esc(p.submitted)}</span></div>
        <h1>${esc(p.title)}</h1>
        <p class="detail-authors">${esc(p.authors)}</p>
        <div class="detail-actions flex flex-wrap gap-2"><button class="primary" data-pdf="${esc(p.id)}">${icon("file-pdf")} View PDF</button><button data-save="${esc(p.id)}">${icon("bookmark")} ${p.saved?"Saved":"Save"}</button><button data-cite="${esc(p.id)}">${icon("quote-right")} Cite</button><button data-share="${esc(p.id)}">${icon("share-nodes")} Share</button></div>
        <h2>Abstract</h2>
        <p class="full-abstract">${esc(p.abstract)}</p>
        <div class="tag-row">${p.tags.map(t=>`<span>${esc(t)}</span>`).join("")}</div>
        ${p.metadataSummary?`<section class="cou-metadata"><span class="eyebrow">COU DESCRIPTIVE METADATA</span><h2>${esc(p.metadataSummary)}</h2><div>${metadata.map(tag=>`<article title="${esc(tag.description)}"><small>${esc(tag.facet)}</small><b>${esc(tag.label)}</b><span>${esc(tag.state)} · ${Number(tag.weight).toFixed(3)}</span></article>`).join("")}</div></section>`:""}
        <section class="discussion-section">
          <header><h2>Discussion</h2><span>${threadCount} ${threadCount===1?"thread":"threads"}</span><button class="primary" data-action="new-discussion">Start a thread</button></header>
          ${threadCount?`<div class="linked-thread-list"><span class="eyebrow">LINKED THREADS</span>${linkedDiscussions.map(d=>`<button data-discussion="${esc(d.id)}"><b>${esc(d.title)}</b><small>${d.comments} replies · ${esc(d.topic)}</small>${icon("arrow-right")}</button>`).join("")}</div>`:`<div class="empty"><h2>No discussion yet</h2><p>Start the first evidence-based discussion for this paper.</p></div>`}
          <form class="comment-composer" data-comment-form data-paper-id="${esc(p.id)}"><textarea name="comment" required minlength="20" maxlength="20000" placeholder="Add a substantive comment; PeerXiv will retain it as a linked discussion and find related research."></textarea><button class="primary" type="submit">Post comment</button></form>
        </section>
      </main>
      <aside>
        <section class="side-card record-card"><h2>Research record</h2><dl><div><dt>Identifier</dt><dd>${esc(p.id)}</dd></div><div><dt>Current version</dt><dd>${esc(p.version)}</dd></div><div><dt>Open review</dt><dd>${p.openReview?"Enabled":"Limited"}</dd></div><div><dt>License</dt><dd>${esc(p.license||"CC BY 4.0")}</dd></div><div><dt>Artifacts</dt><dd>${p.manuscript?"Manuscript PDF":"No PDF attached"}</dd></div><div><dt>Classification</dt><dd>${esc(p.topic)} · ${esc(p.code)}</dd></div></dl></section>
        <section class="side-card vote-large"><span>Community score</span><div><button data-vote="up" data-id="${esc(p.id)}">${icon("caret-up")}</button><b>${p.score+(state.votes.get(p.id)||0)}</b><button data-vote="down" data-id="${esc(p.id)}">${icon("caret-down")}</button></div></section>
        <section class="side-card"><h2>Version history</h2>${versionHistory.map(version=>`<div class="version"><b>v${Number(version.number)||1}</b><span>${Number(version.number)===(Number(String(p.version).replace(/^v/,""))||1)?"Current revision":"Earlier revision"}</span><small>${esc(version.created_at?new Date(version.created_at).toLocaleDateString():p.submitted)}</small></div>`).join("")}</section>
      </aside>
    </div>
  </div>`;
}

function uploadModal(){return `<div class="modal-layer fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/60 p-3 sm:p-6"><form class="upload-modal relative my-auto w-full max-w-xl overflow-y-auto rounded-xl p-5 sm:p-8" data-submission-form><button type="button" class="close" data-action="close-upload">${icon("xmark")}</button><span class="eyebrow">NEW RESEARCH RECORD</span><h2>Submit a preprint</h2><p>Create a durable draft or publish a classified research record. The CoU classifier assigns the subject, subtopics, methods, contribution type, evidence profile, and descriptive metadata automatically.</p><div class="classification-note">${icon("diagram-project")} <span><b>No manual category required</b><small>Classification runs when the paper is published and retains its evidence and validation trace.</small></span></div><div class="import-actions"><button type="button" data-integration="overleaf"><span class="integration-mini overleaf-logo">TeX</span> Import from Overleaf</button><button type="button" data-integration="orcid"><span class="integration-mini orcid-logo"><i class="fa-brands fa-orcid"></i></span> Add authors from ORCID</button><button type="button" data-integration="git"><span class="integration-mini git-logo">${icon("code-branch")}</span> Attach Git repository</button></div><label>Paper title<input name="title" required maxlength="500" placeholder="Full research title"/></label><label>Authors<input name="authors" required placeholder="Comma-separated author names"/></label><label>Abstract<textarea name="abstract" required maxlength="50000" placeholder="Problem, method, results, and contribution"></textarea></label><label>Author keywords<input name="tags" placeholder="uncertainty, validation, distributed systems"/></label><label>Section excerpts <small>Optional, separate sections with a blank line</small><textarea name="sections" maxlength="100000" placeholder="Methods, findings, or other text that should inform classification"></textarea></label><label class="file-drop">${icon("cloud-arrow-up")}<b>Choose manuscript PDF</b><span>Required to publish; optional for a draft</span><input name="manuscript" type="file" accept="application/pdf,.pdf"/></label><label>Connect to workspace<select name="workspace"><option value="">No workspace</option>${workspaces.map((w,index)=>`<option value="${index}">${esc(w.name)}</option>`).join("")}</select></label><footer><button type="button" data-action="close-upload">Cancel</button><button type="submit" name="intent" value="draft">Save draft</button><button class="primary" type="submit" name="intent" value="publish">Classify & publish</button></footer></form></div>`}

function integrationDialog(){
  const kind=state.integrationModal;
  if(!kind) return "";
  const current=state.integrations[kind];
  const fields=kind==="orcid"?`<label>ORCID iD<input name="identifier" value="${esc(current.identifier)}" placeholder="0000-0000-0000-0000" required/></label><label>Record visibility<select name="visibility"><option ${current.visibility==="public"?"selected":""}>public</option><option ${current.visibility==="limited"?"selected":""}>limited</option></select></label>`:kind==="overleaf"?`<label>Project name<input name="projectName" value="${esc(current.projectName)}" required placeholder="Research manuscript"/></label><label>Overleaf project URL<input name="projectUrl" value="${esc(current.projectUrl)}" required placeholder="https://www.overleaf.com/project/..."/></label><label>Synchronization<select name="sync"><option value="manual" ${current.sync==="manual"?"selected":""}>Manual import</option><option value="requested" ${current.sync==="requested"?"selected":""}>Request automatic sync when backend is available</option></select></label>`:`<label>Provider<select name="provider"><option ${current.provider==="GitHub"?"selected":""}>GitHub</option><option ${current.provider==="GitLab"?"selected":""}>GitLab</option><option ${current.provider==="Other"?"selected":""}>Other</option></select></label><label>Repository remote<input name="remoteUrl" value="${esc(current.remoteUrl)}" required placeholder="https://github.com/org/repository.git"/></label><label>Default branch<input name="branch" value="${esc(current.branch)}" required placeholder="main"/></label>`;
  const titles={orcid:"Configure ORCID",overleaf:"Configure Overleaf",git:"Configure Git repository"};
  return `<div class="modal-layer integration-layer fixed inset-0 z-[60] grid place-items-center overflow-y-auto bg-black/60 p-3"><form class="upload-modal workflow-dialog relative w-full max-w-xl rounded-xl p-5 sm:p-8" data-integration-form data-kind="${kind}"><button type="button" class="close" data-action="close-integration">${icon("xmark")}</button><span class="eyebrow">CONNECTED SERVICE</span><h2>${titles[kind]}</h2><p>This configuration is persisted locally. OAuth, remote verification, synchronization, and webhooks require the backend.</p>${fields}<div class="backend-boundary">${icon("shield-halved")} No credentials or access tokens are requested or stored.</div><footer>${current.status==="configured"?`<button type="button" class="danger" data-action="disconnect-integration" data-kind="${kind}">Remove configuration</button>`:""}<button type="button" data-action="close-integration">Cancel</button><button class="primary" type="submit">Save configuration</button></footer></form></div>`;
}

function workflowDialog(){
  const type=state.workflowModal;
  if(!type) return "";
  const dialogs={
    workspace:{title:"Create workspace",eyebrow:"CONNECTED RESEARCH",fields:`<label>Workspace name<input name="name" required placeholder="Project or research program"/></label><label>Linked paper<select name="paper"><option value="">No paper yet</option>${papers.map(p=>`<option value="${esc(p.id)}">${esc(p.title)}</option>`).join("")}</select></label><label>Git repository<input name="repository" placeholder="https://github.com/org/repository.git"/></label><label>Overleaf project<input name="overleaf" placeholder="Project name or URL"/></label><label>Collaborators<input name="members" type="number" min="1" value="1"/></label>`,form:"workspace"},
    discussion:{title:"Start a discussion",eyebrow:"COMMUNITY REVIEW",fields:`<label>Title<input name="title" required placeholder="Question or claim to discuss"/></label><label>Topic<select name="topic">${topics.map(([name])=>`<option>${name}</option>`).join("")}</select></label><label>Linked paper <small>Optional</small><select name="paper"><option value="">General discussion</option>${papers.filter(p=>p.status!=="draft").map(p=>`<option value="${esc(p.id)}" ${(state.discussionContext||state.selectedPaper?.id)===p.id?"selected":""}>${esc(p.title)}</option>`).join("")}</select></label><label>Opening statement<textarea name="body" required minlength="20" maxlength="20000" placeholder="Give readers enough context to respond substantively."></textarea></label>`,form:"discussion"},
    conference:{title:"Add conference",eyebrow:"EVENTS & PROCEEDINGS",fields:`<label>Conference name<input name="name" required/></label><div class="form-row grid grid-cols-1 gap-3 sm:grid-cols-2"><label>Dates<input name="dates" required placeholder="Oct 14–16, 2026"/></label><label>Submission deadline<input name="deadline" required placeholder="Aug 28"/></label></div><label>Location<input name="location" required placeholder="City or Online"/></label><label>Topics<input name="topics" required placeholder="AI · Open science"/></label>`,form:"conference"},
    publication:{title:"Link published version",eyebrow:"JOURNAL RELATIONSHIP",fields:`<label>PeerXiv paper<select name="paper">${papers.filter(p=>p.status!=="draft").map(p=>`<option>${esc(p.title)}</option>`).join("")}</select></label><label>Journal<input name="journal" required/></label><label>DOI<input name="doi" required placeholder="10.xxxx/..."/></label><label>Status<select name="status"><option>Published version linked</option><option>Accepted</option><option>Under review</option></select></label>`,form:"publication"},
    filters:{title:"Filter research",eyebrow:"FEED CONTROLS",fields:`<label>Topic<select name="topic"><option>All topics</option>${topics.map(([name])=>`<option ${state.topic===name?"selected":""}>${name}</option>`).join("")}</select></label><label>Sort order<select name="sort"><option value="new" ${state.sort==="new"?"selected":""}>Newest</option><option value="top" ${state.sort==="top"?"selected":""}>Top score</option><option value="discussed" ${state.sort==="discussed"?"selected":""}>Most discussed</option></select></label>`,form:"filters"},
    message:{title:"New conversation",eyebrow:"MESSAGES",fields:`<label>Recipient email<input name="recipient" type="email" required autocomplete="email" placeholder="researcher@example.org"/></label><label>First message<textarea name="message" required maxlength="10000"></textarea></label>`,form:"message"},
    profile:{title:"Edit profile",eyebrow:"RESEARCHER PROFILE",fields:`<label>Name<input name="name" required value="${esc(state.profile.name)}"/></label><label>Role<input name="role" required value="${esc(state.profile.role)}"/></label><label>Research focus<textarea name="bio" required>${esc(state.profile.bio)}</textarea></label>`,form:"profile"},
    collection:{title:"Create collection",eyebrow:"YOUR LIBRARY",fields:`<label>Collection name<input name="name" required placeholder="e.g. Replication candidates"/></label>`,form:"collection"},
    artifact:{title:"Register artifact",eyebrow:"RESEARCH PROVENANCE",fields:`<label>Artifact name<input name="name" required placeholder="Dataset, code release, notebook…"/></label><label>Artifact URL<input name="url" required placeholder="https://…"/></label><label>Type<select name="type"><option>Code</option><option>Dataset</option><option>Notebook</option><option>Protocol</option><option>Other</option></select></label>`,form:"artifact"},
    presentation:{title:"Add presentation",eyebrow:"RESEARCH COMMUNICATION",fields:`<label>Title<input name="title" required/></label><div class="form-row grid grid-cols-1 gap-3 sm:grid-cols-2"><label>Speaker<input name="speaker" required value="${esc(state.profile.name)}"/></label><label>Format<select name="format"><option>Conference talk</option><option>Seminar</option><option>Poster</option><option>Research briefing</option></select></label></div><label>Event<input name="event" required placeholder="Conference or seminar series"/></label><div class="form-row grid grid-cols-1 gap-3 sm:grid-cols-2"><label>Slide count<input name="slides" type="number" min="1" required/></label><label>Linked paper<select name="paper">${papers.filter(p=>p.status!=="draft").map(p=>`<option value="${esc(p.id)}">${esc(p.title)}</option>`).join("")}</select></label></div>`,form:"presentation"},
    journalModel:{title:"Define PeerXiv Journal",eyebrow:"EDITORIAL MODEL",fields:`<label>Journal title<input name="title" required value="${esc(state.journalModel.title)}"/></label><label>Scope<textarea name="scope" required minlength="20" placeholder="Research scope and editorial purpose">${esc(state.journalModel.scope)}</textarea></label><label>Review model<select name="reviewModel"><option ${state.journalModel.reviewModel==="Open post-publication review"?"selected":""}>Open post-publication review</option><option ${state.journalModel.reviewModel==="Transparent pre-publication review"?"selected":""}>Transparent pre-publication review</option><option ${state.journalModel.reviewModel==="Community review with editorial validation"?"selected":""}>Community review with editorial validation</option></select></label><label>Governance<textarea name="governance" required minlength="20" placeholder="Editors, conflicts, appeals, and community oversight">${esc(state.journalModel.governance)}</textarea></label>`,form:"journalModel"}
  };
  const dialog=dialogs[type];
  return `<div class="modal-layer fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-black/60 p-3"><form class="upload-modal workflow-dialog relative w-full max-w-xl rounded-xl p-5 sm:p-8" data-workflow-form="${dialog.form}"><button type="button" class="close" data-action="close-workflow">${icon("xmark")}</button><span class="eyebrow">${dialog.eyebrow}</span><h2>${dialog.title}</h2>${dialog.fields}<footer><button type="button" data-action="close-workflow">Cancel</button><button class="primary" type="submit">Save</button></footer></form></div>`;
}

function citationDialog(){
  const paper=paperById(state.citationPaper);
  if(!paper)return "";
  const formats=citationVariants(paper);
  const value=formats[state.citationStyle]||formats.apa;
  return `<div class="modal-layer fixed inset-0 z-[60] grid place-items-center overflow-y-auto bg-black/60 p-3"><section class="upload-modal citation-dialog relative w-full max-w-xl rounded-xl p-5 sm:p-8" role="dialog" aria-modal="true" aria-label="Cite ${esc(paper.title)}"><button type="button" class="close" data-action="close-citation">${icon("xmark")}</button><span class="eyebrow">CITATION EXPORT</span><h2>Cite this paper</h2><p>${esc(paper.title)}</p><nav>${Object.keys(formats).map(style=>`<button class="${state.citationStyle===style?"active":""}" data-citation-style="${style}">${style==="bibtex"?"BibTeX":style.toUpperCase()}</button>`).join("")}</nav><textarea readonly aria-label="Formatted citation">${esc(value)}</textarea><footer><button data-action="download-bibtex">${icon("download")} Download BibTeX</button><button class="primary" data-action="copy-citation">${icon("copy")} Copy ${state.citationStyle==="bibtex"?"BibTeX":state.citationStyle.toUpperCase()}</button></footer></section></div>`;
}

function shareDialog(){
  const target=state.shareTarget;
  if(!target)return "";
  const mailto=`mailto:?subject=${encodeURIComponent(target.title)}&body=${encodeURIComponent(`${target.text}\n\n${target.url}`)}`;
  return `<div class="modal-layer fixed inset-0 z-[60] grid place-items-center overflow-y-auto bg-black/60 p-3"><form class="upload-modal share-dialog relative w-full max-w-xl rounded-xl p-5 sm:p-8" data-share-form><button type="button" class="close" data-action="close-share">${icon("xmark")}</button><span class="eyebrow">SHARE ${esc(target.kind.toUpperCase())}</span><h2>${esc(target.title)}</h2><p>${esc(target.text)}</p><label>Permanent PeerXiv link<div class="share-link"><input readonly value="${esc(target.url)}"/><button type="button" data-action="copy-share-link">${icon("copy")} Copy</button></div></label><label>Send to a conversation<select name="conversation">${conversations.length?conversations.map(conversation=>`<option value="${esc(conversation.id)}">${esc(conversation.name)}</option>`).join(""):`<option disabled>No conversations available</option>`}</select></label><div class="share-options">${navigator.share?`<button type="button" data-action="native-share">${icon("share-from-square")} Device share</button>`:""}<a href="${esc(mailto)}">${icon("envelope")} Email</a></div><footer><button type="button" data-action="close-share">Cancel</button><button class="primary" type="submit" ${conversations.length?"":"disabled"}>${icon("message")} Send in Messages</button></footer></form></div>`;
}

function workspaceDetailPage(){
  const index=state.selectedWorkspace;
  const workspace=workspaces[index];
  if(!workspace){state.selectedWorkspace=null;return workspacesPage()}
  const linked=papers.find(p=>p.id===workspace.paper);
  const tabs=[["overview","Overview"],["source","Source & manuscripts"],["artifacts","Artifacts"],["activity","Activity"]];
  const panel=state.workspaceTab==="source"?`<div class="workspace-panel"><h2>Connected source</h2><div class="resource-row"><span class="integration-logo git-logo">${icon("code-branch")}</span><div><b>Git repository</b><p>${esc(workspace.repository||"No repository configured")}</p></div><button data-integration="git">${workspace.repository?"Manage":"Configure"}</button></div><div class="resource-row"><span class="integration-logo overleaf-logo">TeX</span><div><b>Overleaf manuscript</b><p>${esc(workspace.overleaf||"No project configured")}</p></div><button data-integration="overleaf">${workspace.overleaf?"Manage":"Configure"}</button></div></div>`:state.workspaceTab==="artifacts"?`<div class="workspace-panel"><h2>Artifacts</h2><p>${Number(workspace.artifacts||0)} artifacts are registered with this workspace.</p><button class="primary" data-action="add-artifact">${icon("plus")} Register artifact</button></div>`:state.workspaceTab==="activity"?`<div class="workspace-panel activity-list"><h2>Activity</h2><p><b>Workspace updated</b><span>${esc(workspace.updated||"just now")}</span></p><p><b>Paper relationship retained</b><span>${esc(workspace.paper||"No paper linked")}</span></p><p><b>Local prototype state saved</b><span>Browser storage</span></p></div>`:`<div class="workspace-panel"><h2>Research overview</h2>${linked?`<button class="linked-paper" data-paper="${esc(linked.id)}">${icon("file-lines")}<span><b>${esc(linked.title)}</b><small>${esc(linked.id)} · ${esc(linked.version)}</small></span>${icon("arrow-right")}</button>`:`<p>No paper is connected yet.</p>`}<div class="workspace-metrics"><div><b>${Number(workspace.members||1)}</b><span>Collaborators</span></div><div><b>${Number(workspace.artifacts||0)}</b><span>Artifacts</span></div><div><b>${workspace.repository?1:0}</b><span>Repositories</span></div></div></div>`;
  return `<div class="workspace-detail mx-auto max-w-6xl px-4 py-7 sm:px-6"><button class="back" data-action="back-workspaces">${icon("arrow-left")} All workspaces</button><header><span class="eyebrow">${esc(workspace.status||"ACTIVE")} WORKSPACE</span><h1>${esc(workspace.name)}</h1><p>Linked research, source, manuscripts, artifacts, and provenance in one working context.</p></header><nav>${tabs.map(([id,label])=>`<button class="${state.workspaceTab===id?"active":""}" data-workspace-tab="${id}">${label}</button>`).join("")}</nav>${panel}</div>`;
}

function discussionDetailPage(){
  const discussion=state.selectedDiscussion;
  if(!discussion){return discussionsPage()}
  const initials=discussion.author.split(/\s+/).map(part=>part[0]).slice(0,2).join("").toUpperCase();
  const linked=paperById(discussion.linkedPaper);
  return `<div class="discussion-detail mx-auto max-w-5xl px-4 py-7 sm:px-6"><button class="back" data-action="back-discussions">${icon("arrow-left")} All discussions</button><article class="discussion-thread"><header><span class="eyebrow">${esc(discussion.topic)} · COMMUNITY REVIEW</span><h1>${esc(discussion.title)}</h1><div><span class="avatar">${esc(initials)}</span><p><b>${esc(discussion.author)}</b><small>Started ${esc(discussion.time)} ago</small></p></div></header><div class="thread-body"><aside><button data-discussion-vote="${esc(discussion.id)}" data-direction="up">${icon("caret-up")}</button><b>${discussion.score||0}</b><button data-discussion-vote="${esc(discussion.id)}" data-direction="down">${icon("caret-down")}</button></aside><main><p>${esc(discussion.body)}</p>${linked?`<button class="linked-paper" data-paper="${esc(linked.id)}">${icon("file-lines")}<span><b>${esc(linked.title)}</b><small>${esc(linked.id)} · ${esc(linked.version)}</small></span>${icon("arrow-right")}</button>`:""}<footer><button data-discussion-follow="${esc(discussion.id)}">${icon("star")} ${discussion.following?"Following":"Follow"}</button><button data-discussion-save="${esc(discussion.id)}">${icon("bookmark")} ${discussion.saved?"Saved":"Save"}</button><button data-share-discussion="${esc(discussion.id)}">${icon("share-nodes")} Share</button></footer></main></div></article><section class="thread-replies"><header><h2>${discussion.replies.length} ${discussion.replies.length===1?"reply":"replies"}</h2><span>Replies are retained with the discussion record.</span></header>${discussion.replies.map(reply=>{const replyInitials=reply.author.split(/\s+/).map(part=>part[0]).slice(0,2).join("").toUpperCase();return `<article><span class="avatar">${esc(replyInitials)}</span><div><b>${esc(reply.author)}</b><small> · ${esc(reply.time||"just now")}</small><p>${esc(reply.body)}</p><button>${icon("caret-up")} ${reply.score||1}</button></div></article>`}).join("")||`<div class="empty"><h2>No replies yet</h2><p>Be the first to extend the research discussion.</p></div>`}<form data-discussion-reply data-discussion-id="${esc(discussion.id)}"><label>Join the discussion<textarea name="reply" required minlength="10" placeholder="Add evidence, a methodological question, critique, or clarification."></textarea></label><button class="primary" type="submit">Post reply</button></form></section></div>`;
}

function presentationDetailPage(){
  const presentation=presentations[state.selectedPresentation];
  if(!presentation){state.selectedPresentation=null;return presentationsPage()}
  const linked=paperById(presentation.paper);
  const outline=["Research question and context","Method and evidence","Core result","Validation and limitations","Discussion and next work"];
  return `<div class="space-detail mx-auto max-w-6xl px-4 py-7 sm:px-6"><button class="back" data-action="back-presentations">${icon("arrow-left")} All presentations</button><header class="presentation-hero"><div class="slide-preview"><span>PEERXIV PRESENTATION</span>${icon("person-chalkboard")}</div><div><span class="eyebrow">${esc(presentation.format)} · ${presentation.slides} SLIDES</span><h1>${esc(presentation.title)}</h1><p>${esc(presentation.speaker)} · ${esc(presentation.event)}</p><div><button class="primary" data-presentation-export="${state.selectedPresentation}">${icon("download")} Export metadata</button><button data-action="new-discussion" data-linked-paper="${esc(presentation.paper)}">${icon("comment")} Discuss</button></div></div></header>${linked?`<button class="linked-paper" data-paper="${esc(linked.id)}">${icon("file-lines")}<span><b>${esc(linked.title)}</b><small>${esc(linked.id)} · ${esc(linked.version)}</small></span>${icon("arrow-right")}</button>`:""}<section class="presentation-outline"><header><span class="eyebrow">REGISTERED DECK OUTLINE</span><h2>Presentation record</h2><p>The deck binary is not stored yet, but this view makes its linked scholarly context and exportable record usable.</p></header><div>${outline.map((item,index)=>`<article><span>${String(index+1).padStart(2,"0")}</span><b>${item}</b><small>${Math.max(1,Math.round(presentation.slides/outline.length))} slides</small></article>`).join("")}</div></section></div>`;
}

function conferenceDetailPage(){
  const conference=conferences[state.selectedConference];
  if(!conference){state.selectedConference=null;return conferencesPage()}
  const topicWords=conference.topics.toLowerCase().split(/[^a-z]+/).filter(word=>word.length>3);
  const related=papers.filter(p=>topicWords.some(word=>[p.topic,...p.tags].join(" ").toLowerCase().includes(word))).slice(0,3);
  return `<div class="space-detail mx-auto max-w-6xl px-4 py-7 sm:px-6"><button class="back" data-action="back-conferences">${icon("arrow-left")} All conferences</button><header class="conference-hero"><span class="eyebrow">CALL FOR PAPERS · CLOSES ${esc(conference.deadline.toUpperCase())}</span><h1>${esc(conference.name)}</h1><p>${icon("calendar-days")} ${esc(conference.dates)} &nbsp; ${icon("location-dot")} ${esc(conference.location)}</p><div><button class="primary ${conference.followed?"followed":""}" data-conference-follow="${state.selectedConference}">${icon("bookmark")} ${conference.followed?"Following":"Follow conference"}</button><button data-action="new-discussion">${icon("comment")} Discuss event</button></div></header><div class="conference-detail-grid"><section><span class="eyebrow">TOPIC SCOPE</span><h2>${esc(conference.topics)}</h2><p>Follow this space to retain the event, its call, and related PeerXiv research together.</p></section><section><span class="eyebrow">SUBMISSION TIMELINE</span><dl><div><dt>Submission deadline</dt><dd>${esc(conference.deadline)}</dd></div><div><dt>Event dates</dt><dd>${esc(conference.dates)}</dd></div><div><dt>Location</dt><dd>${esc(conference.location)}</dd></div></dl></section></div><section class="related-space-records"><header><span class="eyebrow">RELATED PEERXIV RESEARCH</span><h2>Research matching the event scope</h2></header><div class="paper-list">${related.map(paperCard).join("")||`<div class="empty"><h2>No related papers yet</h2><p>Classified papers matching this scope will appear here.</p></div>`}</div></section></div>`;
}

function journalDetailPage(){
  const journal=journals[state.selectedJournal];
  if(!journal){state.selectedJournal=null;return journalsPage()}
  const linked=papers.find(p=>p.title===journal.paper);
  return `<div class="space-detail mx-auto max-w-5xl px-4 py-7 sm:px-6"><button class="back" data-action="back-journals">${icon("arrow-left")} Journal relationships</button><header class="journal-relationship"><span class="eyebrow">${esc(journal.status)}</span><h1>${esc(journal.paper)}</h1><p>Published in <b>${esc(journal.journal)}</b></p></header><section class="publication-chain"><article><span>01</span><div><small>PEERXIV PREPRINT</small><h2>${esc(linked?.id||journal.paper)}</h2><p>${esc(linked?.version||"Research record")}</p>${linked?`<button data-paper="${esc(linked.id)}">Open preprint</button>`:""}</div></article><i>${icon("arrow-down")}</i><article><span>02</span><div><small>JOURNAL RELATIONSHIP</small><h2>${esc(journal.journal)}</h2><p>DOI: ${esc(journal.doi)}</p><button data-copy-doi="${esc(journal.doi)}" ${journal.doi==="Pending"?"disabled":""}>${icon("copy")} Copy DOI</button></div></article></section><div class="backend-boundary">${icon("link")} The preprint-to-publication relationship is retained locally; DOI verification remains a backend integration responsibility.</div></div>`;
}

function authDialog(){
  if(!state.authModal)return "";
  const registering=state.authModal==="register";
  const registrationAvailable=state.registrationMode!=="disabled";
  const registrationCopy=state.registrationMode==="invite"?"PeerXiv is accepting invited alpha researchers.":"Publish, discuss, build research spaces, and receive relevant research notifications.";
  return `<div class="modal-layer fixed inset-0 z-[70] grid place-items-center overflow-y-auto bg-black/60 p-3"><form class="upload-modal auth-dialog relative w-full max-w-md rounded-xl p-5 sm:p-8" data-auth-form="${registering?"register":"login"}"><button type="button" class="close" data-action="close-auth">${icon("xmark")}</button><span class="eyebrow">${registering?"JOIN THE RESEARCH NETWORK":"WELCOME BACK"}</span><h2>${registering?"Create your PeerXiv account":"Sign in to PeerXiv"}</h2><p>${registering?registrationCopy:"Continue your papers, discussions, spaces, and research network."}</p>${registering?`<label>Display name<input name="display_name" required minlength="2" autocomplete="name" placeholder="Your name"/></label><label>Role<input name="role" required value="Researcher" autocomplete="organization-title"/></label>${state.registrationMode==="invite"?`<label>Alpha invite code<input name="invite_code" required minlength="12" autocomplete="off"/></label>`:""}`:""}<label>Email<input name="email" type="email" required autocomplete="email" placeholder="you@example.org"/></label><label>Password<input name="password" type="password" required minlength="${registering?12:1}" autocomplete="${registering?"new-password":"current-password"}"/></label><footer>${registering?`<button type="button" data-auth-switch="login">I already have an account</button>`:registrationAvailable?`<button type="button" data-auth-switch="register">${state.registrationMode==="invite"?"Use an invite":"Create account"}</button>`:"<span>Registration is currently closed.</span>"}<button class="primary" type="submit">${registering?"Create account":"Sign in"}</button></footer></form></div>`;
}

function toastView(){return state.toast?`<div class="toast ${state.toast.tone}">${icon(state.toast.tone==="error"?"triangle-exclamation":"circle-check")} ${esc(state.toast.message)}</div>`:""}

function render(){
  const routes={messages:messagesPage,discussions:discussionsPage,library:libraryPage,connections:connectionsPage,profile:profilePage,spaces:spacesHubPage,workspaces:workspacesPage,presentations:presentationsPage,conferences:conferencesPage,journals:journalsPage};
  const body=state.selectedPaper?paperDetail(state.selectedPaper):state.selectedDiscussion?discussionDetailPage():state.selectedWorkspace!==null?workspaceDetailPage():state.selectedPresentation!==null?presentationDetailPage():state.selectedConference!==null?conferenceDetailPage():state.selectedJournal!==null?journalDetailPage():(routes[state.page]||homeLayout)();
  app.innerHTML=`${topNav()}${body}${state.uploadOpen?uploadModal():""}${workflowDialog()}${integrationDialog()}${citationDialog()}${shareDialog()}${authDialog()}${toastView()}`;
  document.body.classList.toggle("overlay-open", Boolean(state.mobileNavOpen||state.uploadOpen||state.workflowModal||state.integrationModal||state.citationPaper||state.shareTarget||state.authModal));
  bind();
}

function paperById(id){return papers.find(p=>p.id===id)}

function setRouteHash(kind,id){
  const hash=id?`#${kind}=${encodeURIComponent(id)}`:"";
  history.replaceState(null,"",`${location.pathname}${location.search}${hash}`);
}

function clearSelections(){
  state.selectedPaper=null;state.selectedDiscussion=null;state.selectedWorkspace=null;
  state.selectedPresentation=null;state.selectedConference=null;state.selectedJournal=null;
}

async function openPaper(id,updateHash=true){
  let paper=paperById(id);
  if(!paper){
    try{
      const record=await apiRequest(`/papers/${encodeURIComponent(id)}`);
      paper=paperFromBackend(record);
      papers.unshift(paper);
      persistPrototype();
    }catch(error){showToast(error.message||"Could not open this paper.","error");return}
  }
  clearSelections();
  state.selectedPaper=paper;
  state.notificationOpen=false;
  if(updateHash)setRouteHash("paper",paper.id);
  render();
}

async function openDiscussion(id,updateHash=true){
  let discussion=discussions.find(item=>item.id===id);
  if(!discussion){showToast("This discussion could not be found.","error");return}
  if(state.backendDiscussions.has(id)){
    try{discussion=upsertDiscussion(await apiRequest(`/social/discussions/${encodeURIComponent(id)}`))}
    catch(error){showToast(error.message||"Could not load this discussion.","error");return}
  }
  clearSelections();
  state.selectedDiscussion=discussion;
  state.page="discussions";
  state.notificationOpen=false;
  if(updateHash)setRouteHash("discussion",discussion.id);
  render();
}

async function routeFromHash(){
  const params=new URLSearchParams(location.hash.slice(1));
  const paper=params.get("paper");
  const discussion=params.get("discussion");
  if(paper){await openPaper(paper,false);return}
  if(discussion){await openDiscussion(discussion,false)}
}

function openPdf(paper){
  if(!paper?.pdfAvailable&&!paper?.manuscript?.stored){
    showToast("No viewable PDF is attached to this research record.","error");
    return;
  }
  const url=paper.pdfUrl||`/api/v1/papers/${encodeURIComponent(paper.id)}/pdf`;
  window.open(url,"_blank","noopener,noreferrer");
  showToast("Opening the manuscript PDF.");
}

function canonicalPaperUrl(id){return `${location.origin}${location.pathname}#paper=${encodeURIComponent(id)}`}
function canonicalDiscussionUrl(id){return `${location.origin}${location.pathname}#discussion=${encodeURIComponent(id)}`}

function citationVariants(p){
  const year=p.submitted?.match(/\b(?:19|20)\d{2}\b/)?.[0]||String(new Date().getFullYear());
  const url=canonicalPaperUrl(p.id);
  const key=`${p.authors.split(",")[0].trim().split(/\s+/).at(-1)||"peerxiv"}${year}${p.id.replace(/[^a-z0-9]/gi,"")}`;
  const title=p.title.replace(/[{}]/g,"");
  return {
    apa:`${p.authors} (${year}). ${p.title}. PeerXiv (${p.id}, ${p.version}). ${url}`,
    mla:`${p.authors}. “${p.title}.” PeerXiv, ${year}, ${p.id}, ${p.version}. ${url}.`,
    chicago:`${p.authors}. “${p.title}.” PeerXiv ${p.version} (${year}). ${p.id}. ${url}.`,
    bibtex:`@article{${key},\n  author = {${p.authors.replaceAll(", "," and ")}},\n  title = {${title}},\n  journal = {PeerXiv},\n  year = {${year}},\n  number = {${p.id}},\n  note = {${p.version}},\n  url = {${url}}\n}`
  };
}

function legacyCopyText(value){
  const field=document.createElement("textarea");
  field.value=value;
  field.setAttribute("readonly","");
  field.style.position="fixed";
  field.style.opacity="0";
  document.body.appendChild(field);
  field.select();
  field.setSelectionRange(0,field.value.length);
  let copied=false;
  try{copied=document.execCommand("copy")}catch{copied=false}
  field.remove();
  return copied;
}

async function copyText(value,label){
  let copied=false;
  try{
    if(navigator.clipboard?.writeText&&window.isSecureContext){await navigator.clipboard.writeText(value);copied=true}
  }catch{copied=false}
  if(!copied) copied=legacyCopyText(value);
  showToast(copied?`${label} copied to clipboard.`:`Select and copy the ${label.toLowerCase()} manually.`,copied?"success":"error");
  return copied;
}

function downloadText(filename,value,type="text/plain"){
  const blob=new Blob([value],{type});
  const url=URL.createObjectURL(blob);
  const link=document.createElement("a");
  link.href=url;link.download=filename;link.click();
  window.setTimeout(()=>URL.revokeObjectURL(url),0);
}

function openShareTarget(target){state.shareTarget=target;render()}

function sharePaper(p){
  if(!p)return;
  openShareTarget({kind:"paper",id:p.id,title:p.title,text:`${p.title} — ${p.authors}`,url:canonicalPaperUrl(p.id)});
}

function validOrcid(value){
  const compact=value.replaceAll("-","").toUpperCase();
  if(!/^\d{15}[\dX]$/.test(compact)) return false;
  let total=0;
  for(const digit of compact.slice(0,15)) total=(total+Number(digit))*2;
  const result=(12-(total%11))%11;
  return (result===10?"X":String(result))===compact.at(-1);
}

async function handleComment(event){
  event.preventDefault();
  const form=event.currentTarget;
  const paper=paperById(form.dataset.paperId);
  const body=new FormData(form).get("comment").trim();
  if(!paper||!body)return;
  if(!requireSignedIn("comment on this paper"))return;
  if(!paper.status){showToast("This paper is unavailable for comments.","error");return}
  form.querySelectorAll("button,textarea").forEach(control=>control.disabled=true);
  try{
    const record=await apiRequest("/social/discussions",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({title:`Comment: ${body.slice(0,120)}`,topic:paper.topic||"Research Practice",body,paper_identifier:paper.id})
    });
    upsertDiscussion(record);paper.comments=(paper.comments||0)+1;
    await refreshAccountData();persistPrototype();render();showToast("Comment retained as a linked, classified discussion.");
  }catch(error){form.querySelectorAll("button,textarea").forEach(control=>control.disabled=false);showToast(error.message||"Could not post this comment.","error")}
}

async function handleDiscussionReply(event){
  event.preventDefault();
  const form=event.currentTarget;
  const discussion=discussions.find(item=>item.id===form.dataset.discussionId);
  const body=new FormData(form).get("reply").trim();
  if(!discussion||!body)return;
  if(!requireSignedIn("join this discussion"))return;
  if(!state.backendDiscussions.has(discussion.id)){
    showToast("This discussion is unavailable for replies.","error");
    return;
  }
  try{
    await apiRequest(`/social/discussions/${encodeURIComponent(discussion.id)}/comments`,{
      method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body})
    });
    upsertDiscussion(await apiRequest(`/social/discussions/${encodeURIComponent(discussion.id)}`));
    await refreshAccountData();
    render();
    showToast("Reply posted and classified for related research.");
  }catch(error){showToast(error.message||"Could not post reply.","error")}
}

async function handleAuth(event){
  event.preventDefault();
  const form=event.currentTarget;
  const data=new FormData(form);
  const mode=form.dataset.authForm;
  const payload={email:data.get("email").trim(),password:data.get("password")};
  if(mode==="register"){
    payload.display_name=data.get("display_name").trim();
    payload.role=data.get("role").trim();
    if(state.registrationMode==="invite")payload.invite_code=data.get("invite_code").trim();
  }
  form.querySelectorAll("button,input").forEach(control=>control.disabled=true);
  try{
    applySession(await apiRequest(`/accounts/${mode}`,{
      method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)
    }));
    state.authModal=null;
    await Promise.all([refreshAccountData(),refreshCommunityData(),refreshConversations()]);
    initializeRealtime();
    persistPrototype();
    render();
    showToast(mode==="register"?"Your PeerXiv account is ready.":"Signed in.");
  }catch(error){
    form.querySelectorAll("button,input").forEach(control=>control.disabled=false);
    showToast(error.message||"Authentication failed.","error");
  }
}

async function handleLogout(){
  try{await apiRequest("/accounts/logout",{method:"POST"})}catch(error){console.warn(error)}
  realtimeSocket?.disconnect();realtimeSocket=null;
  state.auth={ready:true,authenticated:false,user:null,csrfToken:null};
  state.people=[];state.activities=[];state.notifications=[];state.messages={};conversations.splice(0,conversations.length);state.conversation=null;
  state.page="home";clearSelections();render();showToast("Signed out.");
}

async function followPerson(userId){
  if(!requireSignedIn("follow researchers"))return;
  const person=state.people.find(item=>item.id===userId);
  if(!person)return;
  try{
    const result=await apiRequest(`/accounts/people/${encodeURIComponent(userId)}/follow`,{
      method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({following:!person.following})
    });
    person.following=result.following;
    await refreshAccountData();render();showToast(result.following?`Following ${person.display_name}.`:`Unfollowed ${person.display_name}.`);
  }catch(error){showToast(error.message||"Could not update this follow.","error")}
}

async function mutateDiscussion(discussion,action,value){
  if(!requireSignedIn(`${action} this discussion`))return;
  if(!state.backendDiscussions.has(discussion.id)){
    showToast("This discussion is unavailable for this action.","error");return;
  }
  try{
    const result=await apiRequest(`/social/discussions/${encodeURIComponent(discussion.id)}/${action}`,{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify(action==="vote"?{value}:{enabled:value})
    });
    if(action==="vote"){discussion.score=result.score;discussion.userVote=result.viewer_vote}
    else discussion[action==="follow"?"following":"saved"]=result[action==="follow"?"following":"saved"];
    render();
  }catch(error){showToast(error.message||"Could not update the discussion.","error")}
}

async function markNotificationRead(notification){
  if(!notification||notification.read||!state.auth.authenticated)return;
  notification.read=true;render();
  try{await apiRequest(`/accounts/notifications/${encodeURIComponent(notification.id)}/read`,{method:"POST"})}
  catch(error){console.warn("Could not mark notification read",error)}
}

async function handleShareSubmit(event){
  event.preventDefault();
  const target=state.shareTarget;
  if(!target)return;
  const conversationId=new FormData(event.currentTarget).get("conversation");
  const conversation=conversations.find(item=>item.id===conversationId);
  if(!conversation)return;
  const form=event.currentTarget;
  form.querySelectorAll("button,select").forEach(control=>control.disabled=true);
  try{
    const body=`${target.kind==="paper"?"Shared preprint":"Shared discussion"}: ${target.title}\n${target.url}`;
    appendConversationMessage(await apiRequest(`/social/conversations/${encodeURIComponent(conversation.id)}/messages`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body})}));
    state.conversation=conversation.id;state.shareTarget=null;state.page="messages";clearSelections();setRouteHash("","");render();showToast(`Shared with ${conversation.name}.`);
  }catch(error){form.querySelectorAll("button,select").forEach(control=>control.disabled=false);showToast(error.message||"Could not share this record.","error")}
}

async function handleSubmission(event){
  event.preventDefault();
  if(!requireSignedIn("submit research"))return;
  const form=event.currentTarget;
  const data=new FormData(form);
  const intent=event.submitter?.value||"draft";
  const file=data.get("manuscript");
  if(intent==="publish"&&(!file||!file.size)){
    const field=form.elements.manuscript;
    field.setCustomValidity("Choose a PDF before publishing.");field.reportValidity();field.setCustomValidity("");return;
  }
  const title=data.get("title").trim();
  const abstract=data.get("abstract").trim();
  const authors=data.get("authors").split(",").map(value=>value.trim()).filter(Boolean);
  const tags=data.get("tags").split(",").map(tag=>tag.trim()).filter(Boolean);
  const sectionText=data.get("sections").trim();
  const sections=sectionText.split(/\n\s*\n/).map(text=>text.trim()).filter(Boolean).map((text,index)=>({heading:`Submission excerpt ${index+1}`,text}));
  form.querySelectorAll("button,input,textarea,select").forEach(control=>control.disabled=true);
  try{
    const draft=await apiRequest("/papers",{
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({
        title,abstract,authors,tags,
        open_review:intent==="publish"
      })
    });
    let published=null;
    if(intent==="publish"){
      const publishData=new FormData();
      publishData.set("authors",JSON.stringify(authors));
      publishData.set("tags",JSON.stringify(tags));
      publishData.set("sections",JSON.stringify(sections));
      publishData.set("metadata",JSON.stringify({submission_source:"peerxiv-web"}));
      publishData.set("manuscript",file,file.name);
      published=await apiRequest(`/papers/${encodeURIComponent(draft.identifier)}/publish`,{method:"POST",body:publishData});
    }
    const metadata=published?.metadata;
    const metadataTags=metadata?.tags||[];
    const primaryCode=metadata?.primary_category||draft.subfield||"px.PENDING";
    const primaryTag=metadataTags.find(tag=>tag.facet==="subject"&&tag.slug===primaryCode.toLowerCase());
    const visibleTags=[...new Set([
      ...tags,
      ...metadataTags.filter(tag=>["method","concept"].includes(tag.facet)).slice(0,6).map(tag=>tag.label)
    ])];
    const now=new Date();
    const paper={
      id:draft.identifier,title,authors:authors.join(", "),
      topic:primaryTag?.label||draft.subject,code:primaryCode,
      submitted:now.toLocaleDateString(undefined,{day:"numeric",month:"short",year:"numeric"}),
      time:"just now",version:`v${published?.number||1}`,score:0,comments:0,citations:0,
      abstract,tags:visibleTags,openReview:intent==="publish",saved:intent==="draft",
      status:intent==="draft"?"draft":"published",
      manuscript:published?.manuscript_uri?{name:file.name,size:file.size,type:file.type,stored:true}:null,
      pdfAvailable:Boolean(published?.manuscript_uri),
      pdfUrl:`/api/v1/papers/${encodeURIComponent(draft.identifier)}/pdf`,
      metadataSummary:metadata?.summary||null,
      metadataTags
    };
    papers.unshift(paper);
    const workspaceIndex=data.get("workspace");
    if(workspaceIndex!==""){
      const workspace=workspaces[Number(workspaceIndex)];
      if(workspace){workspace.paper=paper.id;workspace.papers=[...new Set([...(workspace.papers||[]),paper.id])];workspace.updated="just now";}
    }
    addNotificationMatches(published?.notifications||[]);
    const notificationText=intent==="draft"
      ?`Draft saved: ${paper.title}`
      :`Published and classified as ${paper.topic}: ${paper.title}`;
    state.notifications.unshift({id:`n${Date.now()}`,kind:intent==="draft"?"draft":"classification",text:notificationText,reason:metadata?.summary||null,time:"now",read:false,paper:paper.id});
    state.uploadOpen=false;
    state.page=intent==="draft"?"library":"home";
    if(intent==="publish") state.topic="All topics";
    state.selectedPaper=null;
    persistPrototype();
    showToast(intent==="draft"?"Draft saved to your library.":`Classified as ${paper.topic} and published.`);
  }catch(error){
    form.querySelectorAll("button,input,textarea,select").forEach(control=>control.disabled=false);
    showToast(error.message||"Submission failed.","error");
  }
}

function handleIntegration(event){
  event.preventDefault();
  const form=event.currentTarget;
  const kind=form.dataset.kind;
  const data=new FormData(form);
  if(kind==="orcid"){
    const identifier=data.get("identifier").trim();
    if(!validOrcid(identifier)){
      const field=form.elements.identifier;
      field.setCustomValidity("Enter a valid ORCID iD, including its checksum.");field.reportValidity();field.setCustomValidity("");return;
    }
    state.integrations.orcid={status:"configured",identifier,visibility:data.get("visibility")};
  }else if(kind==="overleaf"){
    let parsed;
    try{parsed=new URL(data.get("projectUrl").trim())}catch{parsed=null}
    if(!parsed||!(parsed.hostname==="overleaf.com"||parsed.hostname.endsWith(".overleaf.com"))){
      const field=form.elements.projectUrl;field.setCustomValidity("Use a valid overleaf.com project URL.");field.reportValidity();field.setCustomValidity("");return;
    }
    state.integrations.overleaf={status:"configured",projectName:data.get("projectName").trim(),projectUrl:parsed.href,sync:data.get("sync")};
  }else{
    const remoteUrl=data.get("remoteUrl").trim();
    if(!/^(https?:\/\/|ssh:\/\/|git@)[^\s]+/.test(remoteUrl)){
      const field=form.elements.remoteUrl;field.setCustomValidity("Use an HTTPS, SSH, or git@ repository remote.");field.reportValidity();field.setCustomValidity("");return;
    }
    state.integrations.git={status:"configured",provider:data.get("provider"),remoteUrl,branch:data.get("branch").trim()};
  }
  state.integrationModal=null;
  persistPrototype();
  showToast(`${kind==="git"?"Git":kind==="orcid"?"ORCID":"Overleaf"} configuration saved locally.`);
}

async function handleWorkflow(event){
  event.preventDefault();
  const form=event.currentTarget;
  const type=form.dataset.workflowForm;
  const data=new FormData(form);
  const authenticatedTypes=new Set(["workspace","discussion","conference","publication","message","profile","artifact","presentation","journalModel"]);
  if(authenticatedTypes.has(type)&&!requireSignedIn(type==="discussion"?"start a discussion":"save this research action"))return;
  form.querySelectorAll("button,input,textarea,select").forEach(control=>control.disabled=true);
  let message="Saved.";
  try{
    if(type==="workspace"){
      const record=await apiRequest("/spaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"workspace",title:data.get("name").trim(),description:"Connected papers, source, artifacts, and collaborators.",paper_identifiers:data.get("paper")?[data.get("paper")]:[],details:{repository:data.get("repository").trim(),overleaf:data.get("overleaf").trim(),expected_members:Number(data.get("members"))||1}})});
      upsertSpace(record);state.page="workspaces";message="Workspace created and persisted.";
    }else if(type==="discussion"){
      const record=await apiRequest("/social/discussions",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:data.get("title").trim(),topic:data.get("topic"),body:data.get("body").trim(),paper_identifier:data.get("paper")||null})});
      const discussion=upsertDiscussion(record);
      clearSelections();state.selectedDiscussion=discussion;state.page="discussions";state.discussionContext=null;setRouteHash("discussion",discussion.id);message="Discussion published, classified, and retained.";
    }else if(type==="conference"){
      const record=await apiRequest("/spaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"conference",title:data.get("name").trim(),description:data.get("topics").trim(),details:{dates:data.get("dates").trim(),deadline:data.get("deadline").trim(),location:data.get("location").trim(),topics:data.get("topics").trim()}})});
      upsertSpace(record);state.page="conferences";message="Conference space created.";
    }else if(type==="publication"){
      const paperTitle=data.get("paper");const linked= papers.find(item=>item.title===paperTitle);
      const record=await apiRequest("/spaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"journal",title:`${data.get("journal").trim()} — ${paperTitle}`,status:data.get("status"),paper_identifiers:linked?[linked.id]:[],details:{paper_title:paperTitle,journal:data.get("journal").trim(),doi:data.get("doi").trim()}})});
      upsertSpace(record);state.page="journals";state.journalTab="published";message="Published relationship persisted.";
    }else if(type==="filters"){
      state.topic=data.get("topic");state.sort=data.get("sort");state.page="home";message="Feed filters applied.";
    }else if(type==="message"){
      const record=await apiRequest("/social/conversations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({recipient_email:data.get("recipient").trim(),body:data.get("message").trim()})});
      const conversation=upsertConversation(record);realtimeSocket?.emit("conversation.join",{conversation_id:conversation.id});state.conversation=conversation.id;state.page="messages";state.mobileConversationOpen=true;message="Conversation created and retained.";
    }else if(type==="profile"){
      const account=await apiRequest("/accounts/me",{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({display_name:data.get("name").trim(),role:data.get("role").trim(),bio:data.get("bio").trim()})});
      applySession({authenticated:true,user:account,csrf_token:state.auth.csrfToken});message="Profile updated.";
    }else if(type==="collection"){
      const name=data.get("name").trim();if(!state.collections.some(item=>item.toLowerCase()===name.toLowerCase()))state.collections.push(name);message="Collection created.";
    }else if(type==="artifact"){
      const workspace=workspaces[state.selectedWorkspace];
      if(!workspace?.backend)throw new Error("Create or open a persisted workspace before registering artifacts.");
      await apiRequest(`/spaces/${encodeURIComponent(workspace.id)}/resources`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({resource_type:data.get("type").toLowerCase(),title:data.get("name").trim(),url:data.get("url").trim()})});
      upsertSpace(await apiRequest(`/spaces/${encodeURIComponent(workspace.id)}`));message="Artifact registered with the workspace.";
    }else if(type==="presentation"){
      const record=await apiRequest("/spaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"presentation",title:data.get("title").trim(),paper_identifiers:data.get("paper")?[data.get("paper")]:[],details:{speaker:data.get("speaker").trim(),format:data.get("format"),event:data.get("event").trim(),slides:Number(data.get("slides"))||1}})});
      upsertSpace(record);state.page="presentations";message="Presentation persisted with its research record.";
    }else if(type==="journalModel"){
      state.journalModel={title:data.get("title").trim(),scope:data.get("scope").trim(),reviewModel:data.get("reviewModel"),governance:data.get("governance").trim()};
      const record=await apiRequest("/spaces",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({kind:"journal",title:state.journalModel.title,description:state.journalModel.scope,status:"concept",details:{review_model:state.journalModel.reviewModel,governance:state.journalModel.governance}})});
      upsertSpace(record);state.page="journals";state.journalTab="concept";message="PeerXiv Journal model persisted.";
    }
    state.workflowModal=null;
    if(state.auth.authenticated)await refreshAccountData();
    persistPrototype();showToast(message);
  }catch(error){
    form.querySelectorAll("button,input,textarea,select").forEach(control=>control.disabled=false);
    showToast(error.message||"Could not save this action.","error");
  }
}

function bind(){
  app.querySelectorAll("[data-page]").forEach(el=>el.onclick=()=>{const protectedPages=new Set(["messages","library","profile"]);if(protectedPages.has(el.dataset.page)&&!requireSignedIn(`open ${el.dataset.page}`))return;state.page=el.dataset.page;clearSelections();setRouteHash("","");state.mobileNavOpen=false;state.mobileConversationOpen=false;state.notificationOpen=false;render()});
  app.querySelectorAll("[data-topic]").forEach(el=>el.onclick=e=>{e.stopPropagation();state.topic=el.dataset.topic;state.page="topic";clearSelections();setRouteHash("","");state.mobileNavOpen=false;render()});
  app.querySelectorAll("[data-paper]").forEach(el=>el.onclick=e=>{if(e.target.closest("[data-save],[data-cite],[data-share],[data-pdf]"))return;const notification=state.notifications.find(item=>item.id===el.dataset.notification);if(notification)void markNotificationRead(notification);void openPaper(el.dataset.paper)});
  app.querySelectorAll("[data-notification-discussion]").forEach(el=>el.onclick=()=>{const notification=state.notifications.find(item=>item.id===el.dataset.notification);if(notification)void markNotificationRead(notification);void openDiscussion(el.dataset.notificationDiscussion)});
  app.querySelectorAll("[data-save]").forEach(el=>el.onclick=e=>{e.stopPropagation();const p=paperById(el.dataset.save);p.saved=!p.saved;persistPrototype();render()});
  app.querySelectorAll("[data-expand]").forEach(el=>el.onclick=e=>{e.stopPropagation();const id=el.dataset.expand;state.expandedAbstracts.has(id)?state.expandedAbstracts.delete(id):state.expandedAbstracts.add(id);render()});
  app.querySelectorAll("[data-vote]").forEach(el=>el.onclick=e=>{e.stopPropagation();const id=el.dataset.id;const value=el.dataset.vote==="up"?1:-1;state.votes.set(id,state.votes.get(id)===value?0:value);persistPrototype();render()});
  app.querySelectorAll("[data-conversation]").forEach(el=>el.onclick=async()=>{state.conversation=el.dataset.conversation;state.mobileConversationOpen=true;try{await loadConversation(state.conversation)}catch(error){showToast(error.message||"Could not load this conversation.","error")}render()});
  app.querySelectorAll("[data-connect]").forEach(el=>el.onclick=()=>{if(!requireSignedIn("follow researchers"))return;const r=researchers.find(x=>x.name===el.dataset.connect);r.connected=!r.connected;persistPrototype();render()});
  app.querySelectorAll("[data-follow-person]").forEach(el=>el.onclick=()=>{void followPerson(el.dataset.followPerson)});
  app.querySelectorAll("[data-sort]").forEach(el=>el.onclick=()=>{state.sort=el.dataset.sort;persistPrototype();render()});
  app.querySelectorAll("[data-workspace]").forEach(el=>el.onclick=e=>{e.stopPropagation();clearSelections();state.selectedWorkspace=Number(el.dataset.workspace);state.workspaceTab="overview";render()});
  app.querySelectorAll("[data-workspace-tab]").forEach(el=>el.onclick=()=>{state.workspaceTab=el.dataset.workspaceTab;render()});
  app.querySelectorAll("[data-journal-tab]").forEach(el=>el.onclick=()=>{state.journalTab=el.dataset.journalTab;render()});
  app.querySelectorAll("[data-conference-follow]").forEach(el=>el.onclick=()=>{const conference=conferences[Number(el.dataset.conferenceFollow)];conference.followed=!conference.followed;persistPrototype();render()});
  app.querySelectorAll("[data-discussion]").forEach(el=>el.onclick=e=>{if(e.target.closest("[data-discussion-vote],[data-discussion-follow],[data-discussion-save]"))return;void openDiscussion(el.dataset.discussion)});
  app.querySelectorAll("[data-discussion-filter]").forEach(el=>el.onclick=e=>{e.stopPropagation();state.discussionFilter=el.dataset.discussionFilter;state.page="discussions";clearSelections();setRouteHash("","");state.mobileNavOpen=false;render()});
  app.querySelectorAll("[data-discussion-vote]").forEach(el=>el.onclick=e=>{e.stopPropagation();const discussion=discussions.find(item=>item.id===el.dataset.discussionVote);if(!discussion)return;const direction=el.dataset.direction==="down"?-1:1;const next=discussion.userVote===direction?0:direction;void mutateDiscussion(discussion,"vote",next)});
  app.querySelectorAll("[data-discussion-follow]").forEach(el=>el.onclick=e=>{e.stopPropagation();const discussion=discussions.find(item=>item.id===el.dataset.discussionFollow);if(discussion)void mutateDiscussion(discussion,"follow",!discussion.following)});
  app.querySelectorAll("[data-discussion-save]").forEach(el=>el.onclick=e=>{e.stopPropagation();const discussion=discussions.find(item=>item.id===el.dataset.discussionSave);if(discussion)void mutateDiscussion(discussion,"save",!discussion.saved)});
  app.querySelectorAll("[data-pdf]").forEach(el=>el.onclick=e=>{e.stopPropagation();openPdf(paperById(el.dataset.pdf))});
  app.querySelectorAll("[data-cite]").forEach(el=>el.onclick=e=>{e.stopPropagation();state.citationPaper=el.dataset.cite;state.citationStyle="apa";render()});
  app.querySelectorAll("[data-share]").forEach(el=>el.onclick=e=>{e.stopPropagation();sharePaper(paperById(el.dataset.share))});
  app.querySelectorAll("[data-share-discussion]").forEach(el=>el.onclick=e=>{e.stopPropagation();const discussion=discussions.find(item=>item.id===el.dataset.shareDiscussion);if(discussion)openShareTarget({kind:"discussion",id:discussion.id,title:discussion.title,text:`${discussion.title} — ${discussion.author}`,url:canonicalDiscussionUrl(discussion.id)})});
  app.querySelector('[data-action="toggle-explore"]')?.addEventListener("click",()=>{state.exploreOpen=!state.exploreOpen;render()});
  app.querySelector('[data-action="toggle-discussions"]')?.addEventListener("click",()=>{if(state.page!=="discussions"){state.page="discussions";clearSelections();state.discussionsOpen=true;setRouteHash("","")}else{state.discussionsOpen=!state.discussionsOpen}state.mobileNavOpen=false;render()});
  app.querySelector('[data-action="toggle-spaces"]')?.addEventListener("click",()=>{if(state.page!=="spaces"){state.page="spaces";clearSelections();state.spacesOpen=true;setRouteHash("","")}else{state.spacesOpen=!state.spacesOpen}state.mobileNavOpen=false;render()});
  app.querySelector('[data-action="open-mobile-nav"]')?.addEventListener("click",()=>{state.mobileNavOpen=true;render()});
  app.querySelectorAll('[data-action="close-mobile-nav"]').forEach(el=>el.onclick=()=>{state.mobileNavOpen=false;render()});
  app.querySelector('[data-action="back-to-inbox"]')?.addEventListener("click",()=>{state.mobileConversationOpen=false;render()});
  app.querySelectorAll('[data-action="upload"]').forEach(el=>el.onclick=()=>{if(!requireSignedIn("submit research"))return;state.uploadOpen=true;render()});
  app.querySelectorAll('[data-action="close-upload"]').forEach(el=>el.onclick=()=>{state.uploadOpen=false;render()});
  app.querySelectorAll('[data-integration]').forEach(el=>el.onclick=e=>{e.preventDefault();e.stopPropagation();state.integrationModal=el.dataset.integration;render()});
  app.querySelectorAll('[data-action="close-integration"]').forEach(el=>el.onclick=()=>{state.integrationModal=null;render()});
  app.querySelector('[data-action="disconnect-integration"]')?.addEventListener("click",e=>{const kind=e.currentTarget.dataset.kind;state.integrations[kind]={...state.integrations[kind],status:"disconnected"};state.integrationModal=null;persistPrototype();showToast("Local service configuration removed.")});
  const workflowActions={"new-workspace":"workspace","new-discussion":"discussion","new-conference":"conference","link-publication":"publication",filters:"filters","new-message":"message","edit-profile":"profile","new-collection":"collection","add-artifact":"artifact","new-presentation":"presentation","define-journal":"journalModel"};
  Object.entries(workflowActions).forEach(([action,type])=>app.querySelectorAll(`[data-action="${action}"]`).forEach(el=>el.onclick=e=>{e.preventDefault();e.stopPropagation();const protectedTypes=new Set(["workspace","discussion","conference","publication","message","profile","artifact","presentation","journalModel"]);if(protectedTypes.has(type)&&!requireSignedIn(type==="discussion"?"start a discussion":"save this research action"))return;if(type==="discussion")state.discussionContext=el.dataset.linkedPaper||state.selectedPaper?.id||null;state.workflowModal=type;render()}));
  app.querySelectorAll('[data-action="close-workflow"]').forEach(el=>el.onclick=()=>{state.workflowModal=null;render()});
  app.querySelectorAll('[data-action="close-citation"]').forEach(el=>el.onclick=()=>{state.citationPaper=null;render()});
  app.querySelectorAll('[data-citation-style]').forEach(el=>el.onclick=()=>{state.citationStyle=el.dataset.citationStyle;render()});
  app.querySelector('[data-action="copy-citation"]')?.addEventListener("click",()=>{const paper=paperById(state.citationPaper);if(paper)void copyText(citationVariants(paper)[state.citationStyle],"Citation")});
  app.querySelector('[data-action="download-bibtex"]')?.addEventListener("click",()=>{const paper=paperById(state.citationPaper);if(!paper)return;downloadText(`${paper.id.replace(/[^a-z0-9]+/gi,"-")}.bib`,citationVariants(paper).bibtex,"application/x-bibtex");showToast("BibTeX citation downloaded.")});
  app.querySelectorAll('[data-action="close-share"]').forEach(el=>el.onclick=()=>{state.shareTarget=null;render()});
  app.querySelector('[data-action="copy-share-link"]')?.addEventListener("click",()=>{if(state.shareTarget)void copyText(state.shareTarget.url,"Share link")});
  app.querySelector('[data-action="native-share"]')?.addEventListener("click",async()=>{const target=state.shareTarget;if(!target||!navigator.share)return;try{await navigator.share({title:target.title,text:target.text,url:target.url});state.shareTarget=null;render()}catch(error){if(error?.name!=="AbortError")showToast("Device sharing was not available.","error")}});
  app.querySelector('[data-action="toggle-notifications"]')?.addEventListener("click",()=>{state.notificationOpen=!state.notificationOpen;render()});
  app.querySelector('[data-action="mark-notifications-read"]')?.addEventListener("click",async()=>{state.notifications.forEach(item=>item.read=true);render();try{await apiRequest("/accounts/notifications/read-all",{method:"POST"})}catch(error){showToast(error.message||"Could not mark notifications read.","error")}});
  app.querySelectorAll('[data-action="open-auth"]').forEach(el=>el.onclick=()=>{state.authModal="login";state.notificationOpen=false;render()});
  app.querySelectorAll('[data-action="close-auth"]').forEach(el=>el.onclick=()=>{state.authModal=null;render()});
  app.querySelectorAll('[data-auth-switch]').forEach(el=>el.onclick=()=>{state.authModal=el.dataset.authSwitch;render()});
  app.querySelector('[data-action="logout"]')?.addEventListener("click",()=>{void handleLogout()});
  app.querySelector('[data-action="back-workspaces"]')?.addEventListener("click",()=>{state.selectedWorkspace=null;state.page="workspaces";render()});
  app.querySelector('[data-action="back-discussions"]')?.addEventListener("click",()=>{state.selectedDiscussion=null;state.page="discussions";setRouteHash("","");render()});
  app.querySelector('[data-action="back-presentations"]')?.addEventListener("click",()=>{state.selectedPresentation=null;state.page="presentations";render()});
  app.querySelector('[data-action="back-conferences"]')?.addEventListener("click",()=>{state.selectedConference=null;state.page="conferences";render()});
  app.querySelector('[data-action="back-journals"]')?.addEventListener("click",()=>{state.selectedJournal=null;state.page="journals";render()});
  app.querySelector('[data-action="back"]')?.addEventListener("click",()=>{state.selectedPaper=null;setRouteHash("","");render()});
  app.querySelectorAll('[data-presentation-open]').forEach(el=>el.onclick=()=>{clearSelections();state.selectedPresentation=Number(el.dataset.presentationOpen);render()});
  app.querySelectorAll('[data-conference-open]').forEach(el=>el.onclick=()=>{clearSelections();state.selectedConference=Number(el.dataset.conferenceOpen);render()});
  app.querySelectorAll('[data-journal-open]').forEach(el=>el.onclick=()=>{clearSelections();state.selectedJournal=Number(el.dataset.journalOpen);render()});
  app.querySelectorAll('[data-copy-doi]').forEach(el=>el.onclick=()=>{if(el.dataset.copyDoi&&el.dataset.copyDoi!=="Pending")void copyText(el.dataset.copyDoi,"DOI")});
  app.querySelectorAll('[data-paper-reply]').forEach(el=>el.onclick=()=>{const field=app.querySelector('[data-comment-form] textarea');if(!field)return;field.value=`@${el.dataset.paperReply} `;field.focus();field.scrollIntoView({behavior:"smooth",block:"center"})});
  app.querySelectorAll('[data-presentation-export]').forEach(el=>el.onclick=()=>{const presentation=presentations[Number(el.dataset.presentationExport)];const blob=new Blob([JSON.stringify(presentation,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob);const link=document.createElement("a");link.href=url;link.download=`${presentation.title.toLowerCase().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"")||"presentation"}.json`;link.click();URL.revokeObjectURL(url);showToast("Presentation metadata exported.")});
  app.querySelector(".site-search input")?.addEventListener("input",e=>{state.query=e.target.value;state.selectedPaper=null;state.page="home";render();requestAnimationFrame(()=>{const i=app.querySelector(".site-search input");i?.focus();i?.setSelectionRange(i.value.length,i.value.length)})});
  app.querySelector('[data-conversation-search]')?.addEventListener("input",e=>{const query=e.target.value.toLowerCase();app.querySelectorAll(".conversation").forEach(item=>item.hidden=!item.textContent.toLowerCase().includes(query))});
  app.querySelector('[data-submission-form]')?.addEventListener("submit",handleSubmission);
  app.querySelector('[data-comment-form]')?.addEventListener("submit",handleComment);
  app.querySelector('[data-discussion-reply]')?.addEventListener("submit",handleDiscussionReply);
  app.querySelector('[data-integration-form]')?.addEventListener("submit",handleIntegration);
  app.querySelector('[data-workflow-form]')?.addEventListener("submit",handleWorkflow);
  app.querySelector('[data-share-form]')?.addEventListener("submit",handleShareSubmit);
  app.querySelector('[data-auth-form]')?.addEventListener("submit",handleAuth);
  app.querySelector('[data-message-form]')?.addEventListener("submit",async e=>{e.preventDefault();const form=e.currentTarget;const content=new FormData(form).get("message").trim();const conversationId=form.dataset.conversationId;if(!content||!conversationId)return;form.querySelectorAll("button,textarea").forEach(control=>control.disabled=true);try{appendConversationMessage(await apiRequest(`/social/conversations/${encodeURIComponent(conversationId)}/messages`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({body:content})}));render();requestAnimationFrame(()=>{const history=app.querySelector(".message-history");if(history)history.scrollTop=history.scrollHeight})}catch(error){form.querySelectorAll("button,textarea").forEach(control=>control.disabled=false);showToast(error.message||"Could not send this message.","error")}});
  document.onkeydown=e=>{
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();app.querySelector(".site-search input")?.focus();return;}
    if(e.key!=="Escape")return;
    if(state.authModal){state.authModal=null;render()}else if(state.shareTarget){state.shareTarget=null;render()}else if(state.citationPaper){state.citationPaper=null;render()}else if(state.integrationModal){state.integrationModal=null;render()}else if(state.workflowModal){state.workflowModal=null;render()}else if(state.uploadOpen){state.uploadOpen=false;render()}else if(state.notificationOpen){state.notificationOpen=false;render()}else if(state.mobileNavOpen){state.mobileNavOpen=false;render()}else if(state.mobileConversationOpen){state.mobileConversationOpen=false;render()}
  };
}

render();
window.addEventListener("hashchange",()=>{void routeFromHash()});
void initializeFrontend();
