/* app.js — replydesk SPA DOM glue (T21b).
 * All logic lives in rd.js (pure, node-testable); this file only wires the
 * views: sign up / log in / session / log out / workspace, plus the T21e
 * draft flow (pure builders exported on window.rdDraft for node tests).
 */
(function () {
  'use strict';

  var rd = window.rd;
  var storage = window.localStorage;

  var authView = document.getElementById('auth-view');
  var workspaceView = document.getElementById('workspace-view');
  var greeting = document.getElementById('workspace-greeting');
  var signupForm = document.getElementById('signup-form');
  var loginForm = document.getElementById('login-form');
  var signupError = document.getElementById('signup-error');
  var loginError = document.getElementById('login-error');
  var logoutButton = document.getElementById('logout-button');
  var planView = document.getElementById('plan-view');
  var planError = document.getElementById('plan-error');
  var planLock = document.getElementById('plan-lock');
  var workspaceBody = document.getElementById('workspace-body');
  var activateButton = document.getElementById('activate-trial');
  var reviewsEl = document.getElementById('reviews');
  var previewButton = document.getElementById('preview-button');
  var previewList = document.getElementById('preview-list');
  var zeroHint = document.getElementById('zero-found-hint');
  var draftButton = document.getElementById('draft-button');
  var draftNote = document.getElementById('draft-note');

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;',
        '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function starsLabel(n) {
    var out = '';
    for (var i = 1; i <= 5; i++) out += (i <= n ? '\u2605' : '\u2606');
    return out;
  }

  // Plan gate: the founding-plan card shows until the trial is activated;
  // the generation UI stays locked (Draft disabled + visible lock note).
  function refreshPlan() {
    var st = rd.planState(storage);
    if (st.signedIn && !st.plan) {
      planView.classList.remove('hidden');
      planLock.classList.remove('hidden');
      workspaceBody.classList.add('hidden');
      draftButton.disabled = true;
    } else if (st.signedIn) {
      planView.classList.add('hidden');
      planLock.classList.add('hidden');
      workspaceBody.classList.remove('hidden');
      draftButton.disabled = false;
    }
  }

  function showWorkspace(name) {
    greeting.textContent = name ? ('Your workspace — ' + name) : 'Your workspace';
    authView.classList.add('hidden');
    workspaceView.classList.remove('hidden');
    refreshPlan();
  }

  function showAuth() {
    workspaceView.classList.add('hidden');
    authView.classList.remove('hidden');
  }

  signupForm.addEventListener('submit', function (ev) {
    ev.preventDefault();
    signupError.textContent = '';
    rd.createAccount(storage, {
      name: signupForm.elements.name.value,
      email: signupForm.elements.email.value,
      password: signupForm.elements.password.value
    }).then(function (result) {
      if (result.ok) {
        signupForm.reset();
        showWorkspace(result.name);
      } else {
        signupError.textContent = result.error;
      }
    });
  });

  loginForm.addEventListener('submit', function (ev) {
    ev.preventDefault();
    loginError.textContent = '';
    rd.login(storage, {
      email: loginForm.elements.email.value,
      password: loginForm.elements.password.value
    }).then(function (result) {
      if (result.ok) {
        loginForm.reset();
        showWorkspace(result.name);
      } else {
        loginError.textContent = result.error;
      }
    });
  });

  logoutButton.addEventListener('click', function () {
    rd.logout(storage);
    previewList.innerHTML = '';
    zeroHint.classList.add('hidden');
    draftNote.textContent = '';
    showAuth();
  });

  activateButton.addEventListener('click', function () {
    planError.textContent = '';
    var result = rd.activateTrial(storage,
      new Date().toISOString().slice(0, 10));
    if (result.ok) {
      refreshPlan();
    } else {
      planError.textContent = result.error;
    }
  });

  previewButton.addEventListener('click', function () {
    zeroHint.classList.add('hidden');
    var res = rd.previewSummaries(reviewsEl.value);
    previewList.innerHTML = res.items.map(function (r) {
      return '<li><span class="stars">' + starsLabel(r.stars) + '</span> — '
        + esc(r.first) + '</li>';
    }).join('');
    if (!res.found) zeroHint.classList.remove('hidden');
  });

  // --- T21e: draft flow (ARCHITECTURE §11/§12) ------------------------------
  // Pure, node-testable builders live in rdDraft below; the click handler only
  // fetches service.json (cache-busted), calls requestDrafts, and renders.
  var OFFLINE_NOTE = 'replydesk service offline — these are editable templates; '
    + 'live model drafts connect when the service is up.';
  var DEFAULT_PROFILE = { name: 'my business', kind: 'local shop', city: 'town' };

  function defaultProfile(p) {
    return {
      name: (p && p.name) || DEFAULT_PROFILE.name,
      kind: (p && p.kind) || DEFAULT_PROFILE.kind,
      city: (p && p.city) || DEFAULT_PROFILE.city
    };
  }

  // Build card descriptors from parsed reviews plus either a live RunResult
  // JSON ({decisions:[], drafts:[]} per api.runresult_json) or — when `run` is
  // null — the offline client-side triage + labeled template path.
  function buildCards(reviews, run, profile) {
    profile = defaultProfile(profile);
    var decisions = {};
    var drafts = {};
    if (run) {
      (run.decisions || []).forEach(function (d) { decisions[d.review_id] = d; });
      (run.drafts || []).forEach(function (d) { drafts[d.review_id] = d; });
    }
    return reviews.map(function (r) {
      var dec = decisions[r.review_id];
      var category = dec ? dec.category : rd.triageReview(r).category;
      var reason = dec ? dec.reason : rd.triageReview(r).reason;
      var card = {
        review_id: r.review_id, stars: r.stars, text: r.text,
        category: category, reason: reason,
        needsHuman: category === 'needs_human',
        draftText: null, source: null, verified: null
      };
      if (card.needsHuman) return card; // no draft, no box
      var d = run ? drafts[r.review_id] : null;
      if (d) {
        card.draftText = d.text;
        card.source = d.source;
        card.verified = !!d.verified;
      } else {
        var decision = rd.triageReview(r);
        card.draftText = rd.FALLBACK_LABEL + ' '
          + rd.templateReply(decision, profile);
        card.source = rd.FALLBACK_LABEL;
        card.verified = false;
      }
      return card;
    });
  }

  // Offline path: every non-needs-human review gets a labeled template draft.
  function offlineCards(reviews, profile) {
    return {
      mode: 'offline',
      cards: buildCards(reviews, null, profile),
      note: OFFLINE_NOTE
    };
  }

  // requestDrafts({service, fetch, tone, profile, reviewsText}) — pure apart
  // from the injected fetch. Never a dead end: service not live, fetch or POST
  // failure all fall through to the offline template path.
  function requestDrafts(deps) {
    var parsed = rd.parsePaste(deps.reviewsText);
    if (parsed.error || !parsed.reviews.length) {
      return Promise.resolve({ mode: 'empty', cards: [], note: '' });
    }
    var svc = deps.service || {};
    if (svc.status !== 'live' || !svc.url) {
      return Promise.resolve(offlineCards(parsed.reviews, deps.profile));
    }
    var body = JSON.stringify({
      tone: deps.tone || '',
      profile: defaultProfile(deps.profile),
      reviews: parsed.reviews
    });
    // T22b: client-side deadline. Real model calls ran 42-70+ s tonight;
    // give them 240 s, then fall back to the offline template path below.
    var controller = typeof AbortController === 'function'
      ? new AbortController() : null;
    var timer = controller
      ? setTimeout(function () { controller.abort(); }, 240000) : null;
    return deps.fetch(svc.url + '/api/draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body,
      signal: controller ? controller.signal : undefined
    }).then(function (res) {
      if (timer) clearTimeout(timer);
      if (!res.ok) throw new Error('HTTP ' + res.status);
      return res.json();
    }).then(function (run) {
      return {
        mode: 'live',
        cards: buildCards(parsed.reviews, run, deps.profile),
        note: run.note || ''
      };
    }).catch(function () {
      return offlineCards(parsed.reviews, deps.profile);
    });
  }

  // Render cards into a container element. All review text, reasons, labels
  // and draft bodies pass through esc() — nothing raw reaches innerHTML.
  function renderCardsInto(el, cards) {
    el.innerHTML = cards.map(function (c) {
      var h = '<li><span class="stars">' + esc(starsLabel(c.stars)) + '</span> '
        + '<span class="badge">' + esc(c.category) + '</span> '
        + esc(c.reason)
        + '<p>' + esc(c.text) + '</p>';
      if (c.needsHuman) {
        h += '<p class="honest">Needs a human — no draft generated.</p></li>';
      } else {
        h += '<p class="src-label">' + esc(c.source) + ' — '
          + (c.verified ? 'verified' : 'unverified') + '</p>'
          + '<textarea rows="4">' + esc(c.draftText) + '</textarea></li>';
      }
      return h;
    }).join('');
  }

  // CDN caches can split after a push: some nodes serve the old service.json
  // while others already serve the new one. Retry a few times with a fresh
  // cache-bust each attempt and take the first config that says 'live'.
  function fetchServiceConfig(fetchLike) {
    var MAX_ATTEMPTS = 4;
    var RETRY_DELAY_MS = 700;
    var seen = [];
    function attempt(n) {
      return fetchLike('service.json?t=' + Date.now())
        .then(function (res) {
          return res.ok ? res.json()
            : { status: 'unavailable', url: null };
        })
        .catch(function () { return null; })
        .then(function (svc) {
          if (svc && svc.status === 'live') return svc;
          seen.push(svc);
          if (n >= MAX_ATTEMPTS) {
            for (var i = 0; i < seen.length; i++) {
              if (seen[i]) return seen[i]; // any well-formed config wins
            }
            return { status: 'unavailable', url: null };
          }
          return new Promise(function (resolve) {
            setTimeout(resolve, RETRY_DELAY_MS);
          }).then(function () { return attempt(n + 1); });
        });
    }
    return attempt(1);
  }

  var draftCards = document.getElementById('draft-cards');

  draftButton.addEventListener('click', function () {
    draftNote.textContent = 'Drafting…';
    fetchServiceConfig(fetch)
      .then(function (svc) {
        return requestDrafts({
          service: svc,
          fetch: fetch,
          tone: document.getElementById('tone').value,
          profile: {
            name: document.getElementById('bp-name').value,
            kind: document.getElementById('bp-kind').value,
            city: document.getElementById('bp-city').value
          },
          reviewsText: reviewsEl.value
        });
      })
      .then(function (result) {
        renderCardsInto(draftCards, result.cards);
        draftNote.textContent = result.note;
      }, function () {
        draftNote.textContent = OFFLINE_NOTE;
      });
  });

  // Test surface: pure builders, exercised node-side by tests/test_app_js_draft.py.
  window.rdDraft = {
    buildCards: buildCards,
    requestDrafts: requestDrafts,
    renderCardsInto: renderCardsInto,
    defaultProfile: defaultProfile,
    fetchServiceConfig: fetchServiceConfig,
    OFFLINE_NOTE: OFFLINE_NOTE
  };

  // Session restore: a returning visitor with a live session flag lands in
  // the workspace; everyone else sees the auth forms.
  var session = rd.sessionEmail(storage);
  if (session) {
    var accounts = JSON.parse(storage.getItem(rd.ACCOUNTS_KEY) || '{}');
    var acct = accounts[session];
    showWorkspace(acct ? acct.name : null);
  } else {
    showAuth();
  }
})();
