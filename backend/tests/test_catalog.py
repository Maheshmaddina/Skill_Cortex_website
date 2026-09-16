from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import RecordStatus, SlotStatus
from tests.factories import make_department, make_slot, make_webinar

DAY = timedelta(days=1)


def titles(client: TestClient, **params) -> list[str]:
    response = client.get("/webinars", params=params)
    assert response.status_code == 200
    return [card["title"] for card in response.json()["items"]]


def test_catalog_is_public_and_lists_only_active_webinars(client: TestClient, db: Session) -> None:
    make_webinar(db, title="Visible")
    make_webinar(db, title="Hidden", status=RecordStatus.INACTIVE)

    response = client.get("/webinars")  # no auth header

    assert response.status_code == 200
    assert [c["title"] for c in response.json()["items"]] == ["Visible"]
    assert response.json()["total"] == 1


def test_card_shows_next_open_slot_and_total_available_seats(client: TestClient, db: Session) -> None:
    cse = make_department(db, "CSE")
    webinar = make_webinar(db, [cse])
    make_slot(db, webinar, starts_in=-DAY)  # past
    make_slot(db, webinar, capacity=5, available_seats=0, starts_in=2 * DAY)  # full
    next_open = make_slot(db, webinar, capacity=10, available_seats=4, starts_in=3 * DAY)
    make_slot(db, webinar, capacity=20, starts_in=4 * DAY, status=SlotStatus.INACTIVE)
    make_slot(db, webinar, capacity=6, starts_in=10 * DAY)

    card = client.get("/webinars").json()["items"][0]

    assert card["next_slot"]["id"] == str(next_open.id)
    assert card["next_slot"]["available_seats"] == 4
    assert card["available_seats"] == 10  # 0 + 4 + 6 across bookable slots
    assert card["short_description"] == "Learn Python fundamentals and practical programming."
    assert [d["name"] for d in card["departments"]] == ["CSE"]


def test_card_without_open_slots(client: TestClient, db: Session) -> None:
    webinar = make_webinar(db)
    make_slot(db, webinar, capacity=3, available_seats=0)

    card = client.get("/webinars").json()["items"][0]

    assert card["next_slot"] is None
    assert card["available_seats"] == 0


def test_catalog_filters_by_department_and_search(client: TestClient, db: Session) -> None:
    cse, data_science = make_department(db, "CSE"), make_department(db, "Data Science")
    retired = make_department(db, "Retired", status=RecordStatus.INACTIVE)
    make_webinar(db, [cse], title="Python Programming")
    make_webinar(db, [data_science, retired], title="SQL 100% Practical")
    make_webinar(db, [cse, data_science], title="Data Structures")

    assert set(titles(client, department_id=str(cse.id))) == {"Python Programming", "Data Structures"}
    assert titles(client, q="python") == ["Python Programming"]
    assert titles(client, q="%") == ["SQL 100% Practical"]  # literal match, not a wildcard
    assert titles(client, department_id=str(retired.id)) == []


def test_catalog_orders_by_soonest_open_slot_and_paginates(client: TestClient, db: Session) -> None:
    make_webinar(db, title="A — no slots")
    later = make_webinar(db, title="B — later")
    make_slot(db, later, starts_in=5 * DAY)
    sooner = make_webinar(db, title="C — sooner")
    make_slot(db, sooner, starts_in=1 * DAY)

    assert titles(client) == ["C — sooner", "B — later", "A — no slots"]

    second_page = client.get("/webinars", params={"page": 2, "page_size": 2}).json()
    assert [c["title"] for c in second_page["items"]] == ["A — no slots"]
    assert (second_page["total"], second_page["page"], second_page["page_size"]) == (3, 2, 2)


def test_webinar_detail_lists_upcoming_slots_and_active_departments(client: TestClient, db: Session) -> None:
    cse = make_department(db, "CSE")
    retired = make_department(db, "Retired", status=RecordStatus.INACTIVE)
    webinar = make_webinar(db, [cse, retired])
    full = make_slot(db, webinar, capacity=5, available_seats=0, starts_in=2 * DAY)
    open_slot = make_slot(db, webinar, starts_in=3 * DAY)
    make_slot(db, webinar, starts_in=-DAY)

    detail = client.get(f"/webinars/{webinar.id}").json()

    assert detail["instructor"] == "A. Kumar"
    assert detail["description"] == "Learn Python fundamentals and practical programming."
    assert [d["name"] for d in detail["departments"]] == ["CSE"]
    assert [s["id"] for s in detail["slots"]] == [str(full.id), str(open_slot.id)]
    assert [s["is_full"] for s in detail["slots"]] == [True, False]


def test_webinar_slots_endpoint(client: TestClient, db: Session) -> None:
    webinar = make_webinar(db)
    full = make_slot(db, webinar, capacity=5, available_seats=0, starts_in=2 * DAY)
    open_slot = make_slot(db, webinar, starts_in=3 * DAY)
    make_slot(db, webinar, starts_in=4 * DAY, status=SlotStatus.CANCELLED)
    inactive_webinar = make_webinar(db, title="Retired course", status=RecordStatus.INACTIVE)

    slots = client.get(f"/webinars/{webinar.id}/slots").json()

    assert [(s["id"], s["is_full"]) for s in slots] == [(str(full.id), True), (str(open_slot.id), False)]
    assert client.get(f"/webinars/{inactive_webinar.id}/slots").status_code == 404
    assert client.get("/webinars/00000000-0000-0000-0000-000000000000").status_code == 404
