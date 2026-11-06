() => {
  const visible = e => !!(e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden');
  const text = e => (e?.innerText || e?.textContent || '').replace(/\s+/g, ' ').trim();
  const tables = [...document.querySelectorAll('table')].filter(visible).map(table => ({
    headers: [...table.querySelectorAll('thead th')].map(text),
    rows: [...table.querySelectorAll('tbody tr')].slice(0, 200).map(row => ({
      id: row.getAttribute('data-value') || '',
      cells: [...row.querySelectorAll('td')].map(text),
      own: !!row.querySelector('.CyberSkylineGradient')
    }))
  }));
  return {
    title: text([...document.querySelectorAll('h2')].find(visible)),
    statuses: [...document.querySelectorAll('[role="status"]')].filter(visible).map(text),
    filters: [...document.querySelectorAll('[role="combobox"]')].filter(visible).map(text),
    selected: [...document.querySelectorAll('[role="tab"][aria-selected="true"]')].filter(visible).map(text),
    tables,
    login: !!document.querySelector('input[type="password"]'),
    notice: [...document.querySelectorAll('[role="alert"], .ui.message')].filter(visible).map(text).join(' ').slice(0, 1000)
  };
}
