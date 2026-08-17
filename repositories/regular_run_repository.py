from database.client import get_supabase_admin_client, get_supabase_client


REGULAR_RUN_COLUMNS = (
    "regular_run_id,run_type,title,run_date,start_time,location,course_name,"
    "distance_km,target_pace,after_party,participant_count,attendee_names,memo,source_image_name,"
    "source_image_bucket,source_image_path,source_image_mime_type,source_image_size,"
    "raw_ocr_text,source_hash,created_by,created_at"
)

REGULAR_RUN_IMAGE_BUCKET = "regular-run-captures"


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


def list_regular_run_distance_rows() -> list[dict]:
    response = (
        get_supabase_client()
        .table("regular_runs")
        .select("run_date,distance_km,participant_count")
        .order("run_date")
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


def update_regular_run(regular_run_id: int, values: dict) -> dict:
    response = (
        get_supabase_admin_client()
        .table("regular_runs")
        .update(values)
        .eq("regular_run_id", int(regular_run_id))
        .execute()
    )
    return (response.data or [values])[0]


def delete_regular_run(regular_run_id: int) -> None:
    (
        get_supabase_admin_client()
        .table("regular_runs")
        .delete()
        .eq("regular_run_id", int(regular_run_id))
        .execute()
    )


def find_regular_run_by_source_hash(source_hash: str) -> dict | None:
    response = (
        get_supabase_admin_client()
        .table("regular_runs")
        .select("regular_run_id,title,run_date,run_type")
        .eq("source_hash", source_hash)
        .limit(1)
        .execute()
    )
    return (response.data or [None])[0]


def upload_regular_run_image(
    *,
    path: str,
    data: bytes,
    content_type: str,
) -> None:
    (
        get_supabase_admin_client()
        .storage.from_(REGULAR_RUN_IMAGE_BUCKET)
        .upload(
            path=path,
            file=data,
            file_options={
                "content-type": content_type,
                "cache-control": "3600",
                "upsert": "false",
            },
        )
    )


def remove_regular_run_image(path: str) -> None:
    get_supabase_admin_client().storage.from_(REGULAR_RUN_IMAGE_BUCKET).remove([path])
