from database.client import get_supabase_admin_client, get_supabase_client


COURSE_COLUMNS = (
    "activity_id,name,run_date,started_at,ended_at,duration_seconds,"
    "distance_km,elevation_gain_m,point_count,paths,location_name,"
    "description,tags,source_hash,uploaded_by,created_at,updated_at"
)


def list_courses() -> list[dict]:
    try:
        client = get_supabase_admin_client()
    except RuntimeError:
        client = get_supabase_client()

    response = (
        client
        .table("running_activities")
        .select(COURSE_COLUMNS)
        .order("run_date", desc=True)
        .execute()
    )
    return response.data or []


def insert_course(row: dict) -> dict:
    response = (
        get_supabase_admin_client()
        .table("running_activities")
        .insert(row)
        .execute()
    )
    return (response.data or [row])[0]


def delete_course(activity_id: int) -> None:
    (
        get_supabase_admin_client()
        .table("running_activities")
        .delete()
        .eq("activity_id", activity_id)
        .execute()
    )
