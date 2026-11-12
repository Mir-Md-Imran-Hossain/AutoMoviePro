/**
 * Remotion-Compatible Deterministic Spring Physics Engine
 * -------------------------------------------------------
 * Calculates damped harmonic oscillator equations frame-by-frame with zero external runtime dependencies.
 */

class SpringPhysics {
  /**
   * Calculates spring progression at a given frame.
   * @param {Object} options
   * @param {number} options.frame - Current frame index (0-based)
   * @param {number} [options.fps=30] - Frame rate
   * @param {Object} [options.config] - Spring configuration
   * @param {number} [options.config.mass=1] - Mass of the spring object
   * @param {number} [options.config.stiffness=100] - Spring stiffness constant (k)
   * @param {number} [options.config.damping=10] - Damping coefficient (c)
   * @param {number} [options.config.initialVelocity=0] - Initial velocity
   * @param {number} [options.delay=0] - Delay in frames before spring starts
   * @returns {number} Value in range [0, 1] (or slight overshoot > 1 if underdamped)
   */
  static spring({
    frame,
    fps = 30,
    config = {},
    delay = 0,
  }) {
    const adjustedFrame = frame - delay;
    if (adjustedFrame <= 0) return 0;

    const {
      mass = 1,
      stiffness = 120,
      damping = 12,
      initialVelocity = 0,
      clamp = false,
    } = config;

    const m = Math.max(0.001, mass);
    const k = Math.max(0.001, stiffness);
    const c = Math.max(0.0, damping);

    // Natural angular frequency
    const w0 = Math.sqrt(k / m);
    // Damping ratio
    const zeta = c / (2 * Math.sqrt(k * m));

    const t = adjustedFrame / fps;
    let displacement = 0;

    if (zeta < 1.0) {
      // Underdamped (oscillating / bouncy overshoot)
      const wd = w0 * Math.sqrt(1.0 - zeta * zeta);
      const b = (zeta * w0 + initialVelocity) / wd;
      const decay = Math.exp(-zeta * w0 * t);
      displacement = 1.0 - decay * (Math.cos(wd * t) + b * Math.sin(wd * t));
    } else if (Math.abs(zeta - 1.0) < 1e-4) {
      // Critically damped
      const b = initialVelocity + w0;
      const decay = Math.exp(-w0 * t);
      displacement = 1.0 - decay * (1.0 + b * t);
    } else {
      // Overdamped
      const s = w0 * Math.sqrt(zeta * zeta - 1.0);
      const r1 = -zeta * w0 + s;
      const r2 = -zeta * w0 - s;
      const b = (initialVelocity - r1) / (r2 - r1);
      const a = 1.0 - b;
      displacement = 1.0 - (a * Math.exp(r1 * t) + b * Math.exp(r2 * t));
    }

    if (clamp) {
      return Math.max(0, Math.min(1, displacement));
    }
    return displacement;
  }

  /**
   * Linear / clamped interpolation between ranges.
   */
  static interpolate(value, inputRange, outputRange, options = {}) {
    const { extrapolateLeft = 'clamp', extrapolateRight = 'clamp' } = options;

    if (inputRange.length !== outputRange.length || inputRange.length < 2) {
      throw new Error('inputRange and outputRange must have the same length >= 2');
    }

    // Left boundary
    if (value <= inputRange[0]) {
      if (extrapolateLeft === 'clamp') return outputRange[0];
      if (extrapolateLeft === 'identity') return value;
    }

    // Right boundary
    const lastIdx = inputRange.length - 1;
    if (value >= inputRange[lastIdx]) {
      if (extrapolateRight === 'clamp') return outputRange[lastIdx];
      if (extrapolateRight === 'identity') return value;
    }

    // Find segment
    let i = 0;
    while (i < lastIdx && inputRange[i + 1] < value) {
      i++;
    }

    const inStart = inputRange[i];
    const inEnd = inputRange[i + 1];
    const outStart = outputRange[i];
    const outEnd = outputRange[i + 1];

    const progress = (value - inStart) / (inEnd - inStart);
    return outStart + progress * (outEnd - outStart);
  }

  /**
   * Smooth ease-out cubic helper.
   */
  static easeOutCubic(t) {
    const clamped = Math.max(0, Math.min(1, t));
    return 1 - Math.pow(1 - clamped, 3);
  }

  /**
   * Smooth ease-in-out cubic helper.
   */
  static easeInOutCubic(t) {
    const clamped = Math.max(0, Math.min(1, t));
    return clamped < 0.5
      ? 4 * clamped * clamped * clamped
      : 1 - Math.pow(-2 * clamped + 2, 3) / 2;
  }
}

if (typeof window !== 'undefined') {
  window.SpringPhysics = SpringPhysics;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { SpringPhysics };
}
