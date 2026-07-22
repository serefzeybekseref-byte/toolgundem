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
let currentPricing = '';

function reloadGrid() {
  const grid = document.getElementById('products-grid');
  if (!grid || !loadMoreBtn) return;
  currentPage = 1;
  grid.innerHTML = '';
  loadMoreBtn.style.display = '';
  loadMoreBtn.dataset.pricing = currentPricing;
  fetchProducts(false);
}

async function fetchProducts(append) {
  const topic = loadMoreBtn.dataset.topic || '';
  const pricing = loadMoreBtn.dataset.pricing || '';
  const url = `/api/products?page=${currentPage}&per_page=20${topic ? '&topic=' + topic : ''}${pricing ? '&pricing=' + encodeURIComponent(pricing) : ''}`;

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
    } else if (grid && !append) {
      grid.innerHTML = '<p style="color: var(--text-secondary); padding: 24px 0;">Bu fiyat kategorisinde araç bulunamadı.</p>';
    }

    if (!data.has_more) {
      loadMoreBtn.style.display = 'none';
    } else {
      loadMoreBtn.textContent = 'Daha Fazla Yükle';
      loadMoreBtn.disabled = false;
      loadMoreBtn.style.display = '';
    }
  } catch (err) {
    loadMoreBtn.textContent = 'Daha Fazla Yükle';
    loadMoreBtn.disabled = false;
  }
}

if (loadMoreBtn) {
  loadMoreBtn.addEventListener('click', () => {
    currentPage++;
    fetchProducts(true);
  });
}

// Fiyat filtresi
const pricingFilterEls = document.querySelectorAll('.pricing-filter-btn');
if (pricingFilterEls.length && loadMoreBtn) {
  pricingFilterEls.forEach(btn => {
    btn.addEventListener('click', () => {
      pricingFilterEls.forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentPricing = btn.dataset.pricing || '';
      reloadGrid();
    });
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

// Search - debounced input + canli oneri dropdown'u
const searchInput = document.getElementById('search-input');
const searchForm = document.getElementById('search-form');
const searchSuggest = document.getElementById('search-suggest');

if (searchInput && searchForm) {
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      searchForm.submit();
    } else if (e.key === 'Escape') {
      hideSuggest();
    }
  });

  function hideSuggest() {
    if (searchSuggest) {
      searchSuggest.innerHTML = '';
      searchSuggest.classList.remove('active');
    }
  }

  function renderSuggest(results) {
    if (!searchSuggest) return;
    if (!results.length) {
      hideSuggest();
      return;
    }
    searchSuggest.innerHTML = results.map(p => `
      <a href="/urun/${p.slug}" class="search-suggest-item">
        ${p.thumbnail ? `<img src="${p.thumbnail}" alt="" class="search-suggest-thumb" loading="lazy">` : '<div class="search-suggest-thumb search-suggest-thumb-fallback">' + p.original_name[0].toUpperCase() + '</div>'}
        <div class="search-suggest-text">
          <div class="search-suggest-name">${p.original_name}</div>
          <div class="search-suggest-summary">${(p.summary_tr || '').slice(0, 70)}</div>
        </div>
      </a>
    `).join('');
    searchSuggest.classList.add('active');
  }

  let debounceTimer = null;
  let latestQuery = '';
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim();
    latestQuery = q;
    if (q.length < 2) {
      hideSuggest();
      return;
    }
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(async () => {
      try {
        const resp = await fetch(`/api/search-suggest?q=${encodeURIComponent(q)}`);
        const data = await resp.json();
        // Kullanici yazmaya devam ettiyse eski sonucu gosterme (race condition onlemi)
        if (q === latestQuery) {
          renderSuggest(data.results || []);
        }
      } catch (err) {
        hideSuggest();
      }
    }, 200);
  });

  // Kutu disina tiklaninca kapat
  document.addEventListener('click', (e) => {
    if (!searchForm.contains(e.target)) {
      hideSuggest();
    }
  });

  // Odaklaninca (ve zaten yazi varsa) tekrar goster
  searchInput.addEventListener('focus', () => {
    if (searchInput.value.trim().length >= 2 && searchSuggest.innerHTML) {
      searchSuggest.classList.add('active');
    }
  });

  // Ne aradigini net gostermek icin placeholder'i donguyle degistir (CTR icin kucuk ama etkili detay)
  const searchPlaceholders = [
    'Araç ara...', 'Kod yazmak için AI ara...', 'Logo oluştur...',
    'Video üret...', 'Sunum hazırla...', 'PDF özetle...', 'Müzik üret...',
  ];
  if (!searchInput.value) {
    let phIndex = 0;
    searchInput.setAttribute('placeholder', 'Araç ara...');
    setInterval(() => {
      if (document.activeElement === searchInput || searchInput.value) return;
      phIndex = (phIndex + 1) % searchPlaceholders.length;
      searchInput.setAttribute('placeholder', searchPlaceholders[phIndex]);
    }, 2600);
  }
}

