const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}

function clear(element) { while (element.firstChild) element.removeChild(element.firstChild); }

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type': 'application/json'}, ...options});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  window.setTimeout(() => element.classList.remove('show'), 2800);
}

function setView(name) {
  $$('.tab').forEach((tab) => tab.classList.toggle('active', tab.dataset.view === name));
  $$('.view').forEach((view) => view.classList.toggle('active', view.id === `view-${name}`));
  history.replaceState(null, '', `#${name}`);
  if (name === 'sources') loadSources();
}

$$('.tab').forEach((tab) => tab.addEventListener('click', () => setView(tab.dataset.view)));
$('.brand').addEventListener('click', (event) => { event.preventDefault(); setView('search'); });

function badge(text, kind = '') {
  return node('span', `badge ${kind}`, text || 'unverified');
}

function sourceLink(result) {
  if (!result.source_url) return node('span', '', result.source_name || result.source);
  const link = node('a', '', result.source_name || result.source);
  link.href = result.source_url;
  link.target = '_blank';
  link.rel = 'noreferrer';
  return link;
}

function renderResults(results, query) {
  const container = $('#search-results');
  clear(container);
  container.className = 'result-list';
  $('#results-title').textContent = results.length ? `Matches for “${query}”` : `No local match for “${query}”`;
  $('#result-count').textContent = `${results.length} result${results.length === 1 ? '' : 's'}`;
  if (!results.length) {
    container.classList.add('empty-state');
    container.append(node('div', 'empty-icon', '—'), node('p', '', 'Try a shorter term, another domain, or add a glossary override.'));
    return;
  }
  results.forEach((result) => {
    const card = node('article', `result-card ${result.status === 'deprecated' ? 'deprecated' : ''}`);
    const line = node('div', 'term-line');
    const pair = node('div', 'term-pair');
    pair.append(node('p', 'source-term', result.source_term || '—'));
    const target = node('h3', 'target-term');
    target.append(node('span', '', result.target_term || 'No bilingual equivalent'));
    pair.append(target);
    line.append(pair);
    const score = node('span', 'badge', `${Math.round(result.score)} pts`);
    line.append(score);
    card.append(line);
    const badges = node('div', 'badges');
    badges.append(badge(result.status, result.status), badge(result.authority));
    if (result.domain) badges.append(badge(result.domain));
    if (result.match) badges.append(badge(result.match));
    card.append(badges);
    const meta = node('div', 'result-meta');
    const provenance = node('p');
    provenance.append('Source: ', sourceLink(result));
    if (result.usage_note) provenance.append(node('span', '', ` · ${result.usage_note}`));
    const details = node('button', 'detail-button', 'View evidence →');
    details.type = 'button';
    details.addEventListener('click', () => showDetails(result.source_term));
    meta.append(provenance, details);
    card.append(meta);
    container.append(card);
  });
}

async function search(event) {
  event?.preventDefault();
  const query = $('#search-query').value.trim();
  if (!query) return;
  const [from, to] = $('#search-direction').value.split('-');
  const params = new URLSearchParams({q: query, from, to, mode: $('#search-mode').value, limit: '16'});
  const domain = $('#search-domain').value;
  if (domain) params.set('domain', domain);
  const form = $('#search-form');
  form.classList.add('loading');
  try { renderResults(await api(`/api/search?${params}`), query); }
  catch (error) { toast(error.message); }
  finally { form.classList.remove('loading'); }
}

$('#search-form').addEventListener('submit', search);
$('#search-direction').addEventListener('change', () => { if ($('#search-query').value.trim()) search(); });
$('#search-domain').addEventListener('change', () => { if ($('#search-query').value.trim()) search(); });
$('#search-mode').addEventListener('change', () => { if ($('#search-query').value.trim()) search(); });

async function showDetails(term) {
  const [from, to] = $('#search-direction').value.split('-');
  const params = new URLSearchParams({q: term, from, to});
  if ($('#search-domain').value) params.set('domain', $('#search-domain').value);
  try {
    const detail = await api(`/api/explain?${params}`);
    $('#dialog-title').textContent = term;
    const content = $('#dialog-content');
    clear(content);
    if (detail.selected) {
      const summary = node('section', 'detail-section');
      summary.append(node('h3', '', 'Selected equivalent'), node('p', '', detail.selected.target_term || 'No bilingual equivalent'));
      const badges = node('div', 'badges');
      badges.append(badge(detail.selected.status, detail.selected.status), badge(detail.selected.authority));
      summary.append(badges);
      content.append(summary);
    }
    detail.details.forEach((record) => {
      const section = node('section', 'detail-section');
      section.append(node('h3', '', `Source record ${record.concept_id}`));
      if (record.definition_en) section.append(node('p', '', `EN: ${record.definition_en}`));
      if (record.definition_lv) section.append(node('p', '', `LV: ${record.definition_lv}`));
      const pre = node('pre', '', JSON.stringify(record.provenance_record, null, 2));
      section.append(pre);
      content.append(section);
    });
    $('#details-dialog').showModal();
  } catch (error) { toast(error.message); }
}

$('#dialog-close').addEventListener('click', () => $('#details-dialog').close());
$('#details-dialog').addEventListener('click', (event) => {
  if (event.target === $('#details-dialog')) $('#details-dialog').close();
});

