/**
 * Shared auth helper for patient pages.
 *
 * Usage: const user = await window.PatientAuth.requireAuth();
 * If not authenticated → redirect to /login.
 * If consent not given → redirect to /consent.
 */
(function () {
  'use strict';

  var _cachedUser = null;

  async function fetchCurrentUser() {
    if (_cachedUser) return _cachedUser;
    try {
      var resp = await fetch('/api/v1/auth/patient/me');
      if (!resp.ok) return null;
      _cachedUser = await resp.json();
      return _cachedUser;
    } catch (e) {
      return null;
    }
  }

  /**
   * Ensure the patient is authenticated and has given consent.
   * Redirects to /login or /consent if needed.
   * Returns the user object on success.
   */
  async function requireAuth() {
    var user = await fetchCurrentUser();
    if (!user) {
      window.location.href = '/login';
      // Return a never-resolving promise so calling code doesn't continue
      return new Promise(function () {});
    }
    if (!user.consent_personal_data) {
      window.location.href = '/consent';
      return new Promise(function () {});
    }
    return user;
  }

  window.PatientAuth = {
    requireAuth: requireAuth,
    fetchCurrentUser: fetchCurrentUser,
  };
})();
