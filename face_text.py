bl_info = {
    'name': 'Face Text — Engrave & Emboss in mm',
    'author': 'JoeMirai', 'version': (1, 0, 1), 'blender': (4, 2, 0),
    'location': '3D View > Sidebar > Face Text',
    'description': 'Engrave or emboss text on one selected planar face with exact millimeter height and depth',
    'category': 'Mesh',
}

import math
from pathlib import Path
import bpy
import bmesh
from mathutils import Matrix, Vector
from mathutils.geometry import tessellate_polygon, intersect_point_tri_2d
from bpy.props import StringProperty, FloatProperty, EnumProperty, PointerProperty


def mm_units(scene):
    """Blender scale_length is meters per scene unit, regardless of display unit."""
    return 0.001 / scene.unit_settings.scale_length


def face_frame(obj, scene):
    bm = bmesh.from_edit_mesh(obj.data)
    bm.normal_update()
    selected = [f for f in bm.faces if f.select]
    if len(selected) != 1:
        raise ValueError('Select exactly one face in Edit Mode.')
    face = selected[0]
    world = obj.matrix_world.copy()
    if abs(world.to_3x3().determinant()) < 1e-12:
        raise ValueError('Object has zero scale. Fix its scale first.')
    normal = (world.to_3x3().inverted().transposed() @ face.normal).normalized()
    points = [world @ v.co for v in face.verts]
    center = sum(points, Vector()) / len(points)
    if max(abs((p - center).dot(normal)) for p in points) > 0.01 * mm_units(scene):
        raise ValueError('Selected face is not planar. Choose a flat face.')
    # Project object X onto face; object Y is the fallback for side faces.
    tangent = world.to_3x3() @ Vector((1, 0, 0))
    tangent -= normal * tangent.dot(normal)
    if tangent.length < 1e-8:
        tangent = world.to_3x3() @ Vector((0, 1, 0))
        tangent -= normal * tangent.dot(normal)
    tangent.normalize()
    up = normal.cross(tangent).normalized()
    return center, tangent, up, normal, points


class FACE_TEXT_Settings(bpy.types.PropertyGroup):
    text: StringProperty(name='Text', default='123')
    height_mm: FloatProperty(name='Text height (mm)', default=5.0, min=0.01, precision=3,
        description='Actual visible height of the entire text, not the font em size')
    depth_mm: FloatProperty(name='Depth (mm)', default=0.5, min=0.001, precision=3,
        description='Distance into or out of the selected face')
    mode: EnumProperty(name='Operation', items=[('ENGRAVE', 'Engrave (in)', 'Cut into face'),
        ('EMBOSS', 'Emboss (out)', 'Raise above face')], default='ENGRAVE')
    offset_x_mm: FloatProperty(name='Horizontal (mm)', default=0.0, precision=3)
    offset_y_mm: FloatProperty(name='Vertical (mm)', default=0.0, precision=3)
    angle_deg: FloatProperty(name='Rotation (degrees)', default=0.0, precision=1)
    font_path: StringProperty(name='Font file', subtype='FILE_PATH',
        description='Optional TTF/OTF; leave blank for Blender built-in font')


