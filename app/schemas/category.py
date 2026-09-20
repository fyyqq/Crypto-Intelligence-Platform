from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    cmc_category_id: str
    name: str
    slug: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
