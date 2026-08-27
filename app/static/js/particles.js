(() => {
  "use strict";

  const canvas = document.getElementById("particle-canvas");
  const container = document.getElementById("particle-background");

  if (!canvas || !container) return;
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return;

  // ---------------------------------------------------------------------------
  // Configuration & Dynamic DaisyUI Theme Detection
  // ---------------------------------------------------------------------------

  const CONFIG = {
    density: 0.008,
    minParticles: 35,
    maxParticles: 100,
    connectionDistance: 150,
    mouseRadius: 160,
    mouseForce: 0.2,
    baseSpeed: 8,
    packetChance: 0.003,
    maxPackets: 8,
    nodeOpacity: 0.7,
    lineOpacity: 0.2,
    respectReducedMotion: true,
  };

  // Helper to extract DaisyUI colors or fall back gracefully
  function getThemeColors() {
    const style = getComputedStyle(document.documentElement);
    // DaisyUI defines colors as HSL triplets (e.g., "259 94% 51%")
    const primary = style.getPropertyValue("--p").trim() || "147 100% 36%"; // fallback
    const secondary = style.getPropertyValue("--s").trim() || "217 91% 60%";

    return {
      primary: `hsl(${primary})`,
      primaryAlpha: (a) => `hsla(${primary} / ${a})`,
      secondaryAlpha: (a) => `hsla(${secondary} / ${a})`,
    };
  }

  let themeColors = getThemeColors();

  // Re-fetch theme colors whenever DaisyUI theme changes
  const themeObserver = new MutationObserver(() => {
    themeColors = getThemeColors();
  });
  themeObserver.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });

  // ---------------------------------------------------------------------------
  // Canvas State & Mouse Tracking
  // ---------------------------------------------------------------------------

  let width = 0;
  let height = 0;
  let dpr = 1;

  const particles = [];
  const packets = [];

  const mouse = {
    x: -9999,
    y: -9999,
    active: false,
  };

  const random = (min, max) => Math.random() * (max - min) + min;
  const clamp = (val, min, max) => Math.max(min, Math.min(max, val));

  // ---------------------------------------------------------------------------
  // Particle System
  // ---------------------------------------------------------------------------

  class Particle {
    constructor() {
      this.reset(true);
    }

    reset(initial = false) {
      this.x = initial ? random(0, width) : random(-20, width + 20);
      this.y = initial ? random(0, height) : random(-20, height + 20);

      const angle = random(0, Math.PI * 2);
      const speed = random(CONFIG.baseSpeed * 0.5, CONFIG.baseSpeed);
      this.vx = Math.cos(angle) * speed;
      this.vy = Math.sin(angle) * speed;

      this.radius = random(1.2, 2.4);
      this.isSecondary = Math.random() < 0.25;
      this.opacity = random(0.3, CONFIG.nodeOpacity);

      this.pulse = random(0, Math.PI * 2);
      this.pulseSpeed = random(0.01, 0.03);
    }

    update() {
      this.pulse += this.pulseSpeed;
      this.x += this.vx;
      this.y += this.vy;

      // Interactive Cursor Push Force
      if (mouse.active) {
        const dx = this.x - mouse.x;
        const dy = this.y - mouse.y;
        const distSq = dx * dx + dy * dy;
        const radiusSq = CONFIG.mouseRadius * CONFIG.mouseRadius;

        if (distSq < radiusSq && distSq > 0) {
          const dist = Math.sqrt(distSq);
          const force = (1 - dist / CONFIG.mouseRadius) * CONFIG.mouseForce;
          this.vx += (dx / dist) * force;
          this.vy += (dy / dist) * force;
        }
      }

      // Drag / Friction to stabilize speed
      this.vx *= 0.98;
      this.vy *= 0.98;

      // Wrap-around boundary checking
      if (this.x < -30) this.x = width + 30;
      if (this.x > width + 30) this.x = -30;
      if (this.y < -30) this.y = height + 30;
      if (this.y > height + 30) this.y = -30;
    }

    draw() {
      const currentRadius = this.radius + Math.sin(this.pulse) * 0.5;
      const alphaFn = this.isSecondary
        ? themeColors.secondaryAlpha
        : themeColors.primaryAlpha;

      ctx.beginPath();
      ctx.arc(this.x, this.y, currentRadius, 0, Math.PI * 2);
      ctx.fillStyle = alphaFn(this.opacity);
      ctx.shadowBlur = 8;
      ctx.shadowColor = alphaFn(0.5);
      ctx.fill();
      ctx.shadowBlur = 0; // Reset for performance
    }
  }

  // ---------------------------------------------------------------------------
  // Data Packet System
  // ---------------------------------------------------------------------------

  class DataPacket {
    constructor(from, to) {
      this.from = from;
      this.to = to;
      this.progress = 0;
      this.speed = random(0.008, 0.02);
      this.size = random(1.5, 2.5);
    }

    update() {
      this.progress += this.speed;
      return this.progress < 1;
    }

    draw() {
      const x = this.from.x + (this.to.x - this.from.x) * this.progress;
      const y = this.from.y + (this.to.y - this.from.y) * this.progress;

      ctx.beginPath();
      ctx.arc(x, y, this.size, 0, Math.PI * 2);
      ctx.fillStyle = themeColors.secondaryAlpha(0.9);
      ctx.shadowBlur = 10;
      ctx.shadowColor = themeColors.secondaryAlpha(1);
      ctx.fill();
      ctx.shadowBlur = 0;
    }
  }

  // ---------------------------------------------------------------------------
  // Connection Lines & Cursor Threads
  // ---------------------------------------------------------------------------

  function drawConnections() {
    for (let i = 0; i < particles.length; i++) {
      const p1 = particles[i];

      // Dynamic connection to Mouse Cursor
      if (mouse.active) {
        const dx = p1.x - mouse.x;
        const dy = p1.y - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);

        if (dist < CONFIG.mouseRadius) {
          const alpha = (1 - dist / CONFIG.mouseRadius) * 0.35;
          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(mouse.x, mouse.y);
          ctx.strokeStyle = themeColors.primaryAlpha(alpha);
          ctx.lineWidth = 1;
          ctx.stroke();
        }
      }

      // Particle to Particle connections
      for (let j = i + 1; j < particles.length; j++) {
        const p2 = particles[j];
        const dx = p1.x - p2.x;
        const dy = p1.y - p2.y;
        const distSq = dx * dx + dy * dy;
        const maxDistSq = CONFIG.connectionDistance * CONFIG.connectionDistance;

        if (distSq < maxDistSq) {
          const dist = Math.sqrt(distSq);
          const alpha = CONFIG.lineOpacity * (1 - dist / CONFIG.connectionDistance);

          ctx.beginPath();
          ctx.moveTo(p1.x, p1.y);
          ctx.lineTo(p2.x, p2.y);
          ctx.strokeStyle = p1.isSecondary || p2.isSecondary
            ? themeColors.secondaryAlpha(alpha)
            : themeColors.primaryAlpha(alpha);
          ctx.lineWidth = 0.75;
          ctx.stroke();
        }
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Lifecycle & Resize Management
  // ---------------------------------------------------------------------------

  function resizeCanvas() {
    const rect = container.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    dpr = Math.min(window.devicePixelRatio || 1, 2);

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    initParticles();
  }

  function initParticles() {
    particles.length = 0;
    packets.length = 0;

    const count = clamp(
      Math.round(width * height * CONFIG.density),
      CONFIG.minParticles,
      CONFIG.maxParticles
    );

    for (let i = 0; i < count; i++) {
      particles.push(new Particle());
    }
  }

  function spawnPacket() {
    if (packets.length >= CONFIG.maxPackets || Math.random() > CONFIG.packetChance) return;

    const from = particles[Math.floor(Math.random() * particles.length)];
    if (!from) return;

    const targets = particles.filter((p) => {
      if (p === from) return false;
      const dx = p.x - from.x;
      const dy = p.y - from.y;
      return (dx * dx + dy * dy) <= (CONFIG.connectionDistance * CONFIG.connectionDistance);
    });

    if (targets.length) {
      const to = targets[Math.floor(Math.random() * targets.length)];
      packets.push(new DataPacket(from, to));
    }
  }

  // ---------------------------------------------------------------------------
  // Animation Loop
  // ---------------------------------------------------------------------------

  function animate() {
    ctx.clearRect(0, 0, width, height);

    drawConnections();

    for (const p of particles) {
      p.update();
      p.draw();
    }

    spawnPacket();

    for (let i = packets.length - 1; i >= 0; i--) {
      if (!packets[i].update()) {
        packets.splice(i, 1);
      } else {
        packets[i].draw();
      }
    }

    requestAnimationFrame(animate);
  }

  // ---------------------------------------------------------------------------
  // Event Listeners & Initialization
  // ---------------------------------------------------------------------------

  window.addEventListener("mousemove", (e) => {
    const rect = canvas.getBoundingClientRect();
    mouse.x = e.clientX - rect.left;
    mouse.y = e.clientY - rect.top;
    mouse.active = true;
  }, { passive: true });

  window.addEventListener("mouseleave", () => {
    mouse.active = false;
  });

  const prefersReducedMotion =
    CONFIG.respectReducedMotion &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (prefersReducedMotion) {
    resizeCanvas();
    drawConnections();
    particles.forEach((p) => p.draw());
    return;
  }

  new ResizeObserver(resizeCanvas).observe(container);
  resizeCanvas();
  animate();
})();