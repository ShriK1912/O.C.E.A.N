/**
 * EcoTrace · MarineVigil Landing Page
 * Scroll-driven canvas frame animation + overlay panel logic
 */

/* ── Config ── */
const TOTAL_FRAMES = 100;
const SCROLL_MULTIPLIER = 5; // px of scroll per frame
const FRAME_PATH = (n) => `ezgif-frame-${String(n).padStart(3, '0')}.jpg`;

const SCENES = [
  {
    id: 'panel-1',
    startFrame: 0,
    endFrame: 18,
    dotIndex: 0,
    label: 'Scene 1 / 5 — The Threat',
  },
  {
    id: 'panel-2',
    startFrame: 19,
    endFrame: 46,
    dotIndex: 1,
    label: 'Scene 2 / 5 — Discharge Detected',
  },
  {
    id: 'panel-3',
    startFrame: 47,
    endFrame: 64,
    dotIndex: 2,
    label: 'Scene 3 / 5 — SAR Detection',
  },
  {
    id: 'panel-4',
    startFrame: 65,
    endFrame: 84,
    dotIndex: 3,
    label: 'Scene 4 / 5 — Hydrodynamic Hindcast',
  },
  {
    id: 'panel-5',
    startFrame: 85,
    endFrame: 100,
    dotIndex: 4,
    label: 'Scene 5 / 5 — Vessel Attribution',
  },
];

/* ── Globals ── */
let currentFrame = 0;
let images = [];
let imagesLoaded = 0;
let isAnimating = false;
let rafId = null;
let targetFrame = 0;

const canvas = document.getElementById('animCanvas');
const ctx = canvas.getContext('2d');

/* ── Setup scroll spacer height ── */
const scrollContainer = document.getElementById('scrollContainer');
scrollContainer.style.height = `${TOTAL_FRAMES * SCROLL_MULTIPLIER + window.innerHeight}px`;

const scrollSpacer = scrollContainer.querySelector('.scroll-spacer');
scrollSpacer.style.height = `${TOTAL_FRAMES * SCROLL_MULTIPLIER}px`;

/* ── Canvas sizing ── */
function resizeCanvas() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
  drawFrame(currentFrame);
}

window.addEventListener('resize', resizeCanvas);
resizeCanvas();

/* ── Image preloading ── */
function preloadImages() {
  const loadingEl = createLoadingOverlay();

  for (let i = 1; i <= TOTAL_FRAMES; i++) {
    const img = new Image();
    img.src = FRAME_PATH(i);
    img.onload = () => {
      imagesLoaded++;
      const percent = Math.round((imagesLoaded / TOTAL_FRAMES) * 100);
      updateLoadingProgress(loadingEl, percent);
      if (imagesLoaded === TOTAL_FRAMES) {
        removeLoadingOverlay(loadingEl);
        drawFrame(0);
        initScrollListener();
      }
    };
    img.onerror = () => {
      imagesLoaded++;
      if (imagesLoaded === TOTAL_FRAMES) {
        removeLoadingOverlay(loadingEl);
        drawFrame(0);
        initScrollListener();
      }
    };
    images[i - 1] = img;
  }
}

