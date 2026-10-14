/* app.js — replydesk SPA DOM glue (T21b).
 * All logic lives in rd.js (pure, node-testable); this file only wires the
 * views: sign up / log in / session / log out / workspace placeholder.
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

  draftButton.addEventListener('click', function () {
    draftNote.textContent = '';
    if (rd.triageReview && rd.templateReply) {
      // T21d lands these pure ports; when present, render the previewed
      // reviews through the deterministic template path.
      draftNote.textContent = 'Template drafts below — model replies connect via the service.';
      var res = rd.previewSummaries(reviewsEl.value);
      previewList.innerHTML = res.items.map(function (r) {
        var d = rd.triageReview(r);
        return '<li><span class="stars">' + starsLabel(r.stars) + '</span> — '
          + esc(d.category) + ': ' + esc(rd.FALLBACK_LABEL
            + rd.templateReply(d, { name: '', kind: '', city: '' }))
          + '</li>';
      }).join('');
    } else {
      draftNote.textContent =
        'Drafting service connects in the next build step.';
    }
  });

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
