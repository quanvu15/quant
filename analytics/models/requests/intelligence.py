"""Phase 4 — Global Intelligence request models."""
from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class MaritimeBatchRequest(BaseModel):
    imos: List[str] = Field(..., min_length=1, max_length=100)


class MaritimeAreaRequest(BaseModel):
    lat_min: float = Field(..., ge=-90, le=90)
    lat_max: float = Field(..., ge=-90, le=90)
    lon_min: float = Field(..., ge=-180, le=180)
    lon_max: float = Field(..., ge=-180, le=180)
    vessel_type: Optional[str] = None
