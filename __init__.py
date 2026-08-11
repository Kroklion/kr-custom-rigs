from . import genrig_convenience
from . import postprocess
from . import hooks

rigify_info = {
    "name": "kr-custom-rigs",
    "author": "Kroklion",
    "description":
        "Adds convenience and some additional rigs.\n",
    "link": "",
    "blender": (4, 0, 0),
}

def register():
    hooks.register()
    genrig_convenience.register()
    postprocess.register()
    pass

def unregister():
    genrig_convenience.unregister()
    postprocess.unregister()
    pass