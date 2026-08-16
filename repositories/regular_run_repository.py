from database.client import get_supabase_admin_client, get_supabase_client


REGULAR_RUN_COLUMNS = (
    "regular_run_id,title,run_date,start_time,location,course_name,"
    "distance_km,target_pace,participant_count,memo,source_image_name,"
    "raw_ocr_text,source_hash,created_by,created_at"
)


def list_regular_runs() -> list[dict]:
    try:
        client = get_supabase_admin_client()
    except RuntimeError:
        client = get_supabase_client()

    response = (
        client.table("regular_runs")
        .select(REGULAR_RUN_COLUMNS)
        .order("run_date", desc=True)
        .order("start_time", desc=True)
        .execute()
    )
    return response.data or []


def insert_regular_run(row: dict) -> dict:
    response = (
        get_supabase_admin_client()
        .table("regular_runs")
        .insert(row)
        .execute()
    )
    return (response.data or [row])[0]
