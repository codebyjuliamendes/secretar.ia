from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.scheduling import (
    Busy,
    Rule,
    generate_slots,
    match_service,
    overlaps,
    rules_to_text,
    services_to_text,
    within_rules,
)

TZ = ZoneInfo("America/Sao_Paulo")
RULES = [Rule(0, 9 * 60, 12 * 60), Rule(0, 13 * 60, 18 * 60)]  # segunda: 09-12 e 13-18
MONDAY = datetime(2030, 1, 7, 8, 0, tzinfo=TZ)  # 07/01/2030 é segunda-feira


def test_generate_slots_respects_windows_step_and_duration():
    slots = generate_slots(
        rules=RULES, busy=[], tz=TZ, start_from=MONDAY.astimezone(UTC), days=1, duration_min=60, step_min=30
    )
    locals_ = [s.start.astimezone(TZ).strftime("%H:%M") for s in slots]
    assert locals_[0] == "09:00" and "11:00" in locals_ and "11:30" not in locals_  # 11:30+60 > 12:00
    assert "12:00" not in locals_ and "13:00" in locals_ and locals_[-1] == "17:00"
    assert all(s.end - s.start == timedelta(minutes=60) for s in slots)


def test_generate_slots_excludes_busy_and_past_and_limits():
    busy_start = datetime(2030, 1, 7, 9, 30, tzinfo=TZ).astimezone(UTC)
    busy = [Busy(busy_start, busy_start + timedelta(minutes=60))]  # 09:30-10:30 ocupado
    slots = generate_slots(
        rules=RULES, busy=busy, tz=TZ, start_from=MONDAY.astimezone(UTC), days=1, duration_min=60, step_min=30
    )
    locals_ = [s.start.astimezone(TZ).strftime("%H:%M") for s in slots]
    assert "09:00" not in locals_ and "09:30" not in locals_ and "10:00" not in locals_ and "10:30" in locals_
    later = datetime(2030, 1, 7, 16, 10, tzinfo=TZ).astimezone(UTC)
    slots2 = generate_slots(rules=RULES, busy=[], tz=TZ, start_from=later, days=1, duration_min=60, step_min=30)
    assert [s.start.astimezone(TZ).strftime("%H:%M") for s in slots2] == ["16:30", "17:00"]
    assert (
        len(
            generate_slots(
                rules=RULES,
                busy=[],
                tz=TZ,
                start_from=MONDAY.astimezone(UTC),
                days=7,
                duration_min=60,
                step_min=30,
                limit=3,
            )
        )
        == 3
    )


def test_generate_slots_skips_days_without_rules():
    tuesday = MONDAY + timedelta(days=1)
    assert (
        generate_slots(
            rules=RULES, busy=[], tz=TZ, start_from=tuesday.astimezone(UTC), days=1, duration_min=30, step_min=30
        )
        == []
    )
    assert (
        generate_slots(
            rules=[], busy=[], tz=TZ, start_from=MONDAY.astimezone(UTC), days=7, duration_min=30, step_min=30
        )
        == []
    )


def test_within_rules_and_overlaps():
    ok = datetime(2030, 1, 7, 17, 0, tzinfo=TZ).astimezone(UTC)
    assert within_rules(ok, 60, RULES, TZ)
    assert not within_rules(ok, 90, RULES, TZ)  # 17:00 + 90 min passa das 18:00
    lunch = datetime(2030, 1, 7, 12, 15, tzinfo=TZ).astimezone(UTC)
    assert not within_rules(lunch, 30, RULES, TZ)
    a = datetime(2030, 1, 1, 10, tzinfo=UTC)
    assert overlaps(a, a + timedelta(hours=1), a + timedelta(minutes=30), a + timedelta(hours=2))
    assert not overlaps(a, a + timedelta(hours=1), a + timedelta(hours=1), a + timedelta(hours=2))


def test_match_service_and_texts():
    services = [
        {"id": "1", "name": "Toxina botulínica", "durationMin": 45, "priceCents": 99000},
        {"id": "2", "name": "Peeling", "durationMin": 30, "priceCents": None},
    ]
    assert match_service(services, "peeling")["id"] == "2"
    assert match_service(services, "aplicação de toxina botulínica")["id"] == "1"
    assert match_service(services, "botox") is None
    assert match_service(services, None) is None
    txt = services_to_text(services)
    assert "Toxina botulínica (45 min, R$ 990,00)" in txt and "valor sob consulta" in txt
    assert rules_to_text(RULES) == "segunda 09:00-12:00, 13:00-18:00"
    assert "não configurados" in rules_to_text([])
