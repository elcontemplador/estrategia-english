(() => {
  const search = document.querySelector('#search');
  if (search) {
    const topic = document.querySelector('#topic');
    const year = document.querySelector('#year');
    const cards = [...document.querySelectorAll('[data-essay]')];
    const count = document.querySelector('#result-count');
    const empty = document.querySelector('#empty-results');
    const normalise = text => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    function filter() {
      const terms = normalise(search.value.trim()).split(/\s+/).filter(Boolean);
      let visible = 0;
      for (const card of cards) {
        const match = terms.every(term => normalise(card.dataset.search).includes(term))
          && (!topic.value || card.dataset.topics.split(' ').includes(topic.value))
          && (!year.value || card.dataset.year === year.value);
        card.hidden = !match;
        if (match) visible++;
      }
      count.textContent = visible + (visible === 1 ? ' essay' : ' essays') + ' shown';
      empty.hidden = visible !== 0;
    }
    search.addEventListener('input', filter);
    topic.addEventListener('change', filter);
    year.addEventListener('change', filter);
    filter();
  }
  for (const button of document.querySelectorAll('[data-copy]')) {
    button.addEventListener('click', async () => {
      const text = document.getElementById(button.dataset.copy).textContent.trim();
      const status = button.parentElement.querySelector('[role="status"]');
      try {
        await navigator.clipboard.writeText(text);
        status.textContent = 'Citation copied.';
      } catch (_) {
        status.textContent = 'Select the citation above to copy it.';
      }
    });
  }
})();
