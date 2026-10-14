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

  function showWorkspace(name) {
    greeting.textContent = name ? ('Your workspace — ' + name) : 'Your workspace';
    authView.classList.add('hidden');
    workspaceView.classList.remove('hidden');
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
    showAuth();
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
