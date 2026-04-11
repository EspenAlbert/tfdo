from pathlib import Path

from pydantic import BaseModel

from tfdo._internal.inspect.hcl_resource_paths import HclResourcePathsResult, collect_resource_argument_paths


class InspectHclPathsInput(BaseModel):
    root: Path
    include_hidden: bool = False


def inspect_hcl_paths(input_model: InspectHclPathsInput) -> HclResourcePathsResult:
    return collect_resource_argument_paths(input_model.root.resolve(), include_hidden=input_model.include_hidden)
