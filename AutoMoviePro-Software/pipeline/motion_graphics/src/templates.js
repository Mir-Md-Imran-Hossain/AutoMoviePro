/**
 * AutoMovie Pro — Motion Graphics Composition Templates & 3-Layer Visual Architecture
 * -----------------------------------------------------------------------------------
 * Provides standard Canvas 2D + SVG DOM renderers for:
 * Layer 1: Dark Cyberpunk Grid, Floating Organic Neon Particles, Pulse Ambient Glow
 * Layer 2: Core Asset (Glassmorphic HUD Cards, Data Graphs, Curved Progress, Counters)
 * Layer 3: Kinetic Typography with Word-Level Highlights & Safe-Zone Bounds
 */

var SpringEngine = (typeof require !== 'undefined')
  ? require('./spring.js').SpringPhysics
  : (typeof SpringPhysics !== 'undefined' ? SpringPhysics : window.SpringPhysics);

// Seeded pseudo-random for deterministic particle positioning
function createRng(seed = 12345) {
  let s = seed;
  return function () {
    s = (s * 16807) % 2147483647;
    return (s - 1) / 2147483646;
  };
}

class MotionGraphicsTemplates {
  /**
   * LAYER 1: Dark Cyberpunk Grid, Floating Neon Particles, and Ambient Pulse Glow
   */
  static renderBackgroundLayer(ctx, width, height, frame, fps = 30) {
    const t = frame / fps;

    // 1. Deep Space Cyber Gradient
    const bgGrad = ctx.createLinearGradient(0, 0, 0, height);
    bgGrad.addColorStop(0, '#060913');
    bgGrad.addColorStop(0.45, '#0b1120');
    bgGrad.addColorStop(1, '#030712');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, width, height);

    // 2. Ambient Harmonic Pulse Glow
    const pulseIntensity = 0.22 + 0.08 * Math.sin(t * 2.5);
    const pulseGrad = ctx.createRadialGradient(
      width * 0.5,
      height * 0.55,
      width * 0.05,
      width * 0.5,
      height * 0.55,
      width * 0.75
    );
    pulseGrad.addColorStop(0, `rgba(14, 165, 233, ${pulseIntensity})`);
    pulseGrad.addColorStop(0.5, `rgba(99, 102, 241, ${pulseIntensity * 0.5})`);
    pulseGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = pulseGrad;
    ctx.fillRect(0, 0, width, height);

    // 3. 3D Perspective Futuristic Cyber Grid (Receding Floor)
    ctx.save();
    const horizonY = height * 0.72;
    const vanishX = width * 0.5;
    const gridGrad = ctx.createLinearGradient(0, horizonY, 0, height);
    gridGrad.addColorStop(0, 'rgba(56, 189, 248, 0.05)');
    gridGrad.addColorStop(0.6, 'rgba(56, 189, 248, 0.25)');
    gridGrad.addColorStop(1, 'rgba(14, 165, 233, 0.45)');
    ctx.strokeStyle = gridGrad;
    ctx.lineWidth = 1.5;

    // Moving horizontal grid lines (flow downwards towards camera)
    const lineSpeed = 48.0; // px/sec
    const offset = (t * lineSpeed) % 60;
    const numLines = 14;
    for (let i = 0; i < numLines; i++) {
      const p = Math.pow((i + offset / 60) / numLines, 2.2);
      const ly = horizonY + p * (height - horizonY);
      if (ly >= horizonY && ly <= height) {
        ctx.beginPath();
        ctx.moveTo(0, ly);
        ctx.lineTo(width, ly);
        ctx.stroke();
      }
    }

    // Radiating perspective lines from horizon
    const numRays = 18;
    for (let i = -numRays; i <= numRays; i++) {
      const bottomX = vanishX + i * (width / 10);
      ctx.beginPath();
      ctx.moveTo(vanishX, horizonY);
      ctx.lineTo(bottomX, height);
      ctx.stroke();
    }
    ctx.restore();

