# -*- mode: python ; coding: utf-8 -*-

import torch
import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_submodules
)


datas=[]
binaries=[]
hiddenimports=[]



# ======================
# EasyOCR
# ======================

for pkg in [

    "easyocr",

    "cv2",

    "PIL",

    "numpy",

]:

    try:

        d,b,h=collect_all(pkg)

        datas+=d

        binaries+=b

        hiddenimports+=h

    except:

        pass




# ======================
# Torch DLL
# ======================

torch_path=os.path.dirname(torch.__file__)


torch_lib=os.path.join(
    torch_path,
    "lib"
)



for f in os.listdir(torch_lib):

    if f.endswith(".dll"):

        binaries.append(

            (
                os.path.join(
                    torch_lib,
                    f
                ),
                "torch/lib"

            )

        )





# ======================
# Hidden imports
# ======================


hiddenimports += [

    "torch",

    "torch._C",

    "torch.nn",

    "torchvision",

    "easyocr",

    "cv2",

    "numpy",

    "scipy",

    "skimage",

    "yaml",

    "PIL",

    "pkg_resources",

]



hiddenimports += collect_submodules(
    "easyocr"
)



# ICO

datas.append(
    (
        "1.ico",
        "."
    )
)



a=Analysis(

    [

        "ScreenAlarm.py"

    ],

    pathex=[],

    binaries=binaries,

    datas=datas,

    hiddenimports=hiddenimports,

    hookspath=[],

    hooksconfig={},

    runtime_hooks=[],

    excludes=[

        "torch.cuda",

        "tensorboard"

    ],

    noarchive=False

)



pyz=PYZ(

    a.pure

)



exe=EXE(

    pyz,

    a.scripts,

    [],

    exclude_binaries=True,

    name="数字报警",

    icon="1.ico",

    console=False,

    upx=False

)



coll=COLLECT(

    exe,

    a.binaries,

    a.datas,

    strip=False,

    upx=False,

    name="数字报警"

)