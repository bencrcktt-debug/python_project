import importlib
import sys


_ENTRYPOINT_MODULE = "tfl_app.entrypoints.streamlit_app"


def main() -> None:
    module = sys.modules.get(_ENTRYPOINT_MODULE)
    if module is None:
        module = importlib.import_module(_ENTRYPOINT_MODULE)
    else:
        module = importlib.reload(module)
    module.render_app()


main()
