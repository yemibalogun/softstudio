(() => {
  "use strict";

  const canvas = document.getElementById("particle-canvas");
  const container = document.getElementById("particle-background");

  if (!canvas || !container) return;
  const ctx = canvas.getContext("2d", { alpha: false });
  if (!ctx) return;

  // ---------------------------------------------------------------------------
  // Fast 3D Simplex Noise Implementation (for fluid vector field)
  // ---------------------------------------------------------------------------
  const F3 = 1.0 / 3.0, G3 = 1.0 / 6.0;
  const p = new Uint8Array(256);
  for (let i = 0; i < 256; i++) p[i] = Math.floor(Math.random() * 256);
  const perm = new Uint8Array(512), permMod12 = new Uint8Array(512);
  for (let i = 0; i < 512; i++) {
    perm[i] = p[i & 255];
    permMod12[i] = (perm[i] % 12);
  }
  const grad3 = new Float32Array([
    1,1,0, -1,1,0, 1,-1,0, -1,-1,0,
    1,0,1, -1,0,1, 1,0,-1, -1,0,-1,
    0,1,1, 0,-1,1, 0,1,-1, 0,-1,-1
  ]);

  function simplex3(xin, yin, zin) {
    let n0, n1, n2, n3;
    let s = (xin + yin + zin) * F3;
    let i = Math.floor(xin + s), j = Math.floor(yin + s), k = Math.floor(zin + s);
    let t = (i + j + k) * G3;
    let X0 = i - t, Y0 = j - t, Z0 = k - t;
    let x0 = xin - X0, y0 = yin - Y0, z0 = zin - Z0;
    let i1, j1, k1, i2, j2, k2;
    if (x0 >= y0) {
      if (y0 >= z0) { i1=1; j1=0; k1=0; i2=1; j2=1; k2=0; }
      else if (x0 >= z0) { i1=1; j1=0; k1=0; i2=1; j2=0; k2=1; }
      else { i1=0; j1=0; k1=1; i2=1; j2=0; k2=1; }
    } else {
      if (y0 < z0) { i1=0; j1=0; k1=1; i2=0; j2=1; k2=1; }
      else if (x0 < z0) { i1=0; j1=1; k1=0; i2=0; j2=1; k2=1; }
      else { i1=0; j1=1; k1=0; i2=1; j2=1; k2=0; }
    }
    let x1 = x0 - i1 + G3, y1 = y0 - j1 + G3, z1 = z0 - k1 + G3;
    let x2 = x0 - i2 + 2.0*G3, y2 = y0 - j2 + 2.0*G3, z2 = z0 - k2 + 2.0*G3;
    let x3 = x0 - 1.0 + 3.0*G3, y3 = y0 - 1.0 + 3.0*G3, z3 = z0 - 1.0 + 3.0*G3;
    let ii = i & 255, jj = j & 255, kk = k & 255;
    
    let t0 = 0.6 - x0*x0 - y0*y0 - z0*z0;
    if (t0 < 0) n0 = 0.0;
    else { let gi0 = permMod12[ii+perm[jj+perm[kk]]]*3; t0 *= t0; n0 = t0 * t0 * (grad3[gi0]*x0 + grad3[gi0+1]*y0 + grad3[gi0+2]*z0); }

    let t1 = 0.6 - x1*x1 - y1*y1 - z1*z1;
    if (t1 < 0) n1 = 0.0;
    else { let gi1 = permMod12[ii+i1+perm[jj+j1+perm[kk+k1]]]*3; t1 *= t1; n1 = t1 * t1 * (grad3[gi1]*x1 + grad3[gi1+1]*y1 + grad3[gi1+2]*z1); }

    let t2 = 0.6 - x2*x2 - y2*y2 - z2*z2;
    if (t2 < 0) n2 = 0.0;
    else { let gi2 = permMod12[ii+i2+perm[jj+j2+perm[kk+k2]]]*3; t2 *= t2; n2 = t2 * t2 * (grad3[gi2]*x2 + grad3[gi2+1]*y2 + grad3[gi2+2]*z2); }

    let t3 = 0.6 - x3*x3 - y3*y3 - z3*z3;
    if (t3 < 0) n3 = 0.0;
    else { let gi3 = permMod12[ii+1+perm[jj+1+perm[kk+1]]]*3; t3 *= t3; n3 = t3 * t3 * (grad3[gi3]*x3 + grad3[gi3+1]*y3 + grad3[gi3+2]*z3); }

    return 32.0 * (n0 + n1 + n2 + n3);
  }

  // ---------------------------------------------------------------------------
  // Fluid Stream Configuration
  // ---------------------------------------------------------------------------

  const CONFIG = {
    particleCount: 2200,      // High density for fine dust / dynamic clouds
    fieldScale: 0.0018,       // Scale of noise swirls
    timeSpeed: 0.0004,        // How fast the fluid turbulence evolves over time
    particleSpeed: 1.8,       // Base velocity through vector field
    mouseRadius: 220,
    mouseForce: 0.08,
  };

  let width = 0, height = 0, dpr = 1;
  let time = 0;
  const particles = [];
  const mouse = { x: -9999, y: -9999, active: false };

  // Color Palette sampled from video: Neon Cyan, Deep Blue, Magenta Accent
  const COLORS = [
    { r: 90,  g: 130, b: 255 },  // Royal/Electric Blue
    { r: 60,  g: 220, b: 255 },  // Cyan Bright
    { r: 160, g: 80,  b: 255 },  // Indigo Violet
    { r: 230, g: 240, b: 255 }   // Core Bright White-Blue
  ];

  class DustParticle {
    constructor() {
      this.reset(true);
    }

    reset(initial = false) {
      this.x = initial ? Math.random() * width : Math.random() * width;
      this.y = initial ? Math.random() * height : (Math.random() < 0.5 ? -10 : height + 10);
      
      this.vx = 0;
      this.vy = 0;
      this.life = Math.random();
      this.maxLife = Math.random() * 200 + 100;
      this.age = Math.random() * this.maxLife;

      // Assign color variant
      this.color = COLORS[Math.floor(Math.random() * COLORS.length)];
      this.size = Math.random() < 0.95 ? Math.random() * 1.2 + 0.5 : Math.random() * 2.5 + 1.2;
    }

    update() {
      this.age++;
      if (this.age >= this.maxLife) {
        this.reset();
      }

      // Calculate fluid flow angle using 3D Simplex Noise
      const angle = simplex3(
        this.x * CONFIG.fieldScale,
        this.y * CONFIG.fieldScale,
        time
      ) * Math.PI * 3;

      // Desired velocity from vector field
      const targetVx = Math.cos(angle) * CONFIG.particleSpeed;
      const targetVy = Math.sin(angle) * CONFIG.particleSpeed;

      // Smooth acceleration into flow field
      this.vx += (targetVx - this.vx) * 0.05;
      this.vy += (targetVy - this.vy) * 0.05;

      // Interactive Cursor Displacement
      if (mouse.active) {
        const dx = this.x - mouse.x;
        const dy = this.y - mouse.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < CONFIG.mouseRadius && dist > 0) {
          const force = (1 - dist / CONFIG.mouseRadius) * CONFIG.mouseForce;
          this.vx += (dx / dist) * force * 5;
          this.vy += (dy / dist) * force * 5;
        }
      }

      this.x += this.vx;
      this.y += this.vy;

      // Wrap boundaries smoothly
      if (this.x < -20) this.x = width + 20;
      if (this.x > width + 20) this.x = -20;
      if (this.y < -20) this.y = height + 20;
      if (this.y > height + 20) this.y = -20;
    }

    draw() {
      // Fade in at start of life, fade out at end
      const progress = this.age / this.maxLife;
      const fadeInOut = Math.sin(progress * Math.PI);
      const alpha = fadeInOut * 0.75;

      ctx.fillStyle = `rgba(${this.color.r}, ${this.color.g}, ${this.color.b}, ${alpha})`;
      ctx.fillRect(this.x, this.y, this.size, this.size);
    }
  }

  // ---------------------------------------------------------------------------
  // Canvas Lifecycle
  // ---------------------------------------------------------------------------

  function resize() {
    const rect = container.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    dpr = Math.min(window.devicePixelRatio || 1, 2);

    canvas.width = Math.floor(width * dpr);
    canvas.height = Math.floor(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    particles.length = 0;
    for (let i = 0; i < CONFIG.particleCount; i++) {
      particles.push(new DustParticle());
    }
  }

  // ---------------------------------------------------------------------------
  // Main Rendering Engine
  // ---------------------------------------------------------------------------

  function animate() {
    time += CONFIG.timeSpeed;

    // Dark space trail fade effect
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(3, 5, 12, 0.25)"; 
    ctx.fillRect(0, 0, width, height);

    // Switch to additive blending for glowing blue nebula core effects
    ctx.globalCompositeOperation = "lighter";

    for (let i = 0; i < particles.length; i++) {
      particles[i].update();
      particles[i].draw();
    }

    requestAnimationFrame(animate);
  }

  // ---------------------------------------------------------------------------
  // Listeners
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

  new ResizeObserver(resize).observe(container);
  resize();
  animate();
})();