from shutil import which

from tfdo._internal.settings import TfDoSettings


class MiseMissingError(RuntimeError):
    pass


def resolve_binary(settings: TfDoSettings) -> str:
    if settings.tf_version is None:
        return settings.binary
    if which("mise") is None:
        raise MiseMissingError(
            f"--tf-version={settings.tf_version} requires mise on PATH. "
            "Install mise: https://mise.jdx.dev/getting-started.html"
        )
    return f"mise x {settings.binary}@{settings.tf_version} -- {settings.binary}"