/* ── Loading overlay ── */
function createLoadingOverlay() {
  const overlay = document.createElement('div');
  overlay.id = 'loadingOverlay';
  overlay.innerHTML = `
    <div class="loading-inner">
      <div class="loading-logo">
        <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
          <circle cx="14" cy="14" r="13" stroke="#00d4ff" stroke-width="1.5"/>
          <path d="M7 14 Q14 6 21 14 Q14 22 7 14Z" fill="#00d4ff" opacity="0.3"/>
          <circle cx="14" cy="14" r="3" fill="#00d4ff"/>
        </svg>
      </div>
      <div class="loading-title">Initializing EcoTrace</div>
      <div class="loading-bar-track">
        <div class="loading-bar-fill" id="loadingFill"></div>
      </div>
      <div class="loading-status" id="loadingStatus">Loading satellite imagery...</div>
    </div>
  `;
  overlay.style.cssText = `
    position: fixed; inset: 0; z-index: 9999;
    background: #020a10;
    display: flex; align-items: center; justify-content: center;
    flex-direction: column;
  `;
  overlay.querySelector('.loading-inner').style.cssText = `
    text-align: center; display: flex; flex-direction: column;
    align-items: center; gap: 16px;
  `;
  overlay.querySelector('.loading-logo').style.cssText = `
    margin-bottom: 8px; animation: spin-slow 4s linear infinite;
  `;
  overlay.querySelector('.loading-title').style.cssText = `
    font-family: 'Space Grotesk', sans-serif; font-size: 1.1rem;
    font-weight: 600; color: #e8f4f8; letter-spacing: -0.02em;
  `;
  overlay.querySelector('.loading-bar-track').style.cssText = `
    width: 240px; height: 3px; background: rgba(0,212,255,0.1);
    border-radius: 2px; overflow: hidden;
  `;
  overlay.querySelector('.loading-bar-fill').style.cssText = `
    height: 100%; width: 0%; background: linear-gradient(90deg, #00d4ff, #00ff88);
    border-radius: 2px; transition: width 0.3s ease;
  `;
  overlay.querySelector('.loading-status').style.cssText = `
    font-size: 0.75rem; color: rgba(0,212,255,0.5);
    font-family: 'JetBrains Mono', monospace; letter-spacing: 0.05em;
  `;

  // Add spinning animation
  const style = document.createElement('style');
  style.textContent = `@keyframes spin-slow { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`;
  document.head.appendChild(style);

  document.body.appendChild(overlay);
  return overlay;
}

function updateLoadingProgress(overlay, percent) {
  const fill = overlay.querySelector('#loadingFill');
  const status = overlay.querySelector('#loadingStatus');
  if (fill) fill.style.width = `${percent}%`;
  if (status) {
    if (percent < 30) status.textContent = 'Loading satellite imagery...';
    else if (percent < 60) status.textContent = 'Calibrating SAR backscatter...';
    else if (percent < 85) status.textContent = 'Initializing hindcast engine...';
    else status.textContent = 'Preparing attribution pipeline...';
  }
}

function removeLoadingOverlay(overlay) {
  overlay.style.transition = 'opacity 0.6s ease';
  overlay.style.opacity = '0';
  setTimeout(() => overlay.remove(), 700);
}

