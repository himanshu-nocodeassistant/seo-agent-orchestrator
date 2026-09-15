"""Read-only Google Search Console metrics routes."""

from fastapi import APIRouter, HTTPException, Query

from agent.gsc import GscAPIClient, GscAPIError, GscConfig

router = APIRouter(prefix="/gsc", tags=["gsc"])


def _gsc_client() -> GscAPIClient:
    config = GscConfig.from_env()
    if config is None:
        raise HTTPException(
            status_code=503,
            detail="GSC is not configured. Set GSC_SITE_URL and GSC_CREDENTIALS_PATH.",
        )
    return GscAPIClient(config)


@router.get("/page-metrics")
async def get_page_metrics(
    url: str = Query(..., min_length=1),
    change_date: str = Query(..., min_length=10, max_length=10),
    days: int = Query(28, ge=1, le=90),
):
    """Return before/after Search Console metrics for one page."""
    client = _gsc_client()
    try:
        return await client.get_page_metrics_range(url, change_date, days)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GscAPIError as exc:
        raise HTTPException(status_code=502, detail="Google Search Console request failed") from exc
    finally:
        await client.close()
