"""Trusted local compatibility probe; run inside Blender, never fed generated code."""
import json

import bpy


def main():
    material = bpy.data.materials.new("factory_compat_probe")
    if bpy.app.version < (5, 0, 0):
        material.use_nodes = True
    world = bpy.context.scene.world
    if bpy.app.version < (5, 0, 0):
        world.use_nodes = True
    node = material.node_tree.nodes.get("Principled BSDF") if material.node_tree else None
    print("FACTORY_API " + json.dumps({
        "version": list(bpy.app.version), "material_nodes": node is not None,
        "world_nodes": world.node_tree is not None,
        "principled_inputs": [socket.name for socket in node.inputs] if node else [],
        "cycles": hasattr(bpy.context.scene, "cycles"),
        "threads": hasattr(bpy.context.scene.render, "threads"),
    }), flush=True)


if __name__ == "__main__":
    main()
