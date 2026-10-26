"""Trusted optional lightweight Blender demonstration, never generated Python."""

import sys

import bpy

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.2)
obj = bpy.context.object
obj.rotation_euler = (0, 0, 0)
obj.keyframe_insert(data_path="rotation_euler", frame=1)
obj.rotation_euler.z = 3.14159
obj.keyframe_insert(data_path="rotation_euler", frame=48)
bpy.ops.object.light_add(type="AREA", location=(0, -3, 4))
bpy.context.object.data.energy = 400
bpy.ops.object.camera_add(location=(0, -5, 3), rotation=(1.03, 0, 0))
scene = bpy.context.scene
scene.camera = bpy.context.object
scene.render.engine = "BLENDER_EEVEE_NEXT"
scene.render.resolution_x = 360
scene.render.resolution_y = 640
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.frame_end = 48
scene.render.image_settings.file_format = "PNG"
scene.render.filepath = sys.argv[sys.argv.index("--") + 1]
bpy.ops.render.render(animation=True)
