"""Fluxo das páginas HTML/HTMX, como o navegador faz."""
from app.security import CSRF_HEADER, SESSION_COOKIE, csrf_token_for
from tests.conftest import make_client

HX = {"HX-Request": "true"}


async def test_full_browser_flow():
    async with make_client() as c:
        assert (await c.get("/login")).status_code == 200
        assert (await c.get("/register")).status_code == 200

        bad = await c.post("/register", data={"email": "ana@example.com", "password": "senha-segura",
                                              "password2": "outra-coisa"}, headers=HX)
        assert bad.status_code == 422 and "não são iguais" in bad.text

        resp = await c.post("/register", data={"email": "ana@example.com", "password": "senha-segura",
                                               "password2": "senha-segura"}, headers=HX)
        assert resp.headers["HX-Redirect"] == "/"
        hx = {**HX, CSRF_HEADER: csrf_token_for(c.cookies[SESSION_COOKIE])}

        home = await c.get("/?y=2026&m=11")
        assert home.status_code == 200 and "Novembro" in home.text and 'name="csrf-token"' in home.text

        # matéria inexistente: erro com link para criar
        resp = await c.post("/partials/subscriptions", data={"code": "#math01"}, headers=hx)
        assert resp.status_code == 404 and "/subjects/new?code=math01" in resp.text

        assert (await c.get("/subjects/new?code=math01")).status_code == 200
        resp = await c.post("/subjects", data={"code": "math01", "name": "Matemática", "color": "#6366f1"}, headers=hx)
        assert resp.headers["HX-Redirect"] == "/s/math01"

        page = await c.get("/s/math01")
        assert page.status_code == 200 and "#math01" in page.text

        resp = await c.post("/s/math01/events", data={"title": "Prova 1", "date": "2026-11-10",
                                                      "start_time": "14:00", "end_time": "16:00"}, headers=hx)
        assert resp.status_code == 200 and resp.headers["HX-Trigger"] == "eventsChanged"
        resp = await c.post("/s/math01/events", data={"title": "", "date": "2026-11-10"}, headers=hx)
        assert resp.status_code == 422 and "título" in resp.text

        month = await c.get("/partials/month?y=2026&m=11")
        assert "Prova 1" in month.text and "14:00" in month.text
        event_id = int(month.text.split("/partials/events/")[1].split('"')[0])

        panel = await c.get(f"/partials/events/{event_id}")
        assert "Terça, 10 de novembro · 14:00–16:00" in panel.text

        day = await c.get("/partials/day?d=2026-11-10")
        assert "Prova 1" in day.text and 'name="subject_code"' in day.text
        resp = await c.post("/events", data={"subject_code": "math01", "title": "Lista 2", "date": "2026-11-10"},
                            headers=hx)
        assert resp.headers["HX-Retarget"] == "#panel" and "Lista 2" in resp.text

        resp = await c.patch(f"/events/{event_id}", data={"title": "Prova 1 (sala 3)", "date": "2026-11-10",
                                                          "start_time": "14:00", "version": "1"}, headers=hx)
        assert resp.status_code == 200 and "Alterações salvas" in resp.text
        resp = await c.patch(f"/events/{event_id}", data={"title": "X", "date": "2026-11-10", "version": "1"},
                             headers=hx)
        assert resp.status_code == 409 and "Outra pessoa alterou" in resp.text

        assert (await c.delete(f"/events/{event_id}", headers=hx)).status_code == 200
        history = await c.get("/partials/s/math01/history")
        assert "apagou" in history.text and "Restaurar" in history.text
        assert "título: Prova 1 → Prova 1 (sala 3)" in history.text
        audit_id = int(history.text.split("/audit/")[1].split("/")[0])
        resp = await c.post(f"/audit/{audit_id}/restore", headers=hx)
        assert resp.status_code == 200 and "restaurado" in resp.text

        # sidebar, busca e toggle
        search = await c.get("/partials/search?code=mat")
        assert "#math01" in search.text and "inscrito" in search.text
        sidebar = await c.get("/partials/sidebar")
        assert 'aria-checked="true"' in sidebar.text
        subject_id = int(sidebar.text.split("/partials/subscriptions/")[1].split("/")[0])
        resp = await c.post(f"/partials/subscriptions/{subject_id}/toggle", headers=hx)
        assert resp.status_code == 204 and resp.headers["HX-Trigger"] == "subscriptionsChanged"
        assert "Prova 1" not in (await c.get("/partials/month?y=2026&m=11")).text
        assert "Escondida" in (await c.get("/partials/s/math01/action")).text

        resp = await c.post("/logout", headers=hx)
        assert resp.headers["HX-Redirect"] == "/login"
        assert (await c.get("/")).status_code == 303


async def test_missing_subject_page_is_404(ana):
    resp = await ana.get("/s/naoexiste")
    assert resp.status_code == 404 and "não existe" in resp.text


async def test_bad_month_params_fall_back_to_today(ana):
    assert (await ana.get("/?y=2026&m=13")).status_code == 200
