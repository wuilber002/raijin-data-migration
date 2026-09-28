(function durationFormatComponent(global) {
  'use strict';

  const SECOND = 1;
  const MINUTE = 60 * SECOND;
  const HOUR = 60 * MINUTE;
  const DAY = 24 * HOUR;
  const MONTH = 30 * DAY;
  const YEAR = 365 * DAY;

  const pad = value => String(value).padStart(2, '0');

  function clockPart(seconds) {
    if (seconds <= 0) return '';
    const hours = Math.floor(seconds / HOUR);
    const minutes = Math.floor((seconds % HOUR) / MINUTE);
    const remainingSeconds = seconds % MINUTE;
    if (hours) return `${pad(hours)}:${pad(minutes)}:${pad(remainingSeconds)}`;
    if (minutes) return `${pad(minutes)}:${pad(remainingSeconds)}`;
    return `${remainingSeconds}s`;
  }

  /**
   * Formats elapsed or estimated seconds as an incremental duration.
   *
   * Fixed calendar units are intentional: 1 year = 365 days and
   * 1 month = 30 days. Empty leading units and zero-only suffixes are omitted.
   * Exact durations use their significant unit, including hour-based operational
   * windows such as 48h.
   */
  function formatDuration(value, { empty = '—' } = {}) {
    if (value === null || value === undefined || value === '') return empty;
    let remaining = Math.round(Number(value));
    if (!Number.isFinite(remaining) || remaining < 0) return empty;
    if (remaining === 0) return '0s';

    if (remaining % YEAR === 0) return `${remaining / YEAR}y`;
    if (remaining < YEAR && remaining % MONTH === 0) return `${remaining / MONTH}m`;
    if (remaining < MONTH && remaining % HOUR === 0) return `${remaining / HOUR}h`;
    const years = Math.floor(remaining / YEAR);
    remaining -= years * YEAR;
    const months = Math.floor(remaining / MONTH);
    remaining -= months * MONTH;
    const days = Math.floor(remaining / DAY);
    remaining -= days * DAY;

    const parts = [];
    if (years) parts.push(`${years}y`);
    if (months) parts.push(`${months}m`);
    if (days) parts.push(`${days}d`);
    const clock = clockPart(remaining);
    if (clock) parts.push(clock);
    return parts.join(' ');
  }

  global.RaijinDuration = Object.freeze({ format: formatDuration });
})(typeof window === 'undefined' ? globalThis : window);
