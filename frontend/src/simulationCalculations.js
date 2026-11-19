/**
 * Academic Simulation benchmark calculation rules:
 * - Baseline 50% and observed 60% => +10 percentage points and +20% relative change
 * - Baseline 0 => absolute difference valid, relative change is 'Unavailable'
 * - Incompatible units or missing values => do not calculate difference
 * - Decreases retain their sign (e.g. -15 percentage points, -25% relative change)
 */
export function calculateBenchmarkDifference({ baseline, observed, unit = '' }) {
  if (baseline === '' || baseline === null || baseline === undefined ||
      observed === '' || observed === null || observed === undefined) {
    return null;
  }

  const b = parseFloat(baseline);
  const o = parseFloat(observed);

  if (Number.isNaN(b) || Number.isNaN(o)) {
    return null;
  }

  const diff = o - b;
  const isZeroDiff = Math.abs(diff) < 1e-9;
  const sign = diff > 0 ? '+' : diff < 0 ? '-' : '';
  const absDiffVal = Math.abs(diff);

  const cleanUnit = (unit || '').trim().toLowerCase();
  const isPercentUnit = cleanUnit === '%' || cleanUnit === 'percent' || cleanUnit === 'percentage points';

  // Absolute difference format
  let absoluteText = '';
  const formattedVal = Number.isInteger(diff) ? Math.abs(diff).toString() : absDiffVal.toFixed(2).replace(/\.?0+$/, '');
  
  if (isPercentUnit) {
    absoluteText = `${isZeroDiff ? '0' : sign + formattedVal} percentage points`;
  } else if (cleanUnit) {
    absoluteText = `${isZeroDiff ? '0' : sign + formattedVal} ${unit.trim()}`;
  } else {
    absoluteText = `${isZeroDiff ? '0' : sign + formattedVal}`;
  }

  // Relative change format
  let relativeText = '';
  if (Math.abs(b) < 1e-9) {
    relativeText = 'Unavailable (zero baseline)';
  } else {
    const rel = (diff / Math.abs(b)) * 100;
    const relSign = rel > 0 ? '+' : rel < 0 ? '-' : '';
    const formattedRel = Number.isInteger(rel) ? Math.abs(rel).toString() : Math.abs(rel).toFixed(1).replace(/\.?0+$/, '');
    relativeText = Math.abs(rel) < 1e-9 ? '0%' : `${relSign}${formattedRel}% relative change`;
  }

  return {
    diff,
    absoluteText,
    relativeText,
    isIncrease: diff > 0,
    isDecrease: diff < 0,
    isZero: isZeroDiff,
  };
}
