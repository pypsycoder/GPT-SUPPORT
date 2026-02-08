/**
 * Shared auth helper for patient pages.
 *
 * Usage in any patient page JS:
 *   const user = await window.PatientAuth.requireAuth();
 *   // user.patient_token is available for legacy API calls
 *
 * If the patient is not authenticated, they are redirected to /login.
 * If consent is not given, they are redirected to /consent.
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

  /**
   * Get the patient_token for legacy API calls.
   * Falls back to extracting from URL for backward compatibility.
   */
  function getPatientToken() {
    if (_cachedUser && _cachedUser.patient_token) {
      return _cachedUser.patient_token;
    }
    // Fallback: extract from URL /p/{token}/...
    var parts = window.location.pathname.split('/').filter(Boolean);
    var pIndex = parts.indexOf('p');
    if (pIndex !== -1 && parts.length > pIndex + 1) {
      return parts[pIndex + 1];
    }
    return null;
  }

  window.PatientAuth = {
    requireAuth: requireAuth,
    fetchCurrentUser: fetchCurrentUser,
    getPatientToken: getPatientToken,
  };
})();