    // 4. Floating Organic Neon Particles
    ctx.save();
    const rng = createRng(9981);
    const particleCount = 28;
    for (let i = 0; i < particleCount; i++) {
      const baseX = rng() * width;
      const baseY = rng() * height;
      const radius = 1.8 + rng() * 3.2;
      const speed = 25.0 + rng() * 35.0;
      const sway = 15.0 + rng() * 25.0;
      const freq = 1.0 + rng() * 2.0;

      // Drift upward and loop
      const py = (baseY - t * speed) % height;
      const finalY = py < 0 ? py + height : py;
      const px = baseX + Math.sin(t * freq + i) * sway;

      // Color selection (cyan, neon purple, bright amber)
      const colorType = i % 3;
      let pColor = 'rgba(56, 189, 248, 0.65)';
      if (colorType === 1) pColor = 'rgba(168, 85, 247, 0.60)';
      if (colorType === 2) pColor = 'rgba(245, 158, 11, 0.55)';

      const alphaPulse = 0.4 + 0.4 * Math.sin(t * 3.0 + i * 1.5);
      ctx.fillStyle = pColor;
      ctx.globalAlpha = Math.max(0.1, alphaPulse);

      ctx.beginPath();
      ctx.arc(px, finalY, radius, 0, Math.PI * 2);
      ctx.fill();

      // Soft glow halo
      ctx.beginPath();
      ctx.arc(px, finalY, radius * 2.8, 0, Math.PI * 2);
      ctx.fillStyle = pColor;
      ctx.globalAlpha = alphaPulse * 0.25;
      ctx.fill();
    }
    ctx.restore();

