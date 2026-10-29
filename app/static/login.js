(() => {
  const portuguese = (navigator.language || "").toLowerCase().startsWith("pt");
  const form = document.getElementById("login");
  document.querySelectorAll(".pt").forEach(element => { element.style.display = portuguese ? "" : "none"; });
  document.querySelectorAll(".en").forEach(element => {
    element.style.display = portuguese ? "none" : (element.tagName === "P" ? "block" : "inline");
  });
  let csrf = "";
  let changingPassword = false;
  let mfaChallenge = "";
  const passwordControl = (name, label, autocomplete) => `<label>${label}<span class="password-control"><input name="${name}" type="password" autocomplete="${autocomplete}" minlength="14" required><button type="button" class="password-visibility-toggle" aria-pressed="false"><span class="password-eye" aria-hidden="true"></span></button></span></label>`;
  const installPasswordVisibilityControls = () => {
    form.querySelectorAll(".password-visibility-toggle").forEach(button => {
      const input = button.closest(".password-control")?.querySelector("input");
      if (!input || button.dataset.ready) return;
      button.dataset.ready = "true";
      const update = () => {
        const visible = input.type === "text";
        button.setAttribute("aria-pressed", String(visible));
        button.setAttribute("aria-label", visible
          ? (portuguese ? "Ocultar senha" : "Hide password")
          : (portuguese ? "Exibir senha" : "Show password"));
        button.title = button.getAttribute("aria-label");
      };
      button.addEventListener("click", () => { input.type = input.type === "password" ? "text" : "password"; update(); input.focus(); });
      update();
    });
  };
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
    form.innerHTML = `${passwordControl("password", portuguese ? "Nova senha" : "New password", "new-password")}${passwordControl("confirmation", portuguese ? "Confirmar senha" : "Confirm password", "new-password")}<p id="message" role="alert"></p><button type="submit">${portuguese ? "Alterar senha" : "Change password"}</button>`;
    installPasswordVisibilityControls();
  };
  const showMfa = () => {
    mfaChallenge = mfaChallenge || "";
    document.querySelector(".card p")?.replaceChildren(portuguese ? "Informe o código de seis dígitos do seu autenticador." : "Enter the six-digit code from your authenticator.");
    form.innerHTML = `<label>${portuguese ? "Código de autenticação" : "Authentication code"}<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required autofocus></label><p id="message" role="alert"></p><button type="submit">${portuguese ? "Verificar código" : "Verify code"}</button>`;
  };
  form.addEventListener("submit", async event => {
    event.preventDefault(); event.stopImmediatePropagation();
    const button = form.querySelector('button[type="submit"]'); button.disabled = true; message().textContent = "";
    try {
      if (changingPassword) {
        if (form.password.value !== form.confirmation.value) throw new Error("password-mismatch");
        const response = await fetch("/api/auth/password", {method: "POST", headers: {"content-type": "application/json", "x-raijin-csrf-token": csrf}, body: JSON.stringify({new_password: form.password.value})});
        if (!response.ok) await responseError(response);
        rememberCsrf((await response.json()).csrf_token);
        location.assign("/");
        return;
      }
      if (mfaChallenge) {
        const response = await fetch("/api/auth/mfa/verify", {method:"POST", headers:{"content-type":"application/json"}, body:JSON.stringify({challenge_token:mfaChallenge, code:form.code.value})});
        if (!response.ok) await responseError(response);
        const payload = await response.json(); rememberCsrf(payload.csrf_token); location.assign("/"); return;
      }
      const response = await fetch("/api/auth/login", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({username: form.username.value, password: form.password.value})});
      if (!response.ok) await responseError(response);
      const payload = await response.json();
      if (payload.mfa_required) { mfaChallenge = payload.challenge_token; showMfa(); return; }
      rememberCsrf(payload.csrf_token);
      if (payload.must_change_password) showChangePassword(); else location.assign("/");
    } catch (error) {
      message().textContent = error.message === "password-mismatch"
        ? (portuguese ? "As senhas não coincidem." : "Passwords do not match.")
        : (error.message && error.message !== "request-failed" ? error.message
          : (changingPassword ? (portuguese ? "Não foi possível alterar a senha." : "Unable to change the password.") : (portuguese ? "Não foi possível autenticar com essas credenciais." : "Unable to authenticate with these credentials.")));
    }
    finally { button.disabled = false; }
  }, true);
  installPasswordVisibilityControls();
  (async () => {
    try {
      const response = await fetch("/api/auth/me", {cache: "no-store"});
      if (!response.ok) return;
      const payload = await response.json(); if (!payload.enabled) return;
      rememberCsrf(payload.csrf_token); if (payload.user?.must_change_password) showChangePassword(); else location.assign("/");
    } catch (_) { /* The login page remains usable while the API starts. */ }
  })();
})();
