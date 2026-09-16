"""OWNER: Person A — case and entity API tests."""
import pytest
from httpx import AsyncClient

from app.models.user import User
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_create_and_list_cases(client: AsyncClient, police_user: User):
    create = await client.post(
        "/cases",
        json={"case_number": "C-100", "title": "Demo Case", "status": "open"},
        headers=auth_header(police_user),
    )
    assert create.status_code == 201
    case = create.json()
    assert case["case_number"] == "C-100"
    assert "id" in case

    listed = await client.get("/cases", headers=auth_header(police_user))
    assert listed.status_code == 200
    assert any(c["id"] == case["id"] for c in listed.json())


@pytest.mark.asyncio
async def test_citizen_cannot_create_case(client: AsyncClient, citizen_user: User):
    resp = await client.post(
        "/cases",
        json={"case_number": "C-200", "title": "Nope"},
        headers=auth_header(citizen_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_update_case(client: AsyncClient, police_user: User, citizen_user: User):
    created = await client.post(
        "/cases",
        json={"case_number": "C-300", "title": "Update Me"},
        headers=auth_header(police_user),
    )
    case_id = created.json()["id"]

    got = await client.get(f"/cases/{case_id}", headers=auth_header(citizen_user))
    assert got.status_code == 200
    assert got.json()["title"] == "Update Me"

    updated = await client.put(
        f"/cases/{case_id}",
        json={"title": "Updated Title", "status": "pending"},
        headers=auth_header(police_user),
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated Title"
    assert updated.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_entity_crud(client: AsyncClient, police_user: User):
    case = (
        await client.post(
            "/cases",
            json={"case_number": "C-400", "title": "Entity Case"},
            headers=auth_header(police_user),
        )
    ).json()

    entity = (
        await client.post(
            f"/cases/{case['id']}/entities",
            json={
                "entity_type": "person",
                "label": "Accused",
                "attributes": {"age": 40},
            },
            headers=auth_header(police_user),
        )
    ).json()
    assert entity["label"] == "Accused"
    assert entity["attributes"]["age"] == 40

    listed = await client.get(
        f"/cases/{case['id']}/entities", headers=auth_header(police_user)
    )
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    one = await client.get(
        f"/cases/{case['id']}/entities/{entity['id']}",
        headers=auth_header(police_user),
    )
    assert one.status_code == 200
    assert one.json()["id"] == entity["id"]


@pytest.mark.asyncio
async def test_unauthenticated_cases_401(client: AsyncClient):
    resp = await client.get("/cases")
    assert resp.status_code == 401