// Gallery Lightbox (Product Hunt tarzi - ayri sayfaya gitmeden buyuk gorsel goster)
const galleryRoot = document.getElementById('gallery-root');
const lightboxOverlay = document.getElementById('lightbox-overlay');
const lightboxImg = document.getElementById('lightbox-img');
const lightboxClose = document.getElementById('lightbox-close');
const lightboxPrev = document.getElementById('lightbox-prev');
const lightboxNext = document.getElementById('lightbox-next');

if (galleryRoot && lightboxOverlay && lightboxImg) {
  const galleryLinks = Array.from(galleryRoot.querySelectorAll('.detail-gallery-item'));
  let currentIndex = 0;

  function openLightbox(index) {
    currentIndex = index;
    lightboxImg.src = galleryLinks[currentIndex].getAttribute('href');
    lightboxOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
    updateNavVisibility();
  }

  function closeLightbox() {
    lightboxOverlay.classList.remove('active');
    document.body.style.overflow = '';
  }

  function updateNavVisibility() {
    lightboxPrev.style.display = galleryLinks.length > 1 ? '' : 'none';
    lightboxNext.style.display = galleryLinks.length > 1 ? '' : 'none';
  }

  function showNext() {
    currentIndex = (currentIndex + 1) % galleryLinks.length;
    lightboxImg.src = galleryLinks[currentIndex].getAttribute('href');
  }

  function showPrev() {
    currentIndex = (currentIndex - 1 + galleryLinks.length) % galleryLinks.length;
    lightboxImg.src = galleryLinks[currentIndex].getAttribute('href');
  }

  galleryLinks.forEach((link, i) => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      openLightbox(i);
    });
  });

  lightboxClose.addEventListener('click', closeLightbox);
  lightboxNext.addEventListener('click', showNext);
  lightboxPrev.addEventListener('click', showPrev);

  // Arka plana (gorselin disina) tiklaninca da kapat
  lightboxOverlay.addEventListener('click', (e) => {
    if (e.target === lightboxOverlay) closeLightbox();
  });

  document.addEventListener('keydown', (e) => {
    if (!lightboxOverlay.classList.contains('active')) return;
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowRight') showNext();
    else if (e.key === 'ArrowLeft') showPrev();
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

// Cok kaynakli logo fallback zinciri: Google favicon -> DuckDuckGo icon -> harf rozeti.
// Yeni affiliate/editoryel urun eklerken tek tek logo yuklemeye gerek kalmasin diye
// otomatik calisir (Clearbit'in ucretsiz logo API'si Aralik 2025'te kapandi, tek
// kaynaga guvenmek yerine zincirleme fallback kullaniyoruz).
function logoFallback(imgEl, domain, letter) {
  if (!imgEl.dataset.fallbackStep) {
    imgEl.dataset.fallbackStep = "1";
    imgEl.src = `https://icons.duckduckgo.com/ip3/${domain}.ico`;
  } else {
    imgEl.outerHTML = `<span class="leaderboard-logo-fallback" style="width:28px;height:28px;font-size:0.8rem;flex-shrink:0;">${letter}</span>`;
  }
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

// Header: scroll sonrasi ince golge (sayfa icerigiyle ayrimi netlestirmek icin)
const siteHeader = document.querySelector('.header');
if (siteHeader) {
  window.addEventListener('scroll', () => {
    siteHeader.classList.toggle('scrolled', window.scrollY > 8);
  }, { passive: true });
}

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
          <a href="/urun/${t.slug}" class="advisor-tool-item">
            <div style="flex: 1;">
              <h4 class="advisor-tool-item-title">${t.original_name}</h4>
              <p class="advisor-tool-item-summary">${t.summary_tr}</p>
            </div>
            <div class="advisor-tool-item-votes">▲ ${t.votes}</div>
          </a>
        `).join('');
      } else {
        toolsDiv.innerHTML = '<p class="advisor-tool-item-summary">Üzgünüm, bu spesifik ihtiyaca uygun bir araç bulamadım.</p>';
      }
      
    } catch (err) {
      messageDiv.textContent = 'Bir hata oluştu. Lütfen tekrar deneyin.';
    } finally {
      submitBtn.textContent = 'Danış';
      submitBtn.disabled = false;
    }
  });
}
