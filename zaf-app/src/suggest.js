/**
 * suggest.js — handles backend communication and rendering suggestion results.
 * Depends on ZAFClient being available (set on window.ZAFClient by app.js).
 */

/* global ZAFClient */

/**
 * Call the backend /suggest endpoint via ZAF's client.request().
 * ZAF sandboxes direct fetch() calls to external domains, so all HTTP
 * requests to the backend must go through client.request().
 *
 * @param {object} client - ZAF client instance
 * @param {string} backendUrl - The backend /suggest URL from app settings
 * @param {object} payload - { ticket_id, current_message, ticket_tags }
 * @returns {Promise<object>} - API response JSON
 */
async function fetchSuggestion(client, backendUrl, payload) {
  const response = await client.request({
    url: backendUrl,
    type: 'POST',
    contentType: 'application/json',
    data: JSON.stringify(payload),
    secure: false,
  });
  return response;
}

/**
 * Render a successful suggestion into the DOM.
 * @param {object} result - API response with suggestion, sources, is_workflow_question
 */
function renderSuggestion(result) {
  if (!result.is_workflow_question) {
    showState('inactive');
    return;
  }

  if (!result.suggestion) {
    showState('inactive');
    return;
  }

  document.getElementById('suggestion-text').textContent = result.suggestion;

  // Render sources
  const sourcesList = document.getElementById('sources-list');
  sourcesList.innerHTML = '';
  (result.sources || []).forEach((src) => {
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = src.url || '#';
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = src.title || src.source_id || 'Source';
    const typeSpan = document.createElement('span');
    typeSpan.className = 'source-type';
    typeSpan.textContent = `(${src.source_type || 'unknown'})`;
    li.appendChild(a);
    li.appendChild(typeSpan);
    sourcesList.appendChild(li);
  });

  // Show/hide sources section based on availability
  const sourcesDetails = document.getElementById('sources-details');
  sourcesDetails.style.display = result.sources && result.sources.length ? '' : 'none';

  showState('suggestion');
}

/**
 * Show one of the four UI states: 'inactive' | 'loading' | 'suggestion' | 'error'
 */
function showState(stateName) {
  const states = ['inactive', 'loading', 'suggestion', 'error'];
  states.forEach((s) => {
    const el = document.getElementById(`state-${s}`);
    if (el) el.classList.toggle('hidden', s !== stateName);
  });
}

/**
 * Set up the copy button behaviour.
 */
function initCopyButton() {
  const btn = document.getElementById('btn-copy');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const text = document.getElementById('suggestion-text').textContent;
    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'Copy suggestion';
        btn.classList.remove('copied');
      }, 2000);
    });
  });
}

// Export for use in app.js
window.SuggestUI = { fetchSuggestion, renderSuggestion, showState, initCopyButton };
