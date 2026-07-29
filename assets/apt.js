/* ═══════════════════════════════════════════════════════════════
   ForesteriaGenova.it — JS condiviso pagine appartamento
   v=3.0 | 2026-07-28
   ═══════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  /* ── Nav scroll ── */
  var navbar = document.getElementById('navbar');
  if (navbar) {
    window.addEventListener('scroll', function () {
      navbar.classList.toggle('scrolled', window.scrollY > 50);
    });
  }

  /* ── Menu mobile ── */
  var navMobile = document.getElementById('navMobile');
  window.toggleMenu = function () {
    if (navMobile) navMobile.classList.toggle('open');
  };
  if (navMobile) {
    navMobile.querySelectorAll('a').forEach(function (a) {
      a.addEventListener('click', function () { navMobile.classList.remove('open'); });
    });
  }

  /* ── Scroll reveal ── */
  var revealEls = document.querySelectorAll('.reveal');
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry, i) {
      if (entry.isIntersecting) {
        setTimeout(function () { entry.target.classList.add('visible'); }, i * 80);
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.12 });
  revealEls.forEach(function (el) { observer.observe(el); });

  /* ── Gallery slider ── */
  window.galleryGo = function (id, dir) {
    var slider = document.getElementById(id);
    if (!slider) return;
    var slides = slider.querySelectorAll('.gallery-slide');
    var current = 0;
    slides.forEach(function (s, i) { if (s.classList.contains('active')) current = i; });
    var next = (current + dir + slides.length) % slides.length;
    slides[current].classList.remove('active');
    slides[next].classList.add('active');
    var counter = document.getElementById(id + '-counter');
    if (counter) counter.textContent = (next + 1) + ' / ' + slides.length;
  };
  window.galleryPrev = function (id) { galleryGo(id, -1); };
  window.galleryNext = function (id) { galleryGo(id, +1); };

  /* ── Lightbox ── */
  var lightboxImgs = [];
  var lightboxIndex = 0;
  var lb = document.getElementById('lightbox');
  var lbImg = document.getElementById('lightboxImg');
  var lbCounter = document.getElementById('lightboxCounter');

  function updateLightbox() {
    if (!lbImg || !lightboxImgs.length) return;
    lbImg.src = lightboxImgs[lightboxIndex].src;
    lbImg.alt = lightboxImgs[lightboxIndex].alt || '';
    if (lbCounter) lbCounter.textContent = (lightboxIndex + 1) + ' / ' + lightboxImgs.length;
  }
  window.openLightbox = function (imgs, index) {
    if (!lb) return;
    lightboxImgs = imgs;
    lightboxIndex = index || 0;
    updateLightbox();
    lb.classList.add('open');
  };
  window.closeLightbox = function () { if (lb) lb.classList.remove('open'); };
  window.lightboxNav = function (dir) {
    if (!lightboxImgs.length) return;
    lightboxIndex = (lightboxIndex + dir + lightboxImgs.length) % lightboxImgs.length;
    updateLightbox();
  };
  window.lightboxBgClick = function (e) { if (e.target === lb) closeLightbox(); };
  document.addEventListener('keydown', function (e) {
    if (!lb || !lb.classList.contains('open')) return;
    if (e.key === 'Escape') closeLightbox();
    if (e.key === 'ArrowLeft') lightboxNav(-1);
    if (e.key === 'ArrowRight') lightboxNav(+1);
  });
  // Clic sulle foto della gallery → lightbox
  document.querySelectorAll('.gallery-slider').forEach(function (slider) {
    var imgs = Array.prototype.slice.call(slider.querySelectorAll('.gallery-slide img'));
    imgs.forEach(function (img, i) {
      img.addEventListener('click', function (e) {
        e.stopPropagation();
        openLightbox(imgs, i);
      });
    });
  });

  /* ── Stato occupazione (fetch da /status.json) ──
     La pagina dichiara data-apt="<chiave status.json>" sul <body>.
     Se occupato: mostra il banner #occBanner (testo già localizzato nel
     markup, con <span id="occDate"></span> per la data) e aggiorna il
     badge #aptAvail usando i testi nei suoi attributi data-free/data-busy. */
  var aptKey = document.body.getAttribute('data-apt');
  if (aptKey) {
    fetch('/status.json?v=' + Date.now())
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (data) {
        if (!data || !data.appartamenti) return;
        var apt = data.appartamenti[aptKey];
        if (!apt) return;
        var avail = document.getElementById('aptAvail');
        var availText = document.getElementById('aptAvailText');
        var fmt = '';
        if (apt.fino_al) {
          var p = apt.fino_al.split('-');
          fmt = p.length === 3 ? p[2] + '/' + p[1] + '/' + p[0] : apt.fino_al;
        }
        if (apt.occupato && fmt) {
          var banner = document.getElementById('occBanner');
          var dateEl = document.getElementById('occDate');
          if (dateEl) dateEl.textContent = fmt;
          if (banner) banner.hidden = false;
          if (avail && availText) {
            avail.dataset.state = 'busy';
            availText.textContent = (avail.getAttribute('data-busy') || '').replace('{d}', fmt);
            avail.hidden = false;
          }
        } else if (avail && availText) {
          avail.dataset.state = 'free';
          availText.textContent = avail.getAttribute('data-free') || '';
          avail.hidden = false;
        }
      })
      .catch(function () { /* silenzioso: senza rete il badge resta nascosto */ });
  }

  /* ── Invio form Web3Forms ── */
  window.handleSubmit = function (e) {
    e.preventDefault();
    var form = e.target;
    var btn = form.querySelector('.btn-submit');
    var originalText = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    fetch('https://api.web3forms.com/submit', {
      method: 'POST',
      body: new FormData(form)
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.success) {
          form.style.display = 'none';
          var ok = document.getElementById('formSuccess');
          if (ok) ok.style.display = 'block';
        } else {
          if (btn) { btn.disabled = false; btn.textContent = originalText; }
        }
      })
      .catch(function () {
        if (btn) { btn.disabled = false; btn.textContent = originalText; }
      });
    return false;
  };
})();
