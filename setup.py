from distutils.core import setup
import py2exe
import os

includes = ['requests', 'json', 'os', 'tkinter', 'ctypes', 'datetime', 'logging', 'queue', 'threading', 'modules.utils.luacfgparser']

data_files = [
    ("images", ["images/DB_logo_white_rgb_200px.png"]),
    ("fonts", ["fonts/DBNeoScreenSans-Bold.ttf", "fonts/DBNeoScreenSans-Regular.ttf"]),
    ("", ["novium.cfg", "icon.ico", "cacert.pem"])
]

setup(
    version="1.1",
    windows=[{
        "script": "Novium.py",
        "icon_resources": [(1, "icon.ico")]
    }],
    options={
        "py2exe": {
            "includes": includes,
            "bundle_files": 3,  
            "compressed": True
        }
    },
    data_files=data_files,
    zipfile=None
)
