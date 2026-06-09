from zoneinfo import ZoneInfo

PH_TZ = ZoneInfo("Asia/Manila")


def calculate_attendance_hours(
    attendance,
    schedule_template,
):
    if not attendance.check_in_time or not attendance.check_out_time:
        return {
            "regular_hours": 0,
            "undertime_hours": 0,
            "overtime_hours": 0,
        }

    check_in = attendance.check_in_time.astimezone(PH_TZ)

    check_out = attendance.check_out_time.astimezone(PH_TZ)

    day_name = attendance.attendance_date.strftime("%A").lower()

    schedule_in = getattr(
        schedule_template,
        f"{day_name}_in",
    )

    schedule_out = getattr(
        schedule_template,
        f"{day_name}_out",
    )

    if not schedule_in or not schedule_out:
        return {
            "regular_hours": 0,
            "undertime_hours": 0,
            "overtime_hours": 0,
        }

    schedule_in_minutes = schedule_in.hour * 60 + schedule_in.minute

    schedule_out_minutes = schedule_out.hour * 60 + schedule_out.minute

    actual_in_minutes = check_in.hour * 60 + check_in.minute

    actual_out_minutes = check_out.hour * 60 + check_out.minute

    late_minutes = max(
        0,
        actual_in_minutes - schedule_in_minutes,
    )

    undertime_minutes = max(
        0,
        schedule_out_minutes - actual_out_minutes,
    )

    overtime_minutes = max(
        0,
        actual_out_minutes - schedule_out_minutes,
    )

    overtime_hours = overtime_minutes / 60 if overtime_minutes > 30 else 0

    undertime_hours = (late_minutes + undertime_minutes) / 60

    regular_hours = max(
        0,
        8 - undertime_hours,
    )

    return {
        "regular_hours": round(
            regular_hours,
            2,
        ),
        "undertime_hours": round(
            undertime_hours,
            2,
        ),
        "overtime_hours": round(
            overtime_hours,
            2,
        ),
    }
