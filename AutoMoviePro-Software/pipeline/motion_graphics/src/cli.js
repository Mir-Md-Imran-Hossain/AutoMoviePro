#!/usr/bin/env node
/**
 * AutoMovie Pro — Motion Graphics Engine CLI
 * -------------------------------------------
 * Usage:
 *   node src/cli.js --spec <path_to_spec.json> --output <out.mp4> [--fps 30] [--duration 3.5] [--transparent]
 */

const fs = require('fs');
const path = require('path');
const { HeadlessMotionRenderer } = require('./renderer');

async function main() {
  const args = process.argv.slice(2);
  const options = {
    fps: 30,
    durationSec: 4.0,
    width: 1080,
    height: 1920,
    transparent: false,
    spec: {},
  };

  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === '--spec' && args[i + 1]) {
      const specPath = path.resolve(args[++i]);
      if (fs.existsSync(specPath)) {
        options.spec = JSON.parse(fs.readFileSync(specPath, 'utf8'));
      } else {
        console.error(`Spec file not found: ${specPath}`);
        process.exit(1);
      }
    } else if (arg === '--output' && args[i + 1]) {
      options.outputPath = path.resolve(args[++i]);
    } else if (arg === '--fps' && args[i + 1]) {
      options.fps = parseInt(args[++i], 10);
    } else if (arg === '--duration' && args[i + 1]) {
      options.durationSec = parseFloat(args[++i]);
    } else if (arg === '--width' && args[i + 1]) {
      options.width = parseInt(args[++i], 10);
    } else if (arg === '--height' && args[i + 1]) {
      options.height = parseInt(args[++i], 10);
    } else if (arg === '--transparent') {
      options.transparent = true;
    }
  }

  if (!options.outputPath) {
    console.error('Error: --output is required');
    process.exit(1);
  }

  try {
    const result = await HeadlessMotionRenderer.render(options);
    console.log('RENDER_RESULT_JSON:' + JSON.stringify(result));
    process.exit(0);
  } catch (err) {
    console.error('Render failed:', err);
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
