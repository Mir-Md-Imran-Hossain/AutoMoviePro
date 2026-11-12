/**
 * AutoMovie Pro — Headless Motion Graphics Renderer (Node.js + Playwright + FFmpeg)
 * ----------------------------------------------------------------------------------
 * Renders React/Motion Canvas style vector compositions frame-by-frame with 
 * 100% deterministic Spring Physics into high-FPS MP4 or Transparent ProRes/VP9 video layers.
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { chromium } = require('playwright-core');

const BASE_DIR = path.resolve(__dirname, '..', '..', '..');

// Helper to resolve local browser executable
function resolveChromiumExecutable() {
  const candidates = [
    path.join(BASE_DIR, 'data', 'playwright_browsers', 'chromium_headless_shell-1234', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe'),
    path.join(BASE_DIR, 'data', 'playwright_browsers', 'chromium-1234', 'chrome-win', 'chrome.exe'),
    path.join(process.env.LOCALAPPDATA || '', 'ms-playwright', 'chromium_headless_shell-1234', 'chrome-headless-shell-win64', 'chrome-headless-shell.exe'),
    path.join(process.env.LOCALAPPDATA || '', 'ms-playwright', 'chromium-1234', 'chrome-win', 'chrome.exe'),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return null;
}

// Helper to resolve FFmpeg binary
function resolveFfmpegExecutable() {
  const candidates = [
    path.join(BASE_DIR, 'ffmpeg-8.1.1-full_build', 'ffmpeg-8.1.1-full_build', 'bin', 'ffmpeg.exe'),
    path.join(BASE_DIR, 'ffmpeg-8.1.1-full_build', 'bin', 'ffmpeg.exe'),
    path.join(BASE_DIR, 'data', 'playwright_browsers', 'ffmpeg-1011', 'ffmpeg-win64.exe'),
    'ffmpeg',
  ];
  for (const c of candidates) {
    if (c === 'ffmpeg' || fs.existsSync(c)) return c;
  }
  return 'ffmpeg';
}

/**
 * Headless Motion Graphics Renderer
 */
class HeadlessMotionRenderer {
  /**
   * Renders a motion graphics composition to an MP4 or transparent video layer.
   * @param {Object} options
   * @param {Object} options.spec - Composition specification
   * @param {string} options.outputPath - Destination video path (.mp4, .mov, or .webm)
   * @param {number} [options.fps=30] - Frame rate
   * @param {number} [options.durationSec=4.0] - Clip duration in seconds
   * @param {number} [options.width=1080] - Resolution width
   * @param {number} [options.height=1920] - Resolution height
   * @param {boolean} [options.transparent=false] - Transparent alpha channel output
   * @returns {Promise<Object>} Render statistics report
   */
  static async render(options = {}) {
    const {
      spec = {},
      outputPath,
      fps = 30,
      durationSec = 4.0,
      width = 1080,
      height = 1920,
      transparent = false,
    } = options;

    if (!outputPath) {
      throw new Error('outputPath is required for rendering');
    }

    const outDir = path.dirname(path.resolve(outputPath));
    if (!fs.existsSync(outDir)) {
      fs.mkdirSync(outDir, { recursive: true });
    }

    const totalFrames = Math.max(1, Math.round(durationSec * fps));
    const browserExe = resolveChromiumExecutable();
    const ffmpegExe = resolveFfmpegExecutable();

    if (!browserExe) {
      throw new Error('Chromium executable not found in data/playwright_browsers');
    }

    // Merge options into spec
    const fullSpec = {
      ...spec,
      width,
      height,
      fps,
      durationSec,
      renderLayer1: !transparent && spec.renderLayer1 !== false,
      renderLayer2: spec.renderLayer2 !== false,
      renderLayer3: spec.renderLayer3 !== false,
    };

    const startTime = Date.now();
    console.log(`[MotionRenderer] Launching Headless Chromium (${width}x${height} @ ${fps}fps, ${totalFrames} frames)...`);

    const browser = await chromium.launch({
      executablePath: browserExe,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-web-security',
        '--allow-file-access-from-files',
      ],
    });

