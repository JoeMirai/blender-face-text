"""blender --background --factory-startup --python tests/test_blender.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy, bmesh
from mathutils import Vector
import face_text
face_text.register()

def volume(obj):
    bpy.context.view_layer.update()
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    bm = bmesh.new(); bm.from_mesh(mesh)
    bm.transform(obj.matrix_world)
    result = abs(bm.calc_volume())
    bm.free(); evaluated.to_mesh_clear()
    return result

def setup(scale_length, transformed=False):
    if bpy.context.object and bpy.context.object.mode != 'OBJECT': bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = scale_length
    unit = face_text.mm_units(bpy.context.scene)
    bpy.ops.mesh.primitive_cube_add(size=40 * unit)
    obj=bpy.context.object
    if transformed:
        obj.scale=(1.5, 0.8, 1.2);obj.rotation_euler=(0.3,0.5,0.4)
        obj.location=(2*unit,3*unit,4*unit)
    bpy.ops.object.mode_set(mode='EDIT')
    bm=bmesh.from_edit_mesh(obj.data)
    for f in bm.faces:f.select_set(False)
    max(bm.faces,key=lambda f:f.normal.z).select_set(True)
    bmesh.update_edit_mesh(obj.data)
    return obj,unit

for scale_length, transformed in [(1.0,False),(0.001,False),(0.001,True)]:
    for operation in ['ENGRAVE','EMBOSS']:
        obj,unit=setup(scale_length,transformed)
        center,right,up,normal,_=face_text.face_frame(obj,bpy.context.scene)
        bpy.ops.object.mode_set(mode='OBJECT');before=volume(obj);bpy.ops.object.mode_set(mode='EDIT')
        s=bpy.context.scene.face_text_settings
        s.text='123';s.height_mm=5;s.depth_mm=0.7;s.mode=operation;s.angle_deg=0
        result=bpy.ops.mesh.face_text_create()
        assert result=={'FINISHED'},result
        assert obj.mode=='OBJECT'
        helper=obj.modifiers[-1].object
        points=[helper.matrix_world @ v.co for v in helper.data.vertices]
        heights=[(p-center).dot(up) for p in points]
        depths=[(p-center).dot(normal) for p in points]
        assert abs((max(heights)-min(heights))/unit-5)<1e-4,heights
        actual=-min(depths)/unit if operation=='ENGRAVE' else max(depths)/unit
        assert abs(actual-0.7)<1e-4,actual
        after=volume(obj)
        assert after<before*0.999999 if operation=='ENGRAVE' else after>before*1.000001,(operation,before,after)
        assert bpy.ops.object.face_text_remove()=={'FINISHED'}
        assert len(obj.modifiers)==0
        print('PASS',operation,'unit scale',scale_length,'transformed',transformed,'height/depth/Boolean/removal')

# Oversized text must fail without leaving a Boolean or orphan helper.
obj,unit=setup(0.001)
s=bpy.context.scene.face_text_settings
s.height_mm=100
helpers_before=sum(bool(o.get('face_text_helper')) for o in bpy.data.objects)
try:
    result=bpy.ops.mesh.face_text_create()
except RuntimeError:
    result={'CANCELLED'}
assert result=={'CANCELLED'} and obj.mode=='EDIT' and not obj.modifiers
assert helpers_before==sum(bool(o.get('face_text_helper')) for o in bpy.data.objects)
s.height_mm=5
print('PASS oversized text rejected and cleaned up')

# Invalid selection must leave the original untouched.
obj,unit=setup(0.001)
bm=bmesh.from_edit_mesh(obj.data)
for f in bm.faces:f.select_set(False)
bmesh.update_edit_mesh(obj.data)
try:
    result=bpy.ops.mesh.face_text_create()
except RuntimeError:
    result={'CANCELLED'}
assert result=={'CANCELLED'}
assert obj.mode=='EDIT' and not obj.modifiers
bpy.ops.object.mode_set(mode='OBJECT')
face_text.unregister()
face_text.register()
face_text.unregister()
print('ALL TESTS PASSED')
