document.addEventListener("DOMContentLoaded", () => {
    const passwordInput = document.getElementById("id_password");
    const showPassword = document.getElementById("showPassword");

    if (passwordInput instanceof HTMLInputElement && showPassword instanceof HTMLInputElement) {
        showPassword.addEventListener("change", () => {
            passwordInput.type = showPassword.checked ? "text" : "password";
        });
    }

    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement) || !form.dataset.confirm) {
            return;
        }

        if (!window.confirm(form.dataset.confirm)) {
            event.preventDefault();
        }
    });

    document.querySelector("[data-print-report]")?.addEventListener("click", () => window.print());
});
