/* rd.js — replydesk in-browser parser (T21a).
 * Port of replydesk/paste_parse.py `parse_paste` per ARCHITECTURE §11:
 * manual '5 | text' lines or a heuristic page-copy parse (Google/Yelp),
 * never throws, returns [] when nothing usable parses.
 * Vanilla JS, no build tooling; exposes the global `rd` namespace.
 */
(function (global) {
  'use strict';

  // --- regex tables (mirrors paste_parse.py) -------------------------------
  var FULL_STAR_CHARS = ['\u2605', '\u2b50', '\ue838'];
  var RUN_FILLER_CHARS = '\ue8dc\ue80d\ue5d4\ue88e';
  var GLYPH_RUN_RE = new RegExp(
    '^[\u2605\u2606\u2b50\u00bd\ue838' + RUN_FILLER_CHARS + '\\s]*[\u2605\ue838]' +
    '[\u2605\u2606\u2b50\u00bd\ue838' + RUN_FILLER_CHARS + '\\s]*$');
  // Note: \ue838 must stay in the outer classes too — real Google star rows are
  // made entirely of it, so a run like \ue838\ue838\ue838 must match via the
  // leading/trailing classes, not the single mandatory center char.
  var NUMERIC_ANCHOR_RE = /^\s*(?:rated\s+)?([1-5])\s*(?:\/|out\s+of)\s*5\s*[.:)]?\s*$/i;
  var DATE_RE = /^(?:just\s+now|a\s+few\s+seconds\s+ago|(?:a|\d+)\s+(?:second|minute|hour|day|week|month|year)s?\s+ago)$/i;
  var NAME_RE = /^(?:[A-Z][\w'.-]*\s+){1,3}[A-Z][\w'.-]*$/;
  var CALENDAR_DATE_RE = /^(?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,?\s*\d{4})?|\d{1,2}\/\d{1,2}\/\d{2,4})$/i;
  var MANUAL_FIRST_RE = /^\s*[1-9]\d*\s*\|/;

  var NOISE_PATTERNS = [
    /response\s+from\s+(the\s+)?(owner|business)|owner\s+responded/i,
    /^(like|share|see\s+more|see\s+less|read\s+more|read\s+less|helpful|translate[^(]*(\([^)]*\))?)$/i,
    /^(share|embed|flag|helpful|order\s+online|get\s+directions|save|claim\s+this\s+business|suggest\s+an\s+edit|write\s+a\s+review|add\s+a\s+photo|not\s+helpful|mark\s+as\s+helpful)$/i,
    /^elite\s+\d{4}$/i,
    /^\d+[+\s]*(friends?|reviews?|photos?|contributions?|followers?)\b/i,
    /^\d+\s+(years?|months?)\s+on\s+(google|yelp)\b/i,
    /^(local\s+guide|\u00b7|\|)+/i
  ];

  // --- helpers --------------------------------------------------------------
  function isNoise(line) {
    return NOISE_PATTERNS.some(function (p) { return p.test(line); });
  }

  function anchorStars(line) {
    if (GLYPH_RUN_RE.test(line)) {
      var full = 0;
      FULL_STAR_CHARS.forEach(function (ch) {
        full += line.split(ch).length - 1;
      });
      if (!full) return null;
      return Math.max(1, Math.min(5, full));
    }
    var m = NUMERIC_ANCHOR_RE.exec(line);
    return m ? parseInt(m[1], 10) : null;
  }

  function isScaffolding(line) {
    line = line.trim();
    if (DATE_RE.test(line) || CALENDAR_DATE_RE.test(line)) return true;
    return line.length <= 40 && NAME_RE.test(line);
  }

  // --- manual mode ----------------------------------------------------------
  // Returns {reviews: [...], error: string|null} — JS has no exceptions across
  // the port boundary; error carries the Python message text when raised there.
  function parseReviews(text) {
    var reviews = [];
    var lines = text.split(/\r\n|\r|\n/);
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (!line.trim()) continue;
      var idx = line.indexOf('|');
      if (idx === -1) {
        return { reviews: [], error: 'line ' + (i + 1) + ": expected '5 | review text' (missing '|')" };
      }
      var stars = line.slice(0, idx).trim();
      var body = line.slice(idx + 1).trim();
      if (!/^\d+$/.test(stars) || parseInt(stars, 10) < 1 || parseInt(stars, 10) > 5) {
        return { reviews: [], error: 'line ' + (i + 1) + ': rating "' + stars + '" is not a whole number from 1 to 5' };
      }
      if (!body) {
        return { reviews: [], error: 'line ' + (i + 1) + ': review text is empty' };
      }
      reviews.push({ review_id: 'r' + (reviews.length + 1), stars: parseInt(stars, 10), text: body });
    }
    return { reviews: reviews, error: null };
  }

  // --- entry point ----------------------------------------------------------
  // Returns {reviews: [...], error: string|null}; never throws.
  function parsePaste(text) {
    try {
      if (!text || !text.trim()) return { reviews: [], error: null };
      var first = null;
      var lines = text.split(/\r\n|\r|\n/);
      for (var i = 0; i < lines.length; i++) {
        if (lines[i].trim()) { first = lines[i]; break; }
      }
      if (MANUAL_FIRST_RE.test(first)) return parseReviews(text);

      var reviews = [];
      var stars = null;
      var bodyLines = [];
      var trailing = false;

      function closeSegment() {
        if (stars !== null) {
          var body = bodyLines.join(' ').replace(/\s+/g, ' ').trim();
          if (body) {
            reviews.push({ review_id: 'p' + (reviews.length + 1), stars: stars, text: body });
          }
        }
        stars = null;
        bodyLines = [];
        trailing = false;
      }

      lines.forEach(function (raw) {
        var line = raw.trim();
        if (!line) return;
        var anchor = anchorStars(line);
        if (anchor !== null) {
          closeSegment();
          stars = anchor;
        } else if (stars === null) {
          return; // scaffolding/noise before the first anchor: dropped
        } else if (isScaffolding(line)) {
          return;
        } else if (isNoise(line)) {
          trailing = true; // noise line: rest of segment untrusted, dropped
        } else if (trailing) {
          return;
        } else {
          bodyLines.push(line);
        }
      });
      closeSegment();
      return { reviews: reviews, error: null };
    } catch (e) {
      return { reviews: [], error: String(e) };
    }
  }

  global.rd = { parsePaste: parsePaste, parseReviews: parseReviews };
})(typeof window !== 'undefined' ? window : globalThis);
