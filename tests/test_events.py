MATH = {"code": "math01", "name": "Matemática", "color": "#6366f1"}
FIS = {"code": "fis01", "name": "Física", "color": "#22c55e"}
PROVA = {"title": "Prova 1", "date": "2026-11-10"}


async def _calendar(client, frm="2026-11-01", to="2026-11-30"):
    resp = await client.get(f"/api/calendar?from={frm}&to={to}")
    assert resp.status_code == 200, resp.text
    return [e["title"] for e in resp.json()]


async def test_subscriber_sees_events_and_edits_propagate(ana, bruno):
    await ana.post("/api/subjects", json=MATH)
    ev = (await ana.post("/api/subjects/math01/events", json=PROVA)).json()
    assert ev["all_day"] is True

    assert await _calendar(bruno) == []  # ainda não assinou
    await bruno.post("/api/subscriptions", json={"code": "math01"})
    assert await _calendar(bruno) == ["Prova 1"]

    # Bruno edita; Ana vê a mudança (as datas não são copiadas)
    resp = await bruno.patch(f"/api/events/{ev['id']}", json={**PROVA, "title": "Prova 1 (adiada)",
                                                              "date": "2026-11-12", "version": 1})
    assert resp.status_code == 200 and resp.json()["version"] == 2
    assert resp.json()["updated_by"] == "bruno@example.com"
    assert await _calendar(ana) == ["Prova 1 (adiada)"]


async def test_inactive_subject_hidden_from_calendar(ana):
    await ana.post("/api/subjects", json=MATH)
    await ana.post("/api/subjects", json=FIS)
    await ana.post("/api/subjects/math01/events", json=PROVA)
    await ana.post("/api/subjects/fis01/events", json={"title": "Lab", "date": "2026-11-11"})
    assert await _calendar(ana) == ["Prova 1", "Lab"]

    fis_id = next(s["subject"]["id"] for s in (await ana.get("/api/subscriptions")).json()
                  if s["subject"]["code"] == "fis01")
    await ana.patch(f"/api/subscriptions/{fis_id}", json={"active": False})
    assert await _calendar(ana) == ["Prova 1"]


async def test_version_conflict(ana, bruno):
    await ana.post("/api/subjects", json=MATH)
    ev = (await ana.post("/api/subjects/math01/events", json=PROVA)).json()
    assert (await ana.patch(f"/api/events/{ev['id']}", json={**PROVA, "title": "A", "version": 1})).status_code == 200
    # Bruno ainda estava com a versão 1 aberta
    resp = await bruno.patch(f"/api/events/{ev['id']}", json={**PROVA, "title": "B", "version": 1})
    assert resp.status_code == 409


async def test_timed_event_stays_on_local_day(ana):
    """23:30 em São Paulo já é dia seguinte em UTC; o evento não pode pular de dia."""
    await ana.post("/api/subjects", json=MATH)
    await ana.post("/api/subjects/math01/events",
                   json={"title": "Revisão", "date": "2026-11-10", "start_time": "23:30"})
    assert await _calendar(ana, "2026-11-10", "2026-11-10") == ["Revisão"]
    assert await _calendar(ana, "2026-11-11", "2026-11-11") == []


async def test_event_validation(ana):
    await ana.post("/api/subjects", json=MATH)
    bad = [
        {**PROVA, "title": "   "},
        {**PROVA, "end_time": "10:00"},
        {**PROVA, "start_time": "10:00", "end_time": "09:00"},
        {**PROVA, "date": "não é data"},
    ]
    for body in bad:
        assert (await ana.post("/api/subjects/math01/events", json=body)).status_code == 422, body
    assert (await ana.get("/api/calendar?from=2026-11-10&to=2026-11-01")).status_code == 422


async def test_history_delete_and_restore(ana, bruno):
    await ana.post("/api/subjects", json=MATH)
    await bruno.post("/api/subscriptions", json={"code": "math01"})
    ev = (await ana.post("/api/subjects/math01/events", json=PROVA)).json()
    await ana.patch(f"/api/events/{ev['id']}", json={**PROVA, "date": "2026-11-12", "version": 1})
    assert (await bruno.delete(f"/api/events/{ev['id']}")).status_code == 204
    assert await _calendar(ana) == []

    history = (await ana.get("/api/subjects/math01/history")).json()
    assert [(h["action"], h["user"]) for h in history] == [
        ("DELETE", "bruno@example.com"), ("UPDATE", "ana@example.com"), ("CREATE", "ana@example.com")]

    restored = await ana.post(f"/api/audit/{history[0]['id']}/restore")
    assert restored.status_code == 201
    assert await _calendar(ana) == ["Prova 1"]
    assert restored.json()["starts_at"].startswith("2026-11-12")
    # não dá para restaurar duas vezes, nem "restaurar" algo que não foi apagado
    assert (await ana.post(f"/api/audit/{history[0]['id']}/restore")).status_code == 409
    assert (await ana.post(f"/api/audit/{history[1]['id']}/restore")).status_code == 422


async def test_deleting_subject_events_cascade_on_unknown_event(ana):
    assert (await ana.patch("/api/events/999", json={**PROVA, "version": 1})).status_code == 404
    assert (await ana.delete("/api/events/999")).status_code == 404
