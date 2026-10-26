"""Original, deterministic motion templates. All output passes the public Board schema."""
from .schemas import Board

KIDS = ["walk", "jump", "observe", "expression", "floating", "parallax", "magic", "sparkle"]
ENGINEERING = ["exploded", "layers", "arrows", "fluid", "gears", "highlight", "rotation", "comparison", "sequence"]


def motion_template(name, duration=4):
    if name not in KIDS+ENGINEERING:
        raise ValueError("Unknown motion template")
    if not .5 <= duration <= 60:
        raise ValueError("Template duration must be 0.5-60s")
    def key(t=0, **values):
        return {"time": t, **values}
    def layer(kind, size=.25, color="#64e8cf", **kw):
        return {"kind": kind, "size": size, "color": color, "keyframes": [key()], **kw}
    layers=[]
    camera={}
    if name in KIDS:
        keys=[key(0,x=.3,y=.6),key(duration,x=.7,y=.6)]
        if name=="walk":
            keys=[key(duration*i/8,x=.2+.6*i/8,y=.60-.025*(i%2),rotation=(-1 if i%2 else 1)*3) for i in range(9)]
        if name=="jump":keys=[key(0,y=.65),key(duration*.5,y=.35),key(duration,y=.65)]
        if name in {"expression","observe"}:keys=[key(0,x=.35,expression="curious"),key(duration*.55,x=.35,expression="surprised"),key(duration,x=.35,expression="happy")]
        layers=[layer("robot",.35,keyframes=keys)]
        if name in {"floating","observe"}:
            layers.append(layer("star",.17,"#ffe294",keyframes=[key(0,x=.7,y=.35),key(duration*.5,x=.7,y=.25,rotation=30),key(duration,x=.7,y=.35)]))
        if name=="parallax":
            layers.insert(0,layer("circle",.85,"#344b66",depth=.2,keyframes=[key(0,x=.5,y=.7)]))
            layers.append(layer("circle",.4,"#42634d",depth=1.5,keyframes=[key(0,x=.8,y=.9)]))
            camera={"pan_x":.1,"pan_y":0,"zoom":1.05}
        if name in {"magic","sparkle"}:
            layers.append(layer("particles",.9,"#ffe294"))
    else:
        if name in {"gears","rotation"}:
            layers=[layer("gear",.35,keyframes=[key(0,x=.35),key(duration,x=.35,rotation=180)]),
                    layer("gear",.25,"#e4b37e",keyframes=[key(0,x=.64),key(duration,x=.64,rotation=-252)])]
        elif name=="fluid":
            layers=[layer("rectangle",.7,"#2b4058")]+[layer("circle",.055,"#76c9ee",keyframes=[key(0,x=.25+i*.06,y=.5),key(duration,x=.7+i*.02,y=.5)]) for i in range(5)]
        elif name in {"exploded","layers","sequence"}:
            layers=[layer("rectangle",.35,color,keyframes=[key(0,x=.5,y=.5),key(duration,x=.5,y=.28+i*.22)]) for i,color in enumerate(["#83b8cc","#e3b47e","#97c8a4"])]
        elif name=="arrows":
            layers=[layer("arrow",.4,keyframes=[key(0,x=.3,opacity=.3),key(duration,x=.7,opacity=1)])]
        elif name=="highlight":
            layers=[layer("rectangle",.4,"#e3b47e"),layer("circle",.65,"#64e8cf",keyframes=[key(0,opacity=.08),key(duration*.5,opacity=.35),key(duration,opacity=.08)])]
        elif name=="comparison":
            layers=[layer("rectangle",.3,"#e3b47e",keyframes=[key(x=.25)]),layer("circle",.3,"#64e8cf",keyframes=[key(x=.75)]),layer("arrow",.15,"#ffffff")]
    return Board.model_validate({"scenes":[{"duration":duration,"background":"#132139","layers":layers,
        "camera":camera,"transition":"magic" if name=="magic" else "fade"}]})