class FACE_TEXT_OT_create(bpy.types.Operator):
    bl_idname = 'mesh.face_text_create'
    bl_label = 'Create Face Text'
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = 'Create a live Boolean engraving or embossing on the selected face'

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        settings = context.scene.face_text_settings
        helper = curve = mesh = modifier = None
        switched = False
        try:
            if not settings.text.strip():
                raise ValueError('Enter some text first.')
            if len(context.objects_in_mode) != 1:
                raise ValueError('Edit one object at a time.')
            center, right, up, normal, face_points = face_frame(obj, context.scene)
            font = None
            if settings.font_path:
                path = bpy.path.abspath(settings.font_path)
                if not Path(path).is_file():
                    raise ValueError('Font file does not exist.')
                font = bpy.data.fonts.load(path, check_existing=True)
            unit = mm_units(context.scene)
            angle = math.radians(settings.angle_deg)
            x_axis = right * math.cos(angle) + up * math.sin(angle)
            y_axis = -right * math.sin(angle) + up * math.cos(angle)
            origin = center + right * settings.offset_x_mm * unit + up * settings.offset_y_mm * unit
            frame = Matrix((x_axis, y_axis, normal)).transposed().to_4x4()
            frame.translation = origin
            bpy.ops.object.mode_set(mode='OBJECT')
            switched = True
            curve = bpy.data.curves.new('Face Text Font', 'FONT')
            curve.body = settings.text
            curve.size = 1.0
            curve.extrude = 0.5
            curve.resolution_u = 16
            curve.fill_mode = 'BOTH'
            if font:
                curve.font = font
            helper = bpy.data.objects.new('Face Text ' + settings.text[:32], curve)
            context.collection.objects.link(helper)
            context.view_layer.update()
            mesh = bpy.data.meshes.new_from_object(helper.evaluated_get(context.evaluated_depsgraph_get()))
            helper_name = helper.name
            bpy.data.objects.remove(helper, do_unlink=True)
            helper = bpy.data.objects.new(helper_name, mesh)
            context.collection.objects.link(helper)
            bpy.data.curves.remove(curve)
            curve = None
            if not mesh.vertices:
                raise ValueError('Font produced no text geometry.')
            mins = [min(v.co[i] for v in mesh.vertices) for i in range(3)]
            maxs = [max(v.co[i] for v in mesh.vertices) for i in range(3)]
            visible_height = maxs[1] - mins[1]
            thickness = maxs[2] - mins[2]
            if visible_height < 1e-9 or thickness < 1e-9:
                raise ValueError('Text has no usable height or thickness.')
            scale = settings.height_mm * unit / visible_height
            depth = settings.depth_mm * unit
            overlap = min(0.01 * unit, depth * 0.1)
            bottom, top = (-depth, overlap) if settings.mode == 'ENGRAVE' else (-overlap, depth)
            for v in mesh.vertices:
                x, y, z = v.co
                v.co = ((x - (mins[0] + maxs[0]) / 2) * scale,
                        (y - (mins[1] + maxs[1]) / 2) * scale,
                        bottom + (z - mins[2]) / thickness * (top - bottom))
            mesh.update()
            # Test the actual glyph footprint against the selected polygon,
            # not merely its bounding rectangle (which misses triangular faces).
            inverse = frame.inverted()
            polygon = [inverse @ p for p in face_points]
            polygon = [Vector((p.x, p.y, 0.0)) for p in polygon]
            triangles = tessellate_polygon([polygon])
            triangles = [tuple(polygon[v] if isinstance(v, int) else v for v in tri) for tri in triangles]
            footprint = {(round(v.co.x, 10), round(v.co.y, 10)) for v in mesh.vertices}
            outside = any(not any(intersect_point_tri_2d(Vector(p),
                Vector((a.x, a.y)), Vector((b.x, b.y)), Vector((c.x, c.y)))
                for a, b, c in triangles) for p in footprint)
            if outside:
                width = (maxs[0] - mins[0]) * scale / unit
                raise ValueError(f'Text does not fit this face: {width:.2f} mm wide x {settings.height_mm:g} mm high. Reduce height, rotate 90 degrees, adjust offsets, or select a larger face.')
            helper.matrix_world = frame
            helper.parent = obj
            helper.matrix_world = frame
            helper.display_type = 'WIRE'
            helper.hide_render = True
            helper['face_text_helper'] = True
            helper['height_mm'] = settings.height_mm
            helper['depth_mm'] = settings.depth_mm
            modifier = obj.modifiers.new('Face Text ' + settings.text[:32], 'BOOLEAN')
            modifier.operation = 'DIFFERENCE' if settings.mode == 'ENGRAVE' else 'UNION'
            modifier.solver = 'EXACT'
            modifier.object = helper
            helper.hide_set(True)
            context.view_layer.objects.active = obj
            # A Boolean is shown reliably in Object Mode. Leave the result there.
            self.report({'INFO'}, f'{settings.mode.title()}: {settings.height_mm:g} mm text, {settings.depth_mm:g} mm depth. Live Boolean created.')
            return {'FINISHED'}
        except Exception as exc:
            if modifier:
                obj.modifiers.remove(modifier)
            if helper:
                bpy.data.objects.remove(helper, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)
            if curve and curve.users == 0:
                bpy.data.curves.remove(curve)
            context.view_layer.objects.active = obj
            if switched and obj.mode != 'EDIT':
                bpy.ops.object.mode_set(mode='EDIT')
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class FACE_TEXT_OT_remove(bpy.types.Operator):
    bl_idname = 'object.face_text_remove'
    bl_label = 'Remove Last Face Text'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.mode == 'OBJECT' and context.active_object is not None

    def execute(self, context):
        obj = context.active_object
        for mod in reversed(list(obj.modifiers)):
            if mod.type == 'BOOLEAN' and mod.object and mod.object.get('face_text_helper'):
                helper = mod.object
                obj.modifiers.remove(mod)
                if not any(m.type == 'BOOLEAN' and m.object == helper for o in bpy.data.objects for m in o.modifiers):
                    mesh = helper.data
                    bpy.data.objects.remove(helper, do_unlink=True)
                    if mesh.users == 0:
                        bpy.data.meshes.remove(mesh)
                return {'FINISHED'}
        self.report({'WARNING'}, 'No Face Text Boolean found on this object.')
        return {'CANCELLED'}


class FACE_TEXT_PT_panel(bpy.types.Panel):
    bl_label = 'Face Text · millimeters'
    bl_idname = 'FACE_TEXT_PT_panel'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Face Text'

    def draw(self, context):
        layout = self.layout
        s = context.scene.face_text_settings
        layout.label(text='Edit Mode: select one flat face')
        layout.prop(s, 'text')
        layout.prop(s, 'height_mm')
        layout.prop(s, 'depth_mm')
        layout.prop(s, 'mode', expand=True)
        layout.prop(s, 'offset_x_mm')
        layout.prop(s, 'offset_y_mm')
        layout.prop(s, 'angle_deg')
        layout.prop(s, 'font_path')
        layout.operator('mesh.face_text_create', icon='FONT_DATA')
        layout.operator('object.face_text_remove', icon='TRASH')
        layout.label(text='Text must fit inside the selected face.')
        layout.label(text='Height is actual visible text height.')
        layout.label(text='Live Boolean; Ctrl+Z to undo.')
        layout.label(text='New settings apply to the next text.')


CLASSES = (FACE_TEXT_Settings, FACE_TEXT_OT_create, FACE_TEXT_OT_remove, FACE_TEXT_PT_panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.face_text_settings = PointerProperty(type=FACE_TEXT_Settings)


def unregister():
    if hasattr(bpy.types.Scene, 'face_text_settings'):
        del bpy.types.Scene.face_text_settings
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
