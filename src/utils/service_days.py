def parse_service_days(
    service_days: int,
) -> tuple[bool, bool, bool, bool, bool, bool, bool]:
    monday = service_days % 2 == 1
    service_days = service_days // 2
    tuesday = service_days % 2 == 1
    service_days = service_days // 2
    wednesday = service_days % 2 == 1
    service_days = service_days // 2
    thursday = service_days % 2 == 1
    service_days = service_days // 2
    friday = service_days % 2 == 1
    service_days = service_days // 2
    saturday = service_days % 2 == 1
    service_days = service_days // 2
    sunday = service_days % 2 == 1

    return (monday, tuesday, wednesday, thursday, friday, saturday, sunday)
