MATH = {"code": "#Math01", "name": "Matemática", "color": "#6366F1"}


async def test_create_subject_normalizes_code_and_subscribes_creator(ana):
    resp = await ana.post("/api/subjects", json=MATH)
    assert resp.status_code == 201
    assert resp.json()["code"] == "math01"
    assert resp.json()["color"] == "#6366f1"

    subs = (await ana.get("/api/subscriptions")).json()
    assert [(s["subject"]["code"], s["active"]) for s in subs] == [("math01", True)]


async def test_duplicate_and_invalid_codes(ana):
    await ana.post("/api/subjects", json=MATH)
    assert (await ana.post("/api/subjects", json={**MATH, "code": "math01"})).status_code == 409
    assert (await ana.post("/api/subjects", json={**MATH, "code": "a"})).status_code == 422
    assert (await ana.post("/api/subjects", json={**MATH, "code": "tem espaço"})).status_code == 422


async def test_search(ana):
    await ana.post("/api/subjects", json=MATH)
    await ana.post("/api/subjects", json={"code": "fis01", "name": "Física", "color": "#22c55e"})
    assert [s["code"] for s in (await ana.get("/api/subjects?q=mat")).json()] == ["math01"]
    assert [s["code"] for s in (await ana.get("/api/subjects?q=%23fis")).json()] == ["fis01"]
    assert (await ana.get("/api/subjects?q=%25")).json() == []


async def test_subscribe_toggle_unsubscribe(ana, bruno):
    await ana.post("/api/subjects", json=MATH)

    assert (await bruno.post("/api/subscriptions", json={"code": "#MATH01"})).status_code == 201
    subject_id = (await bruno.get("/api/subscriptions")).json()[0]["subject"]["id"]

    resp = await bruno.patch(f"/api/subscriptions/{subject_id}", json={"active": False})
    assert resp.json()["active"] is False
    # entrar de novo reativa, sem duplicar
    await bruno.post("/api/subscriptions", json={"code": "math01"})
    subs = (await bruno.get("/api/subscriptions")).json()
    assert len(subs) == 1 and subs[0]["active"] is True

    assert (await bruno.delete(f"/api/subscriptions/{subject_id}")).status_code == 204
    assert (await bruno.get("/api/subscriptions")).json() == []
    assert (await bruno.post("/api/subscriptions", json={"code": "naoexiste"})).status_code == 404