$('#override-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  try {
    await api('/api/override', {method: 'POST', body: JSON.stringify(values)});
    $('#override-message').textContent = 'Saved locally.';
    form.reset();
    if ($('#search-query').value.trim()) search();
  } catch (error) { $('#override-message').textContent = error.message; }
});

$('#translate-source').addEventListener('input', (event) => {
  $('#source-count').textContent = `${event.target.value.length} characters`;
});

function renderTranslation(result) {
  const output = $('#translation-output');
  clear(output);
  output.className = '';
  if (result.sentence_suggestion) {
    const suggestion = node('section', 'suggestion');
    suggestion.append(node('strong', '', 'Exact translation-memory suggestion'), node('p', '', result.sentence_suggestion));
    output.append(suggestion);
  }
  const draft = node('section', 'draft-block');
  draft.append(node('h3', '', 'Terminology substitution preview'), node('p', '', result.draft));
  output.append(draft);
  if (result.choices.length) {
    const list = node('section', 'choice-list');
    list.append(node('h3', '', 'Recognized terminology'));
    result.choices.forEach((choice) => {
      const row = node('div', 'choice-row');
      row.append(node('span', '', choice.source), node('span', '', '→'), node('span', '', choice.target));
      list.append(row);
    });
    output.append(list);
  }
  if (result.translation_memory.length) {
    const memory = node('section', 'tm-block');
    memory.append(node('h3', '', 'Related sentence examples'));
    result.translation_memory.forEach((example) => {
      const card = node('div', 'tm-example');
      card.append(node('p', '', example.source_text), node('p', 'lv', example.target_text));
      memory.append(card);
    });
    output.append(memory);
  }
}

$('#translate-button').addEventListener('click', async () => {
  const text = $('#translate-source').value.trim();
  if (!text) return toast('Enter English source text first.');
  const button = $('#translate-button');
  button.disabled = true;
  button.textContent = 'Analyzing…';
  try {
    renderTranslation(await api('/api/translate-text', {method: 'POST', body: JSON.stringify({text, domain: $('#translate-domain').value})}));
  } catch (error) { toast(error.message); }
  finally { button.disabled = false; button.textContent = 'Analyze text'; }
});

function renderReview(result) {
  const output = $('#review-output');
  clear(output);
  const summary = node('div', `review-summary ${result.ok ? '' : 'has-issues'}`);
  summary.append(node('strong', '', result.ok ? 'No terminology issues found' : `${result.issues.length} issue${result.issues.length === 1 ? '' : 's'} found`));
  output.append(summary);
  result.issues.forEach((issue) => {
    const card = node('div', 'issue-card');
    card.append(node('strong', '', issue.type.replaceAll('_', ' ')));
    if (issue.source) card.append(node('p', '', `Source: ${issue.source}`));
    if (issue.expected) card.append(node('p', '', `Expected: ${issue.expected}`));
    if (issue.found) card.append(node('p', '', `Found: ${issue.found}`));
    if (issue.variants_found?.length) card.append(node('p', '', `Variants: ${issue.variants_found.join(', ')}`));
    output.append(card);
  });
}

async function runReview(endpoint) {
  const source = $('#review-source').value.trim();
  const target = $('#review-target').value.trim();
  if (!source || !target) return toast('Enter both source and translation.');
  try {
    renderReview(await api(endpoint, {method: 'POST', body: JSON.stringify({source, target, domain: $('#review-domain').value})}));
  } catch (error) { toast(error.message); }
}

$('#review-button').addEventListener('click', () => runReview('/api/review'));
$('#consistency-button').addEventListener('click', () => runReview('/api/consistency'));

let sourcesLoaded = false;
async function loadSources() {
  if (sourcesLoaded) return;
  try {
    const sources = await api('/api/sources');
    sourcesLoaded = true;
    $('#active-source-count').textContent = sources.filter((source) => source.active_release_id).length;
    const container = $('#source-list');
    clear(container);
    sources.forEach((source) => {
      const row = node('article', 'source-row');
      const main = node('div');
      const title = node('h3');
      if (source.homepage) {
        const link = sourceLink({source_url: source.homepage, source_name: source.name});
        title.append(link);
      } else title.textContent = source.name;
      main.append(title, node('p', '', source.notes || 'No additional notes.'));
      const evidence = node('div');
      evidence.append(node('span', 'label', 'Authority'), node('p', '', source.authority), node('span', 'label', 'Licence'), node('p', '', source.license_name || 'Not verified'));
      const release = node('div');
      release.append(node('span', 'label', 'Active release'), node('p', '', source.active_version || 'Not imported'), node('span', 'label', 'Records'), node('p', '', source.record_count?.toLocaleString() || '—'));
      row.append(main, evidence, release);
      container.append(row);
    });
  } catch (error) { toast(error.message); }
}

api('/api/health').then((health) => {
  $('#health').lastChild.textContent = ` Local database · ${health.sources} sources`;
}).catch(() => {
  $('#health').classList.add('error');
  $('#health').lastChild.textContent = ' Database unavailable';
});

const initialView = location.hash.slice(1);
if (['search', 'translate', 'review', 'sources'].includes(initialView)) setView(initialView);
