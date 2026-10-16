// Envia o token CSRF em toda requisição HTMX
document.addEventListener("htmx:configRequest", (e) => {
  const token = document.querySelector('meta[name="csrf-token"]')?.content;
  if (token) e.detail.headers["X-CSRF-Token"] = token;
});

// Painel lateral: fecha no X, no Esc ou clicando fora
const closePanel = () => {
  const panel = document.getElementById("panel");
  if (panel) panel.innerHTML = "";
};
document.addEventListener("click", (e) => {
  if (e.target.closest("[data-close-panel]")) return closePanel();
  const panel = document.getElementById("panel");
  if (panel && panel.children.length && !panel.contains(e.target) && !e.target.closest("[hx-get]")) closePanel();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closePanel();
});