/* ── Draw frame on canvas ── */
function drawFrame(frameIndex) {
  const img = images[frameIndex];
  if (!img || !img.complete || !img.naturalWidth) return;

  const canvasW = canvas.width;
  const canvasH = canvas.height;
  const imgW = img.naturalWidth;
  const imgH = img.naturalHeight;

  // Cover-fit: maintain aspect ratio and fill canvas
  const scale = Math.max(canvasW / imgW, canvasH / imgH);
  const drawW = imgW * scale;
  const drawH = imgH * scale;
  const offsetX = (canvasW - drawW) / 2;
  const offsetY = (canvasH - drawH) / 2;

  ctx.clearRect(0, 0, canvasW, canvasH);
  ctx.drawImage(img, offsetX, offsetY, drawW, drawH);

  // Subtle dark vignette for panel readability
  const gradient = ctx.createRadialGradient(
    canvasW / 2, canvasH / 2, canvasH * 0.2,
    canvasW / 2, canvasH / 2, canvasH * 0.85
  );
  gradient.addColorStop(0, 'rgba(0,0,0,0)');
  gradient.addColorStop(1, 'rgba(0,0,0,0.55)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, canvasW, canvasH);
}

/* ── Smooth interpolation loop ── */
function animateToFrame() {
  if (Math.abs(currentFrame - targetFrame) < 0.5) {
    currentFrame = targetFrame;
    drawFrame(Math.round(currentFrame));
    isAnimating = false;
    return;
  }
  currentFrame += (targetFrame - currentFrame) * 0.15;
  drawFrame(Math.round(currentFrame));
  rafId = requestAnimationFrame(animateToFrame);
}

/* ── Scroll handler ── */
function initScrollListener() {
  const stickyFrame = document.getElementById('stickyFrame');
  const progressBar = document.getElementById('progressBar');
  const sceneLabelText = document.getElementById('sceneLabelText');
  const dots = document.querySelectorAll('.prog-dot');
  const panels = {};

  SCENES.forEach((s) => {
    panels[s.id] = document.getElementById(s.id);
  });

  function onScroll() {
    const containerTop = scrollContainer.getBoundingClientRect().top + window.scrollY;
    const scrolled = window.scrollY - containerTop;
    const maxScroll = TOTAL_FRAMES * SCROLL_MULTIPLIER;

    // Frame calculation
    const rawFrame = Math.max(0, Math.min(TOTAL_FRAMES - 1, Math.floor(scrolled / SCROLL_MULTIPLIER)));
    const progress = Math.max(0, Math.min(1, scrolled / maxScroll));

    targetFrame = rawFrame;

    if (!isAnimating) {
      isAnimating = true;
      animateToFrame();
    }

    // Update progress bar
    progressBar.style.setProperty('--progress', `${progress * 100}%`);

    // Update panels and dots
    SCENES.forEach((scene, index) => {
      const panel = panels[scene.id];
      if (!panel) return;

      const inScene = rawFrame >= scene.startFrame && rawFrame <= scene.endFrame;

      if (inScene) {
        panel.classList.add('visible');
        // Update dot
        dots.forEach((d, di) => {
          d.classList.toggle('active', di === scene.dotIndex);
        });
        // Update scene label
        sceneLabelText.textContent = scene.label;
      } else {
        panel.classList.remove('visible');
      }
    });
  }

  // Progress dot click — jump to frame
  document.querySelectorAll('.prog-dot').forEach((dot, index) => {
    dot.addEventListener('click', () => {
      const scene = SCENES[index];
      const containerTop = scrollContainer.getBoundingClientRect().top + window.scrollY;
      const targetScrollY = containerTop + scene.startFrame * SCROLL_MULTIPLIER;
      window.scrollTo({ top: targetScrollY, behavior: 'smooth' });
    });
  });

  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll(); // Initial call
}

/* ── Navbar scroll effect ── */
const navbar = document.getElementById('navbar');
window.addEventListener('scroll', () => {
  navbar.classList.toggle('scrolled', window.scrollY > 20);
}, { passive: true });

/* ── Nav section links scroll ── */
document.querySelectorAll('.nav-link[href^="#"]').forEach((link) => {
  link.addEventListener('click', (e) => {
    const targetId = link.getAttribute('href').slice(1);
    const scene = SCENES.find((s) => {
      // Map nav link IDs to scene indices
      const map = { 'scene-1': 0, 'scene-3': 2, 'scene-4': 3, 'scene-5': 4 };
      return Object.entries(map).find(([k, v]) => k === targetId && v === SCENES.indexOf(s));
    });

    if (scene) {
      e.preventDefault();
      const containerTop = scrollContainer.getBoundingClientRect().top + window.scrollY;
      const targetScrollY = containerTop + scene.startFrame * SCROLL_MULTIPLIER;
      window.scrollTo({ top: targetScrollY, behavior: 'smooth' });
    }
  });
});

/* ── CTA Section entrance animation ── */
const demoCta = document.getElementById('demoCta');
const ctaObserver = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        demoCta.querySelectorAll('.cta-badge, .cta-title, .cta-body, .cta-feature-grid, .demo-button, .cta-disclaimer')
          .forEach((el, i) => {
            el.style.opacity = '0';
            el.style.transform = 'translateY(24px)';
            el.style.transition = `opacity 0.6s ease ${i * 0.1}s, transform 0.6s ease ${i * 0.1}s`;
            requestAnimationFrame(() => {
              el.style.opacity = '1';
              el.style.transform = 'translateY(0)';
            });
          });
        ctaObserver.disconnect();
      }
    });
  },
  { threshold: 0.2 }
);
if (demoCta) ctaObserver.observe(demoCta);

/* ── Init ── */
preloadImages();
