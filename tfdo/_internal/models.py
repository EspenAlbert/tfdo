from pydantic import BaseModel

from tfdo._internal.settings import TfDoSettings


class TfDoBaseInput(BaseModel):
    settings: TfDoSettings
    dry_run: bool = False
