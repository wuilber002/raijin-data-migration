(() => {
  const portuguese = (navigator.language || "").toLowerCase().startsWith("pt");
  const form = document.getElementById("login");
  document.querySelectorAll(".pt").forEach(element => { element.style.display = portuguese ? "" : "none"; });
  document.querySelectorAll(".en").forEach(element => {
    element.style.display = portuguese ? "none" : (element.tagName === "P" ? "block" : "inline");
  });
  let csrf = "";
  let changingPassword = false;
  const responseError = async response => {
    let detail = "";
    try { detail = (await response.json()).detail || ""; } catch (_) { /* use a generic fallback */ }
    const error = new Error(detail || "request-failed");
    throw error;
  };
  const rememberCsrf = value => { csrf = value || ""; sessionStorage.setItem("raijin_csrf", csrf); };
  const message = () => document.getElementById("message");
  const showChangePassword = () => {
    changingPassword = true;
    document.querySelector(".card p")?.replaceChildren(portuguese ? "Defina uma nova senha para continuar." : "Set a new password to continue.");
    form.innerHTML = `<label>${portuguese ? "Nova senha" : "New password"}<input name="password" type="password" autocomplete="new-password" minlength="14" required></label><label>${portuguese ? "Confirmar senha" : "Confirm password"}<input name="confirmation" type="password" autocomplete="new-password" minlength="14" required></label><p id="message" role="alert"></p><button>${portuguese ? "Alterar senha" : "Change password"}</button>`;
  };
  form.addEventListener("submit", async event => {
    event.preventDefault(); event.stopImmediatePropagation();
    const button = form.querySelector("button"); button.disabled = true; message().textContent = "";
    try {
      if (changingPassword) {
        if (form.password.value !== form.confirmation.value) throw new Error("password-mismatch");
        const response = await fetch("/api/auth/password", {method: "POST", headers: {"content-type": "application/json", "x-raijin-csrf-token": csrf}, body: JSON.stringify({new_password: form.password.value})});
        if (!response.ok) await responseError(response);
        rememberCsrf((await response.json()).csrf_token);
        location.assign("/");
        return;
      }
      const response = await fetch("/api/auth/login", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({username: form.username.value, password: form.password.value})});
      if (!response.ok) await responseError(response);
      const payload = await response.json(); rememberCsrf(payload.csrf_token);
      if (payload.must_change_password) showChangePassword(); else location.assign("/");
    } catch (error) {
      message().textContent = error.message === "password-mismatch"
        ? (portuguese ? "As senhas não coincidem." : "Passwords do not match.")
        : (error.message && error.message !== "request-failed" ? error.message
          : (changingPassword ? (portuguese ? "Não foi possível alterar a senha." : "Unable to change the password.") : (portuguese ? "Não foi possível autenticar com essas credenciais." : "Unable to authenticate with these credentials.")));
    }
    finally { button.disabled = false; }
  }, true);
  (async () => {
    try {
      const response = await fetch("/api/auth/me", {cache: "no-store"});
      if (!response.ok) return;
      const payload = await response.json(); if (!payload.enabled) return;
      rememberCsrf(payload.csrf_token); if (payload.user?.must_change_password) showChangePassword(); else location.assign("/");
    } catch (_) { /* The login page remains usable while the API starts. */ }
  })();
})();