    // 5. Subtle Vignette
    const vig = ctx.createRadialGradient(
      width * 0.5,
      height * 0.5,
      width * 0.4,
      width * 0.5,
      height * 0.5,
      width * 0.85
    );
    vig.addColorStop(0, 'rgba(0,0,0,0)');
    vig.addColorStop(1, 'rgba(3, 7, 18, 0.75)');
    ctx.fillStyle = vig;
    ctx.fillRect(0, 0, width, height);
  }

  /**
   * Helper: Draw rounded rectangle
   */
  static drawRoundedRect(ctx, x, y, w, h, radius) {
    ctx.beginPath();
    ctx.moveTo(x + radius, y);
    ctx.lineTo(x + w - radius, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + radius);
    ctx.lineTo(x + w, y + h - radius);
    ctx.quadraticCurveTo(x + w, y + h, x + w - radius, y + h);
    ctx.lineTo(x + radius, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - radius);
    ctx.lineTo(x, y + radius);
    ctx.quadraticCurveTo(x, y, x + radius, y);
    ctx.closePath();
  }

  /**
   * Helper: Draw HUD Corner Brackets
   */
  static drawHudCorners(ctx, x, y, w, h, bracketLen = 24, color = '#38bdf8') {
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.lineCap = 'round';

    // Top-Left
    ctx.beginPath();
    ctx.moveTo(x, y + bracketLen);
    ctx.lineTo(x, y);
    ctx.lineTo(x + bracketLen, y);
    ctx.stroke();

    // Top-Right
    ctx.beginPath();
    ctx.moveTo(x + w - bracketLen, y);
    ctx.lineTo(x + w, y);
    ctx.lineTo(x + w, y + bracketLen);
    ctx.stroke();

    // Bottom-Left
    ctx.beginPath();
    ctx.moveTo(x, y + h - bracketLen);
    ctx.lineTo(x, y + h);
    ctx.lineTo(x + bracketLen, y + h);
    ctx.stroke();

    // Bottom-Right
    ctx.beginPath();
    ctx.moveTo(x + w - bracketLen, y + h);
    ctx.lineTo(x + w, y + h);
    ctx.lineTo(x + w, y + h - bracketLen);
    ctx.stroke();

    ctx.restore();
  }

  /**
   * LAYER 2 TEMPLATE A: Data Graphs & Curved Progress Charts
   */
  static renderDataGraphLayer(ctx, width, height, frame, fps, props = {}) {
    const {
      headline = 'AI বৃদ্ধি ও উৎপাদনশীলতা ইনসাইট',
      metric = '+৮৫%',
      badge = 'PROVEN DATA • ANALYTICS',
      points = [15, 30, 48, 70, 95, 125, 185],
      labels = ['Q1', 'Q2', 'Q3', 'Q4', 'Y1', 'Y2', 'Y3'],
    } = props;

    // Spring physics pop-in for the main card
    const cardSpring = SpringEngine.spring({
      frame,
      fps,
      config: { mass: 0.9, stiffness: 130, damping: 13 },
      delay: 2,
    });

    const cardW = width * 0.88;
    const cardH = height * 0.48;
    const cardX = (width - cardW) / 2;
    const cardY = height * 0.22;

    ctx.save();
    // Center transformation for spring pop-in
    const centerX = cardX + cardW / 2;
    const centerY = cardY + cardH / 2;
    ctx.translate(centerX, centerY);
    const scale = Math.max(0.01, cardSpring);
    ctx.scale(scale, scale);
    ctx.translate(-centerX, -centerY);

    // 1. Glassmorphic Card Container
    ctx.save();
    ctx.shadowColor = 'rgba(0, 0, 0, 0.75)';
    ctx.shadowBlur = 45;
    ctx.shadowOffsetY = 20;

    const cardBg = ctx.createLinearGradient(cardX, cardY, cardX + cardW, cardY + cardH);
    cardBg.addColorStop(0, 'rgba(15, 23, 42, 0.88)');
    cardBg.addColorStop(1, 'rgba(30, 41, 59, 0.75)');
    ctx.fillStyle = cardBg;
    this.drawRoundedRect(ctx, cardX, cardY, cardW, cardH, 32);
    ctx.fill();
    ctx.restore();

    // Border with neon cyan accent
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.45)';
    ctx.lineWidth = 2;
    this.drawRoundedRect(ctx, cardX, cardY, cardW, cardH, 32);
    ctx.stroke();

    // HUD Corner brackets
    this.drawHudCorners(ctx, cardX + 10, cardY + 10, cardW - 20, cardH - 20, 28, '#38bdf8');

    // 2. Top Header Badge Pill
    const badgeSpring = SpringEngine.spring({
      frame,
      fps,
      config: { mass: 0.8, stiffness: 150, damping: 14 },
      delay: 6,
    });
    ctx.save();
    ctx.globalAlpha = Math.min(1.0, badgeSpring * 1.5);
    const badgeW = 280;
    const badgeH = 46;
    const badgeX = cardX + 36;
    const badgeY = cardY + 36;
    ctx.fillStyle = 'rgba(56, 189, 248, 0.15)';
    this.drawRoundedRect(ctx, badgeX, badgeY, badgeW, badgeH, 23);
    ctx.fill();
    ctx.strokeStyle = '#38bdf8';
    ctx.lineWidth = 1.5;
    this.drawRoundedRect(ctx, badgeX, badgeY, badgeW, badgeH, 23);
    ctx.stroke();

    ctx.fillStyle = '#38bdf8';
    ctx.font = 'bold 20px "Hind Siliguri", "Segoe UI", sans-serif';
    ctx.fillText(badge, badgeX + 22, badgeY + 30);

    // Headline inside card
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 36px "Hind Siliguri", "Segoe UI", sans-serif';
    ctx.fillText(headline, cardX + 36, cardY + 125);
    ctx.restore();

    // 3. Curved Chart Canvas within the Card
    const chartX = cardX + 45;
    const chartY = cardY + 170;
    const chartW = cardW - 90;
    const chartH = cardH - 230;

    // Grid baseline
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.lineWidth = 1;
    for (let r = 0; r <= 3; r++) {
      const gy = chartY + (chartH / 3) * r;
      ctx.beginPath();
      ctx.moveTo(chartX, gy);
      ctx.lineTo(chartX + chartW, gy);
      ctx.stroke();
    }

    // Chart draw spring progress (staggered delay after card pops in)
    const chartSpring = SpringEngine.spring({
      frame,
      fps,
      config: { mass: 1.0, stiffness: 90, damping: 15 },
      delay: 10,
    });
    const drawProgress = Math.max(0, Math.min(1, chartSpring));

    // Calculate normalized coordinates
    const minVal = Math.min(...points);
    const maxVal = Math.max(...points);
    const coords = points.map((val, idx) => {
      const px = chartX + (chartW / (points.length - 1)) * idx;
      const normY = (val - minVal) / (maxVal - minVal);
      const py = chartY + chartH - normY * chartH;
      return { x: px, y: py };
    });

    if (coords.length >= 2 && drawProgress > 0.01) {
      // Create smooth cubic bezier path
      const pathLength = coords.length - 1;
      const activeSegments = Math.min(pathLength, drawProgress * pathLength);

      ctx.save();
      ctx.beginPath();
      ctx.moveTo(coords[0].x, coords[0].y);

      for (let i = 0; i < pathLength; i++) {
        const segProgress = Math.max(0, Math.min(1, activeSegments - i));
        if (segProgress <= 0) break;

        const p0 = coords[i];
        const p1 = coords[i + 1];
        const cpX = (p0.x + p1.x) / 2;

        const targetX = p0.x + (p1.x - p0.x) * segProgress;
        const targetY = p0.y + (p1.y - p0.y) * segProgress;

        ctx.bezierCurveTo(cpX, p0.y, cpX, p1.y, targetX, targetY);
      }

      // Neon glowing stroke
      ctx.strokeStyle = '#00f2fe';
      ctx.lineWidth = 5;
      ctx.shadowColor = '#00f2fe';
      ctx.shadowBlur = 18;
      ctx.stroke();
      ctx.restore();

      // Glowing Data Nodes
      coords.forEach((coord, i) => {
        const nodeDelay = 10 + i * 4;
        const nodeSpring = SpringEngine.spring({
          frame,
          fps,
          config: { mass: 0.6, stiffness: 180, damping: 12 },
          delay: nodeDelay,
        });
        if (nodeSpring > 0.1) {
          ctx.save();
          const r = Math.max(0.1, 7 * nodeSpring);
          ctx.beginPath();
          ctx.arc(coord.x, coord.y, r, 0, Math.PI * 2);
          ctx.fillStyle = '#ffffff';
          ctx.shadowColor = '#38bdf8';
          ctx.shadowBlur = 16;
          ctx.fill();
          ctx.strokeStyle = '#0284c7';
          ctx.lineWidth = 3;
          ctx.stroke();

          // X-Axis Label
          if (labels[i]) {
            ctx.fillStyle = 'rgba(203, 213, 225, 0.85)';
            ctx.font = '18px "Hind Siliguri", sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(labels[i], coord.x, chartY + chartH + 30);
          }
          ctx.restore();
        }
      });
    }

    // Metric Badge overlay (bottom right of card)
    const metricSpring = SpringEngine.spring({
      frame,
      fps,
      config: { mass: 0.8, stiffness: 140, damping: 11 },
      delay: 18,
    });
    if (metricSpring > 0.05) {
      ctx.save();
      const mScale = Math.max(0.01, metricSpring);
      const mx = cardX + cardW - 200;
      const my = cardY + cardH - 110;
      ctx.translate(mx + 80, my + 35);
      ctx.scale(mScale, mScale);
      ctx.translate(-(mx + 80), -(my + 35));

      ctx.fillStyle = 'rgba(16, 185, 129, 0.2)';
      this.drawRoundedRect(ctx, mx, my, 160, 70, 20);
      ctx.fill();
      ctx.strokeStyle = '#10b981';
      ctx.lineWidth = 2;
      this.drawRoundedRect(ctx, mx, my, 160, 70, 20);
      ctx.stroke();

      ctx.fillStyle = '#34d399';
      ctx.font = 'bold 38px "Hind Siliguri", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(metric, mx + 80, my + 50);
      ctx.restore();
    }

    ctx.restore();
  }

  /**
   * LAYER 2 TEMPLATE B: Glassmorphic Info-Cards with Radial Gauge & Spring Physics
   */
  static renderGlassmorphicGaugeLayer(ctx, width, height, frame, fps, props = {}) {
    const {
      headline = 'প্রযুক্তি ব্যবহারে সাফল্যের হার',
      subtext = 'আধুনিক অটোমেশন ও এআই টুল ব্যবহারে কাজের গতি বাড়ে বহু গুণ।',
      percentage = 85,
      badge = 'AI BENCHMARK 2026',
    } = props;

    const cardSpring = SpringEngine.spring({
      frame,
      fps,
      config: { mass: 0.95, stiffness: 115, damping: 12 },
      delay: 2,
    });

    const cardW = width * 0.88;
    const cardH = height * 0.44;
    const cardX = (width - cardW) / 2;
    const cardY = height * 0.24;

    ctx.save();
    const centerX = cardX + cardW / 2;
    const centerY = cardY + cardH / 2;
    ctx.translate(centerX, centerY);
    const scale = Math.max(0.01, cardSpring);
    ctx.scale(scale, scale);
    ctx.translate(-centerX, -centerY);

    // Frosted Card Container
    ctx.save();
    ctx.shadowColor = 'rgba(0, 0, 0, 0.8)';
    ctx.shadowBlur = 50;
    ctx.shadowOffsetY = 25;
    const cardBg = ctx.createLinearGradient(cardX, cardY, cardX, cardY + cardH);
    cardBg.addColorStop(0, 'rgba(15, 23, 42, 0.92)');
    cardBg.addColorStop(1, 'rgba(30, 41, 59, 0.80)');
    ctx.fillStyle = cardBg;
    this.drawRoundedRect(ctx, cardX, cardY, cardW, cardH, 36);
    ctx.fill();
    ctx.restore();

    ctx.strokeStyle = 'rgba(147, 51, 234, 0.45)';
    ctx.lineWidth = 2.5;
    this.drawRoundedRect(ctx, cardX, cardY, cardW, cardH, 36);
    ctx.stroke();

    this.drawHudCorners(ctx, cardX + 12, cardY + 12, cardW - 24, cardH - 24, 30, '#a855f7');

    // Badge
    const badgeW = 260;
    const badgeH = 44;
    const badgeX = cardX + 36;
    const badgeY = cardY + 36;
    ctx.fillStyle = 'rgba(168, 85, 247, 0.2)';
    this.drawRoundedRect(ctx, badgeX, badgeY, badgeW, badgeH, 22);
    ctx.fill();
    ctx.strokeStyle = '#c084fc';
    ctx.lineWidth = 1.5;
    this.drawRoundedRect(ctx, badgeX, badgeY, badgeW, badgeH, 22);
    ctx.stroke();

    ctx.fillStyle = '#e9d5ff';
    ctx.font = 'bold 20px "Hind Siliguri", sans-serif';
    ctx.fillText(badge, badgeX + 22, badgeY + 29);

    // Radial Gauge Ring
    const gaugeX = cardX + 140;
    const gaugeY = cardY + cardH * 0.62;
    const gaugeRadius = 78;

    const gaugeSpring = SpringEngine.spring({
      frame,
      fps,
      config: { mass: 1.1, stiffness: 85, damping: 14 },
      delay: 10,
    });
    const gaugeProgress = Math.max(0, Math.min(1, gaugeSpring)) * (percentage / 100);

    // Background track ring
    ctx.save();
    ctx.beginPath();
    ctx.arc(gaugeX, gaugeY, gaugeRadius, -Math.PI / 2, Math.PI * 1.5);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 14;
    ctx.stroke();

    // Progress stroke with glow
    if (gaugeProgress > 0.01) {
      ctx.beginPath();
      ctx.arc(
        gaugeX,
        gaugeY,
        gaugeRadius,
        -Math.PI / 2,
        -Math.PI / 2 + Math.PI * 2 * gaugeProgress
      );
      const strokeGrad = ctx.createLinearGradient(
        gaugeX - gaugeRadius,
        gaugeY,
        gaugeX + gaugeRadius,
        gaugeY
      );
      strokeGrad.addColorStop(0, '#a855f7');
      strokeGrad.addColorStop(1, '#38bdf8');
      ctx.strokeStyle = strokeGrad;
      ctx.lineWidth = 14;
      ctx.lineCap = 'round';
      ctx.shadowColor = '#a855f7';
      ctx.shadowBlur = 18;
      ctx.stroke();
    }

    // Center percentage counter text
    const displayNum = Math.round(gaugeProgress * 100);
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 38px "Hind Siliguri", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(`${displayNum}%`, gaugeX, gaugeY + 14);
    ctx.restore();

    // Right side text description
    const textX = cardX + 270;
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 36px "Hind Siliguri", sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(headline, textX, cardY + 160);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '24px "Hind Siliguri", sans-serif';
    ctx.fillText(subtext, textX, cardY + 220);

    ctx.restore();
  }

  /**
   * LAYER 3: Kinetic Typography Synchronized with Voiceover Cues & Word Highlights
   */
  static renderKineticTypographyLayer(ctx, width, height, frame, fps, props = {}) {
    const {
      cues = [], // [{ word: "প্রযুক্তি", startSec: 0.2, endSec: 0.7 }, ...]
      spokenText = 'সঠিক নিয়ম মেনে এআই ব্যবহার করলে সাফল্য নিশ্চিত।',
      activeColor = '#38bdf8',
      pillColor = 'rgba(56, 189, 248, 0.25)',
    } = props;

    const t = frame / fps;

    // Platform UI Safe Zone: positioned safely above bottom engagement controls (e.g., Y=76% to 84%)
    const subtitleY = height * 0.78;

    ctx.save();
    ctx.textAlign = 'center';

    if (cues && cues.length > 0) {
      // Find active word by timestamp
      let activeIndex = -1;
      for (let i = 0; i < cues.length; i++) {
        if (t >= cues[i].startSec && t <= cues[i].endSec) {
          activeIndex = i;
          break;
        }
      }
      if (activeIndex === -1 && cues.length > 0) {
        activeIndex = t > cues[cues.length - 1].endSec ? cues.length - 1 : 0;
      }

      // Render line of words with dynamic pill around active word
      const words = cues.map((c) => c.word || c);
      const font = 'bold 44px "Hind Siliguri", "Noto Sans Bengali", sans-serif';
      ctx.font = font;

      // Measure total line width to center
      const spaceWidth = ctx.measureText(' ').width;
      const wordMetrics = words.map((w) => ctx.measureText(w).width);
      const totalWidth =
        wordMetrics.reduce((a, b) => a + b, 0) + (words.length - 1) * spaceWidth;

      let curX = (width - totalWidth) / 2;

      words.forEach((w, idx) => {
        const wWidth = wordMetrics[idx];
        const isActive = idx === activeIndex;

        if (isActive) {
          // Spring pop on active word
          const activeSpring = SpringEngine.spring({
            frame: frame - Math.floor((cues[idx].startSec || 0) * fps),
            fps,
            config: { mass: 0.5, stiffness: 220, damping: 10 },
          });
          const scale = 1.0 + 0.12 * Math.max(0, activeSpring);

          ctx.save();
          const wordCenter = curX + wWidth / 2;
          ctx.translate(wordCenter, subtitleY);
          ctx.scale(scale, scale);
          ctx.translate(-wordCenter, -subtitleY);

          // Glowing background pill
          ctx.fillStyle = pillColor;
          this.drawRoundedRect(ctx, curX - 12, subtitleY - 48, wWidth + 24, 64, 16);
          ctx.fill();
          ctx.strokeStyle = activeColor;
          ctx.lineWidth = 2;
          ctx.shadowColor = activeColor;
          ctx.shadowBlur = 14;
          this.drawRoundedRect(ctx, curX - 12, subtitleY - 48, wWidth + 24, 64, 16);
          ctx.stroke();

          // Active highlighted text
          ctx.fillStyle = '#ffffff';
          ctx.textAlign = 'left';
          ctx.fillText(w, curX, subtitleY);
          ctx.restore();
        } else {
          // Inactive regular text
          ctx.save();
          ctx.fillStyle = 'rgba(255, 255, 255, 0.70)';
          ctx.textAlign = 'left';
          ctx.fillText(w, curX, subtitleY);
          ctx.restore();
        }

        curX += wWidth + spaceWidth;
      });
    } else {
      // Fallback single subtitle line with gentle breathing spring
      const textSpring = SpringEngine.spring({
        frame,
        fps,
        config: { mass: 0.7, stiffness: 140, damping: 12 },
        delay: 4,
      });
      ctx.save();
      const scale = Math.max(0.01, textSpring);
      ctx.translate(width / 2, subtitleY);
      ctx.scale(scale, scale);
      ctx.translate(-width / 2, -subtitleY);

      // Pill container
      const font = 'bold 42px "Hind Siliguri", "Noto Sans Bengali", sans-serif';
      ctx.font = font;
      const textWidth = ctx.measureText(spokenText).width;
      const pillW = textWidth + 80;
      const pillH = 76;
      const pillX = (width - pillW) / 2;
      const pillY = subtitleY - 54;

      ctx.fillStyle = 'rgba(15, 23, 42, 0.88)';
      this.drawRoundedRect(ctx, pillX, pillY, pillW, pillH, 24);
      ctx.fill();
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.5)';
      ctx.lineWidth = 2;
      this.drawRoundedRect(ctx, pillX, pillY, pillW, pillH, 24);
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.fillText(spokenText, width / 2, subtitleY);
      ctx.restore();
    }

    ctx.restore();
  }

  /**
   * UNIFIED 3-LAYER COMPOSITOR: Combines Layer 1, Layer 2, Layer 3
   */
  static renderCompositeFrame(ctx, width, height, frame, fps, spec = {}) {
    const {
      renderLayer1 = true,
      renderLayer2 = true,
      renderLayer3 = true,
      templateType = 'data_graph', // 'data_graph' or 'glassmorphic_gauge'
      layer1Props = {},
      layer2Props = {},
      layer3Props = {},
    } = spec;

    // Layer 1: Background
    if (renderLayer1) {
      this.renderBackgroundLayer(ctx, width, height, frame, fps);
    } else {
      ctx.clearRect(0, 0, width, height);
    }

    // Layer 2: Core Asset
    if (renderLayer2) {
      if (templateType === 'glassmorphic_gauge') {
        this.renderGlassmorphicGaugeLayer(ctx, width, height, frame, fps, layer2Props);
      } else {
        this.renderDataGraphLayer(ctx, width, height, frame, fps, layer2Props);
      }
    }

    // Layer 3: Typography
    if (renderLayer3) {
      this.renderKineticTypographyLayer(ctx, width, height, frame, fps, layer3Props);
    }
  }
}

if (typeof window !== 'undefined') {
  window.MotionGraphicsTemplates = MotionGraphicsTemplates;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { MotionGraphicsTemplates };
}
