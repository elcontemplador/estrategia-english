(() => {
  'use strict';

  const normalise = value => String(value || '').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').toLowerCase();

  function enhanceArchive() {
    const list = document.querySelector('#archive-list[data-search-index]');
    const form = document.querySelector('#archive-filters');
    const search = document.querySelector('#search');
    const topic = document.querySelector('#topic');
    const year = document.querySelector('#year');
    const genre = document.querySelector('#genre');
    const sort = document.querySelector('#sort');
    const clear = document.querySelector('#clear-filters');
    const more = document.querySelector('#load-more');
    const count = document.querySelector('#result-count');
    const empty = document.querySelector('#empty-results');
    const status = document.querySelector('#search-status');
    // An incomplete contract must leave the server-rendered archive readable.
    if (![list, form, search, topic, year, genre, sort, clear, more, count, empty, status].every(Boolean)) return;

    const cards = [...list.querySelectorAll('article[data-essay][data-id][data-search]')]
      .map((element, position) => ({
        element, position, id: element.dataset.id,
        metadata: normalise(element.dataset.search),
        title: element.querySelector('h2')?.textContent.trim() || '',
        topics: (element.dataset.topics || '').split(/\s+/),
        year: element.dataset.year || '', genre: element.dataset.genre || '',
        number: Number(element.dataset.number) || 0,
      }));
    const pageSize = 24;
    let limit = pageSize;
    let matches = [];
    let currentSort = '';
    let fullText = null;
    let indexRequest = null;
    let indexFailed = false;
    let searchTimer;
    let printing = false;
    const collator = new Intl.Collator('en', { sensitivity: 'base', numeric: true });
    const statusMessage = document.createElement('span');
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'button search-retry';
    retry.textContent = 'Retry full-text search';
    retry.hidden = true;
    status.replaceChildren(statusMessage, document.createTextNode(' '), retry);
    status.setAttribute('role', 'status');
    count.setAttribute('role', 'status');
    const validOption = (select, value) => [...select.options]
      .some(option => option.value === value && !option.disabled);
    const selected = select => validOption(select, select.value) ? select.value : '';
    const terms = () => normalise(search.value.trim()).split(/\s+/).filter(Boolean);
    const state = () => ({
      q: search.value.trim(), topic: selected(topic), year: selected(year),
      genre: selected(genre), sort: ['newest', 'oldest', 'title'].includes(sort.value) ? sort.value : 'newest',
    });

    function readURL() {
      const params = new URL(window.location.href).searchParams;
      search.value = params.get('q') || '';
      for (const [key, select] of [['topic', topic], ['year', year], ['genre', genre]]) {
        const value = params.get(key) || '';
        select.value = validOption(select, value) ? value : '';
      }
      const value = params.get('sort');
      sort.value = ['newest', 'oldest', 'title'].includes(value) && validOption(sort, value) ? value : 'newest';
      const saved = window.history.state?.estrategiaArchive?.shown;
      limit = Number.isSafeInteger(saved) && saved >= pageSize ? Math.min(saved, Math.max(pageSize, cards.length)) : pageSize;
    }

    function writeURL(method) {
      const url = new URL(window.location.href);
      for (const [key, value] of Object.entries(state())) {
        if (value && !(key === 'sort' && value === 'newest')) url.searchParams.set(key, value);
        else url.searchParams.delete(key);
      }
      const previous = window.history.state;
      const next = { ...(previous && typeof previous === 'object' ? previous : {}), estrategiaArchive: { shown: limit } };
      try {
        window.history[method === 'push' && url.href !== window.location.href ? 'pushState' : 'replaceState'](next, '', url);
      } catch (_) { /* History may be unavailable in embedded or file previews. */ }
    }

    function updateSearchStatus() {
      const searching = terms().length > 0;
      retry.hidden = !searching || !indexFailed;
      if (!searching) statusMessage.textContent = '';
      else if (indexRequest) statusMessage.textContent = 'Loading full-text search. Showing matches in titles, authors and summaries for now.';
      else if (indexFailed) statusMessage.textContent = 'Full-text search is unavailable. Searching titles, authors and summaries only.';
      else if (fullText) statusMessage.textContent = 'Searching the complete essay texts, titles, authors and summaries.';
      else statusMessage.textContent = 'Searching titles, authors and summaries while full-text search starts.';
      list.setAttribute('aria-busy', String(searching && Boolean(indexRequest)));
    }

    function render() {
      const filters = state();
      const query = terms();
      const ordered = [...cards].sort((a, b) => {
        if (filters.sort === 'title') return collator.compare(a.title, b.title) || a.position - b.position;
        return (filters.sort === 'oldest' ? a.number - b.number : b.number - a.number) || a.position - b.position;
      });
      // Do not detach focused links on filtering or loading another page.
      if (currentSort !== filters.sort) {
        const fragment = document.createDocumentFragment();
        ordered.forEach(card => fragment.append(card.element));
        list.append(fragment);
        currentSort = filters.sort;
      }
      matches = ordered.filter(card => query.every(term => (fullText?.get(card.id) || card.metadata).includes(term))
        && (!filters.topic || card.topics.includes(filters.topic))
        && (!filters.year || card.year === filters.year)
        && (!filters.genre || card.genre === filters.genre));
      const visible = new Set(matches.slice(0, limit));
      const focused = document.activeElement;
      let focusHidden = false;
      cards.forEach(card => {
        card.element.hidden = !printing && !visible.has(card);
        if (card.element.hidden && card.element.contains(focused)) focusHidden = true;
      });
      if (focusHidden) search.focus({ preventScroll: true });
      const shown = Math.min(limit, matches.length);
      count.textContent = matches.length + (matches.length === 1 ? ' essay matches' : ' essays match') + '; ' + shown + ' shown.';
      empty.hidden = matches.length !== 0;
      more.hidden = shown >= matches.length;
      more.textContent = 'Show ' + Math.min(pageSize, matches.length - shown) + ' more essays';
      clear.disabled = !filters.q && !filters.topic && !filters.year && !filters.genre && filters.sort === 'newest';
      updateSearchStatus();
    }

    async function loadIndex() {
      if (fullText || indexRequest || !terms().length) return;
      indexFailed = false;
      const request = (async () => {
        const url = new URL(list.dataset.searchIndex, window.location.href);
        if (url.origin !== window.location.origin) throw new Error('Search index must be local.');
        const response = await fetch(url, { credentials: 'same-origin' });
        if (!response.ok) throw new Error('Search index unavailable.');
        const payload = await response.json();
        if (!Array.isArray(payload.articles)) throw new Error('Invalid search index.');
        const indexed = new Map();
        for (const article of payload.articles) {
          if (article && article.id != null && typeof article.text === 'string') indexed.set(String(article.id), article.text);
        }
        if (cards.some(card => !indexed.has(card.id))) throw new Error('Incomplete search index.');
        return new Map(cards.map(card => [card.id, card.metadata + ' ' + normalise(indexed.get(card.id))]));
      })();
      indexRequest = request;
      updateSearchStatus();
      try { fullText = await request; }
      catch (_) { indexFailed = true; }
      finally { indexRequest = null; render(); }
    }

    function apply(method, immediate = false) {
      window.clearTimeout(searchTimer);
      limit = pageSize;
      writeURL(method);
      render();
      if (terms().length && !fullText && !indexFailed) {
        if (immediate) void loadIndex();
        else searchTimer = window.setTimeout(loadIndex, 180);
      }
    }
    search.addEventListener('input', () => apply('replace'));
    for (const select of [topic, year, genre, sort]) select.addEventListener('change', () => apply('push', true));
    form.addEventListener('submit', event => { event.preventDefault(); apply('replace', true); });
    clear.addEventListener('click', event => {
      event.preventDefault();
      search.value = ''; topic.value = ''; year.value = ''; genre.value = ''; sort.value = 'newest';
      apply('push');
      search.focus({ preventScroll: true });
    });
    retry.addEventListener('click', () => {
      search.focus({ preventScroll: true });
      void loadIndex();
    });
    more.addEventListener('click', event => {
      event.preventDefault();
      const firstNew = matches[limit];
      limit += pageSize;
      render();
      writeURL('replace');
      if (firstNew) {
        const target = firstNew.element.querySelector('h2 a') || firstNew.element;
        if (!target.matches('a[href], button, [tabindex]')) target.tabIndex = -1;
        target.focus({ preventScroll: true });
        target.scrollIntoView({ block: 'nearest', behavior: 'instant' });
      }
    });
    window.addEventListener('popstate', () => {
      window.clearTimeout(searchTimer);
      readURL(); render();
      if (!indexFailed) void loadIndex();
    });
    window.addEventListener('beforeprint', () => { printing = true; render(); });
    window.addEventListener('afterprint', () => { printing = false; render(); });
    readURL();
    render();
    writeURL('replace');
    for (const control of [search, topic, year, genre, sort]) control.disabled = false;
    form.setAttribute('aria-busy', 'false');
    form.hidden = false;
    if (terms().length) void loadIndex();
  }

  function enhanceCitations() {
    for (const button of document.querySelectorAll('[data-copy]')) {
      button.hidden = false;
      button.addEventListener('click', async () => {
        const citation = document.getElementById(button.dataset.copy);
        let status = button.parentElement.querySelector('[role="status"]');
        if (!status) {
          status = document.createElement('span');
          status.className = 'status'; status.setAttribute('role', 'status');
          button.after(status);
        }
        status.textContent = '';
        if (!citation) { status.textContent = 'The citation could not be found.'; return; }
        button.disabled = true;
        try {
          await navigator.clipboard.writeText(citation.textContent.trim());
          status.textContent = 'Citation copied.';
        } catch (_) {
          const selection = window.getSelection();
          if (selection) {
            const range = document.createRange();
            range.selectNodeContents(citation); selection.removeAllRanges(); selection.addRange(range);
          }
          status.textContent = 'Automatic copying is unavailable. The citation is selected; use your browser or device copy command.';
        } finally { button.disabled = false; }
      });
    }
  }

  function enhanceReading() {
    for (const toc of document.querySelectorAll('details.reading-toc')) {
      // Save space on arrival at a small screen; native summary stays available.
      // Later viewport changes must not override a reader's explicit choice.
      if (window.matchMedia('(max-width: 900px)').matches) toc.open = false;
      toc.addEventListener('click', event => {
        const link = event.target.closest('a[href^="#"]');
        if (!link || event.defaultPrevented || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
        if (window.matchMedia('(max-width: 900px)').matches) toc.open = false;
      });
    }
    const progress = document.querySelector('#reading-progress');
    const article = document.querySelector('.article-body');
    if (progress && article) {
      progress.setAttribute('aria-hidden', 'true');
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
      let scheduled = false;
      const update = () => {
        scheduled = false;
        const rect = article.getBoundingClientRect();
        const distance = rect.height - window.innerHeight;
        const value = distance > 0 ? Math.min(1, Math.max(0, -rect.top / distance)) : (rect.top <= 0 ? 1 : 0);
        progress.style.transform = 'scaleX(' + value + ')';
        progress.style.transformOrigin = 'left';
        if (reducedMotion.matches) progress.style.transition = 'none';
        else progress.style.removeProperty('transition');
      };
      const schedule = () => { if (!scheduled) { scheduled = true; window.requestAnimationFrame(update); } };
      window.addEventListener('scroll', schedule, { passive: true });
      window.addEventListener('resize', schedule);
      window.addEventListener('load', schedule);
      reducedMotion.addEventListener('change', schedule);
      if ('ResizeObserver' in window) new ResizeObserver(schedule).observe(article);
      schedule();
    }
  }

  function enhanceImages() {
    const dialog = document.querySelector('dialog#image-viewer');
    const image = document.querySelector('#viewer-image');
    const caption = document.querySelector('#viewer-caption');
    const close = document.querySelector('#viewer-close');
    if (!dialog || !image || !caption || !close || typeof dialog.showModal !== 'function') return;
    const sizeToggle = dialog.querySelector('#viewer-size-toggle');
    const viewport = dialog.querySelector('.viewer-scroll');
    const setSize = size => {
      dialog.dataset.size = size;
      if (sizeToggle) sizeToggle.textContent = size === 'fit' ? 'Original size' : 'Fit to width';
    };
    if (sizeToggle) sizeToggle.addEventListener('click', () => {
      setSize(dialog.dataset.size === 'original' ? 'fit' : 'original');
    });
    let opener;
    for (const button of document.querySelectorAll('button.image-zoom')) {
      button.hidden = false;
      button.addEventListener('click', () => {
        const original = button.querySelector('img') || button.closest('figure')?.querySelector('img');
        const source = button.dataset.image || original?.currentSrc || original?.src;
        if (!source) return;
        opener = button;
        image.alt = button.dataset.alt || original?.alt || button.dataset.caption || 'Enlarged article illustration';
        caption.textContent = button.dataset.caption || button.closest('figure')?.querySelector('figcaption')?.textContent || image.alt;
        image.src = source;
        setSize('fit');
        if (!dialog.open) dialog.showModal();
        if (viewport) { viewport.scrollTop = 0; viewport.scrollLeft = 0; }
        close.focus();
      });
    }
    close.addEventListener('click', () => dialog.close());
    dialog.addEventListener('close', () => { if (opener?.isConnected) opener.focus({ preventScroll: true }); });
    dialog.addEventListener('click', event => {
      const rect = dialog.getBoundingClientRect();
      if (event.target === dialog && (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) dialog.close();
    });
    image.addEventListener('error', () => { caption.textContent = 'This illustration could not be loaded. Close this viewer to return to the article.'; });
  }

  enhanceArchive();
  enhanceCitations();
  enhanceReading();
  enhanceImages();
})();
