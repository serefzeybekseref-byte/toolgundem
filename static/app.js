// Theme toggle
const themeToggle = document.getElementById('theme-toggle');
const html = document.documentElement;

// Check saved preference or system preference
const savedTheme = localStorage.getItem('theme');
if (savedTheme) {
  html.setAttribute('data-theme', savedTheme);
} else if (window.matchMedia('(prefers-color-scheme: light)').matches) {
  html.setAttribute('data-theme', 'light');
}

function toggleTheme() {
  const current = html.getAttribute('data-theme');
  const next = current === 'light' ? 'dark' : 'light';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
  updateThemeIcon();
}

function updateThemeIcon() {
  if (!themeToggle) return;
  const isDark = html.getAttribute('data-theme') !== 'light';
  themeToggle.innerHTML = isDark ? '☀️' : '🌙';
}

if (themeToggle) {
  themeToggle.addEventListener('click', toggleTheme);
}
updateThemeIcon();

// Load More button
const loadMoreBtn = document.getElementById('load-more');
let currentPage = 1;

if (loadMoreBtn) {
  loadMoreBtn.addEventListener('click', async () => {
    currentPage++;
    const topic = loadMoreBtn.dataset.topic || '';
    const url = `/api/products?page=${currentPage}&per_page=20${topic ? '&topic=' + topic : ''}`;
    
    loadMoreBtn.textContent = 'Yükleniyor...';
    loadMoreBtn.disabled = true;
    
    try {
      const resp = await fetch(url);
      const data = await resp.json();
      
      const grid = document.getElementById('products-grid');
      if (grid && data.products.length > 0) {
        data.products.forEach(p => {
          const card = createProductCard(p);
          grid.insertAdjacentHTML('beforeend', card);
        });
      }
      
      if (!data.has_more) {
        loadMoreBtn.style.display = 'none';
      } else {
        loadMoreBtn.textContent = 'Daha Fazla Yükle';
        loadMoreBtn.disabled = false;
      }
    } catch (err) {
      loadMoreBtn.textContent = 'Daha Fazla Yükle';
      loadMoreBtn.disabled = false;
    }
  });
}

function createProductCard(p) {
  const tags = (p.tags || '').split(',').filter(t => t).slice(0, 2);
  const tagHtml = tags.map(t => `<span class="tag">${t.trim()}</span>`).join('');
  return `
    <a class="tool-card fade-in" href="/urun/${p.slug}">
      ${p.thumbnail ? `<div class="tool-card-img"><img src="${p.thumbnail}" alt="${p.original_name}" loading="lazy"></div>` : ''}
      <div class="tool-card-body">
        <h3 class="tool-card-title">${p.original_name}</h3>
        <p class="tool-card-summary">${p.summary_tr || ''}</p>
        <div class="tool-card-footer">
          <div class="tool-card-tags">${tagHtml}</div>
          <div class="tool-card-votes">▲ ${p.votes || 0}</div>
        </div>
      </div>
    </a>
  `;
}

// Search - debounced input
const searchInput = document.getElementById('search-input');
const searchForm = document.getElementById('search-form');

if (searchInput && searchForm) {
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      searchForm.submit();
    }
  });
}

// Scroll to top button
const scrollBtn = document.getElementById('scroll-top');
if (scrollBtn) {
  window.addEventListener('scroll', () => {
    if (window.scrollY > 500) {
      scrollBtn.classList.add('visible');
    } else {
      scrollBtn.classList.remove('visible');
    }
  });
  scrollBtn.addEventListener('click', () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
}

// Fade-in animation on scroll
const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
    }
  });
}, { threshold: 0.1 });

document.querySelectorAll('.fade-in').forEach(el => observer.observe(el));

// AI Advisor Logic
const advisorForm = document.getElementById('ai-advisor-form');
if (advisorForm) {
  advisorForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = document.getElementById('advisor-input');
    const submitBtn = document.getElementById('advisor-submit');
    const resultsDiv = document.getElementById('advisor-results');
    const messageDiv = document.getElementById('advisor-message');
    const toolsDiv = document.getElementById('advisor-tools');
    
    const query = input.value.trim();
    if (!query) return;
    
    // UI Loading state
    submitBtn.textContent = 'Düşünüyor...';
    submitBtn.disabled = true;
    resultsDiv.style.display = 'block';
    messageDiv.textContent = '🤖 Veritabanı taranıyor ve analiz ediliyor...';
    toolsDiv.innerHTML = '';
    
    try {
      const resp = await fetch('/api/advisor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      });
      
      const data = await resp.json();
      messageDiv.textContent = data.message || 'İşte önerilerim:';
      
      if (data.tools && data.tools.length > 0) {
        toolsDiv.innerHTML = data.tools.map(t => `
          <a href="/urun/${t.slug}" style="display: flex; align-items: flex-start; gap: 12px; padding: 12px; background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-md); text-decoration: none; color: inherit; transition: border-color 0.2s;">
            <div style="flex: 1;">
              <h4 style="color: var(--accent); margin-bottom: 4px;">${t.original_name}</h4>
              <p style="font-size: 0.85rem; color: var(--text-secondary);">${t.summary_tr}</p>
            </div>
            <div style="font-family: var(--font-mono); font-size: 0.8rem; background: var(--surface-hover); padding: 4px 8px; border-radius: var(--radius-sm);">▲ ${t.votes}</div>
          </a>
        `).join('');
      } else {
        toolsDiv.innerHTML = '<p style="font-size: 0.9rem; color: var(--text-secondary);">Üzgünüm, bu spesifik ihtiyaca uygun bir araç bulamadım.</p>';
      }
      
    } catch (err) {
      messageDiv.textContent = 'Bir hata oluştu. Lütfen tekrar deneyin.';
    } finally {
      submitBtn.textContent = 'Danış';
      submitBtn.disabled = false;
    }
  });
}