    const page = await browser.newPage({
      viewport: { width, height },
      deviceScaleFactor: 1,
    });

    // Load harness HTML
    const harnessUrl = 'file://' + path.resolve(__dirname, 'harness.html').replace(/\\/g, '/');
    await page.goto(harnessUrl, { waitUntil: 'load' });

    // Initialize spec and wait for fonts
    await page.evaluate((s) => {
      window.__initHarness(s);
    }, fullSpec);

    // Wait 100ms for font face readiness
    await page.waitForTimeout(100);

    // Spawn FFmpeg with image2pipe stdin
    const isMov = outputPath.toLowerCase().endsWith('.mov');
    const isWebm = outputPath.toLowerCase().endsWith('.webm');

    let ffmpegArgs = [
      '-y',
      '-f', 'image2pipe',
      '-vcodec', 'png',
      '-r', String(fps),
      '-i', '-',
    ];

    if (transparent) {
      if (isMov) {
        // High quality ProRes 4444 with alpha
        ffmpegArgs.push('-c:v', 'prores_ks', '-profile:v', '4', '-pix_fmt', 'yuva444p10le');
      } else if (isWebm) {
        // VP9 transparent webm
        ffmpegArgs.push('-c:v', 'libvpx-vp9', '-pix_fmt', 'yuva420p', '-b:v', '2M');
      } else {
        // Fallback transparent VP9 or standard MP4
        ffmpegArgs.push('-c:v', 'libx264', '-pix_fmt', 'yuv420p');
      }
    } else {
      // High-performance H.264
      ffmpegArgs.push('-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p');
    }

    ffmpegArgs.push(path.resolve(outputPath));

    console.log(`[MotionRenderer] Piping frames to FFmpeg: ${ffmpegExe}`);
    const ffmpegProc = spawn(ffmpegExe, ffmpegArgs, {
      stdio: ['pipe', 'ignore', 'pipe'],
    });

    let ffmpegErr = '';
    ffmpegProc.stderr.on('data', (d) => {
      ffmpegErr += d.toString();
    });

    const canvasLocator = page.locator('#motionCanvas');

    // Render loop
    for (let f = 0; f < totalFrames; f++) {
      await page.evaluate((frameIdx) => {
        window.__renderFrame(frameIdx);
      }, f);

      // Grab crisp PNG buffer
      const pngBuffer = await canvasLocator.screenshot({
        omitBackground: transparent,
        type: 'png',
      });

      const canWrite = ffmpegProc.stdin.write(pngBuffer);
      if (!canWrite) {
        await new Promise((resolve) => ffmpegProc.stdin.once('drain', resolve));
      }

      if (f % 15 === 0 || f === totalFrames - 1) {
        process.stdout.write(`\r[MotionRenderer] Rendered frame ${f + 1}/${totalFrames} (${Math.round(((f + 1) / totalFrames) * 100)}%)`);
      }
    }
    console.log('');

    // Finish FFmpeg stream
    ffmpegProc.stdin.end();

    await new Promise((resolve, reject) => {
      ffmpegProc.on('close', (code) => {
        if (code === 0) resolve();
        else reject(new Error(`FFmpeg exited with code ${code}: ${ffmpegErr.slice(-500)}`));
      });
      ffmpegProc.on('error', reject);
    });

    await browser.close();

    const elapsedSec = (Date.now() - startTime) / 1000;
    const fileStat = fs.statSync(outputPath);

    console.log(`[MotionRenderer] Successfully rendered: ${outputPath} (${(fileStat.size / (1024 * 1024)).toFixed(2)} MB in ${elapsedSec.toFixed(1)}s)`);

    return {
      success: true,
      outputPath: path.resolve(outputPath),
      fileSizeBytes: fileStat.size,
      durationSec,
      totalFrames,
      fps,
      elapsedSec,
      transparent,
    };
  }
}

module.exports = {
  HeadlessMotionRenderer,
  resolveChromiumExecutable,
  resolveFfmpegExecutable,
};
