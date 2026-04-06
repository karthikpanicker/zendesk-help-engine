/**
 * app.js — ZAF event wiring.
 *
 * Lifecycle:
 * 1. ZAFClient.init() → client
 * 2. app.activated → read ticket context (id, tags)
 * 3. ticket.tags.changed → re-evaluate panel visibility
 * 4. ticket.conversation.message.created → if customer message + workflow tag → fetch suggestion
 */

/* global ZAFClient */

(function () {
  'use strict';

  const { fetchSuggestion, renderSuggestion, showState, initCopyButton } = window.SuggestUI;

  const client = ZAFClient.init();

  let currentTicketId = null;
  let currentTags = [];
  let backendUrl = null;
  let workflowTagSet = new Set();

  // ---------------------------------------------------------------------------
  // Bootstrap
  // ---------------------------------------------------------------------------

  client.on('app.activated', async () => {
    initCopyButton();

    // Read backend URL from app install parameters
    const meta = await client.metadata();
    backendUrl = (meta.settings && meta.settings.backendUrl) || 'http://localhost:8000/suggest';

    // Read initial ticket context
    await refreshTicketContext();
  });

  // Re-evaluate when tags change mid-ticket (agent may add a workflow tag)
  client.on('ticket.tags.changed', async () => {
    await refreshTicketContext();
  });

  // Fire on every new message in the conversation
  client.on('ticket.conversation.message.created', async (data) => {
    // Only act on customer (end-user) messages
    const isEndUser =
      data &&
      data.message &&
      data.message.author &&
      data.message.author.type === 'end_user';

    if (!isEndUser) return;

    const messageText =
      (data.message.content && data.message.content.text) || '';
    if (!messageText.trim()) return;

    if (!isWorkflowTicket()) {
      showState('inactive');
      return;
    }

    await requestSuggestion(messageText);
  });

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  async function refreshTicketContext() {
    try {
      const data = await client.get(['ticket.id', 'ticket.tags']);
      currentTicketId = data['ticket.id'];
      currentTags = data['ticket.tags'] || [];
    } catch (e) {
      console.warn('[WorkflowAssistant] Could not read ticket context:', e);
      currentTags = [];
    }

    if (isWorkflowTicket()) {
      // Keep whatever state was last shown; don't reset to inactive if suggestion is visible
      const suggestionEl = document.getElementById('state-suggestion');
      const isShowingSuggestion = suggestionEl && !suggestionEl.classList.contains('hidden');
      if (!isShowingSuggestion) {
        showState('inactive');
      }
    } else {
      showState('inactive');
    }
  }

  function isWorkflowTicket() {
    // The workflow tag list is baked into the install parameter or can be
    // compared against any known workflow tags.
    // For simplicity we consider any ticket that matched the backend's tag
    // logic. We use a broad check: if the backend returns is_workflow_question=true.
    // But we also want to avoid calling the backend on non-workflow tickets,
    // so we keep a client-side heuristic using common tag substrings.
    const WORKFLOW_KEYWORDS = ['workflow', 'process', 'how-do-i', 'procedure'];
    return currentTags.some((tag) =>
      WORKFLOW_KEYWORDS.some((kw) => tag.toLowerCase().includes(kw))
    );
  }

  async function requestSuggestion(messageText) {
    showState('loading');

    // Resize the app iframe to show the loading spinner
    client.invoke('resize', { width: '100%', height: '120px' });

    try {
      const result = await fetchSuggestion(client, backendUrl, {
        ticket_id: String(currentTicketId),
        current_message: messageText,
        ticket_tags: currentTags,
      });

      renderSuggestion(result);

      // Resize to fit suggestion card
      client.invoke('resize', { width: '100%', height: '280px' });
    } catch (err) {
      console.error('[WorkflowAssistant] Suggestion request failed:', err);
      document.getElementById('error-msg').textContent =
        'Could not reach the suggestion backend. Check your backend URL in app settings.';
      showState('error');
      client.invoke('resize', { width: '100%', height: '80px' });
    }
  }
})();
