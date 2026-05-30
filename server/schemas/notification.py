from datetime import datetime
from pydantic import BaseModel


class NotificationOut(BaseModel):
    id:             int
    user_id:        int
    type:           str
    title:          str
    message:        str
    requisition_id: int | None = None
    read:           bool
    created_at:     datetime

    model_config = {"from_attributes": True}
