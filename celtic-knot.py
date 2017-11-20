# Blender plugin for generating celtic knot curves from 3d meshes
# See README for more information
#
# The MIT License (MIT)
#
# Copyright (c) 2013 Adam Newgas
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

bl_info = {
    "name": "Celtic Knot",
    "description": "",
    "author": "Adam Newgas",
    "version": (0,1,2),
    "blender": (2, 68, 0),
    "location": "View3D > Add > Curve",
    "warning": "",
    "wiki_url": "https://github.com/BorisTheBrave/celtic-knot/wiki",
    "category": "Add Curve"}

import bpy
import bmesh
from collections import defaultdict
from mathutils import Vector
from math import pi, sin, cos

HANDLE_TYPE_MAP = {"AUTO": "AUTOMATIC", "ALIGNED": "ALIGNED"}

TWIST_CW = "TWIST_CW"
STRAIGHT = "STRAIGHT"
TWIST_CCW = "TWIST_CCW"
IGNORE = "IGNORE"


def get_celtic_twists(bm):
    twists = []
    for edge in bm.edges:
        if len(edge.link_loops) == 0:
            twists.append(IGNORE)
        else:
            twists.append(TWIST_CW)
    return twists


def create_bezier(context, bm, twists,
                  crossing_angle, crossing_strength, handle_type, weave_up, weave_down):
    # Cache some values
    s = sin(crossing_angle) * crossing_strength
    c = cos(crossing_angle) * crossing_strength
    orig_obj = obj = context.active_object
    # Create the new object
    curve = bpy.data.curves.new("Celtic", "CURVE")
    curve.dimensions = "3D"
    curve.twist_mode = "MINIMUM"
    obj = obj.data
    # Compute all the midpoints of each edge
    midpoints = []
    for e in obj.edges.values():
        v1 = obj.vertices[e.vertices[0]]
        v2 = obj.vertices[e.vertices[1]]
        m = (v1.co + v2.co) / 2.0
        midpoints.append(m)
    # Stores which loops the curve has already passed through
    loops_entered = defaultdict(lambda: False)
    loops_exited = defaultdict(lambda: False)

    # Loops on the boundary of a surface
    def ignorable_loop(loop):
        return len(loop.link_loops) == 0

    # Starting at loop, build a curve one vertex at a time
    # until we start where we came from
    # Forward means that for any two edges the loop crosses
    # sharing a face, it is passing through in clockwise order
    # else anticlockwise
    def make_loop(loop, forward):
        current_spline = curve.splines.new("BEZIER")
        current_spline.use_cyclic_u = True
        first = True
        # Data for the spline
        # It's faster to store in an array and load into blender
        # at once
        cos = []
        handle_lefts = []
        handle_rights = []
        while True:
            if forward:
                if loops_exited[loop]: break
                loops_exited[loop] = True
                # Follow the face around, ignoring boundary edges
                while True:
                    loop = loop.link_loop_next
                    if not ignorable_loop(loop): break
                assert loops_entered[loop] == False
                loops_entered[loop] = True
                v = loop.vert.index
                prev_loop = loop
                # Find next radial loop
                assert loop.link_loops[0] != loop
                loop = loop.link_loops[0]
                forward = loop.vert.index == v
            else:
                if loops_entered[loop]: break
                loops_entered[loop] = True
                # Follow the face around, ignoring boundary edges
                while True:
                    v = loop.vert.index
                    loop = loop.link_loop_prev
                    if not ignorable_loop(loop): break
                assert loops_exited[loop] == False
                loops_exited[loop] = True
                prev_loop = loop
                # Find next radial loop
                assert loop.link_loops[-1] != loop
                loop = loop.link_loops[-1]
                forward = loop.vert.index == v
            if not first:
                current_spline.bezier_points.add()
            first = False
            midpoint = midpoints[loop.edge.index]
            normal = loop.calc_normal() + prev_loop.calc_normal()
            normal.normalize()
            offset = weave_up if forward else weave_down
            midpoint = midpoint + offset * normal
            cos.extend(midpoint)
            if handle_type != "AUTO":
                tangent = loop.link_loop_next.vert.co - loop.vert.co
                tangent.normalize()
                binormal = normal.cross(tangent).normalized()
                if not forward: tangent *= -1
                s_binormal = s * binormal
                c_tangent = c * tangent
                handle_left = midpoint - s_binormal - c_tangent
                handle_right = midpoint + s_binormal + c_tangent
                handle_lefts.extend(handle_left)
                handle_rights.extend(handle_right)
        points = current_spline.bezier_points
        points.foreach_set("co", cos)
        if handle_type != "AUTO":
            points.foreach_set("handle_left", handle_lefts)
            points.foreach_set("handle_right", handle_rights)

    # Attempt to start a loop at each untouched loop in the entire mesh
    for face in bm.faces:
        for loop in face.loops:
            if ignorable_loop(loop): continue
            if not loops_exited[loop]: make_loop(loop, True)
            if not loops_entered[loop]: make_loop(loop, False)

    # Create an object from the curve
    from bpy_extras import object_utils
    object_utils.object_data_add(context, curve, operator=None)
    # Set the handle type (this is faster than setting it pointwise)
    bpy.ops.object.editmode_toggle()
    bpy.ops.curve.select_all(action="SELECT")
    bpy.ops.curve.handle_type_set(type=HANDLE_TYPE_MAP[handle_type])
    # Some blender versions lack the default
    bpy.ops.curve.radius_set(radius=1.0)
    bpy.ops.object.editmode_toggle()
    # Restore active selection
    curve_obj = context.active_object
    context.scene.objects.active = orig_obj
    return curve_obj


def create_pipe_from_bezier(context, curve_obj, thickness):
    bpy.ops.curve.primitive_bezier_circle_add()
    bpy.ops.transform.resize(value=(thickness,) * 3)
    circle = context.active_object
    curve_obj.data.bevel_object = circle
    curve_obj.select = True
    context.scene.objects.active = curve_obj
    # For some reason only works with keep_original=True
    bpy.ops.object.convert(target="MESH", keep_original=True)
    new_obj = context.scene.objects.active
    new_obj.select = False
    curve_obj.select = True
    circle.select = True
    bpy.ops.object.delete()
    new_obj.select = True
    context.scene.objects.active = new_obj


class CelticKnotOperator(bpy.types.Operator):
    bl_idname = "object.celtic_knot_operator"
    bl_label = "Celtic Knot"
    bl_options = {'REGISTER', 'UNDO', 'PRESET'}

    weave_up = bpy.props.FloatProperty(name="Weave Up",
                                       description="Distance to shift curve upwards over knots",
                                       subtype="DISTANCE",
                                       unit="LENGTH")
    weave_down = bpy.props.FloatProperty(name="Weave Down",
                                         description="Distance to shift curve downward under knots",
                                         subtype="DISTANCE",
                                         unit="LENGTH")
    handle_types = [("ALIGNED","Aligned","Points at a fixed crossing angle"),
                    ("AUTO","Auto","Automatic control points")]
    handle_type = bpy.props.EnumProperty(items=handle_types,
                                         name="Handle Type",
                                         description="Controls what type the bezier control points use",
                                         default="AUTO")
    crossing_angle = bpy.props.FloatProperty(name="Crossing Angle",
                                             description="Aligned only: the angle between curves in a knot",
                                             default=pi/4,
                                             min=0,max=pi/2,
                                             subtype="ANGLE",
                                             unit="ROTATION")
    crossing_strength = bpy.props.FloatProperty(name="Crossing Strength",
                                                description="Aligned only: strenth of bezier control points",
                                                soft_min=0,
                                                subtype="DISTANCE",
                                                unit="LENGTH")
    thickness = bpy.props.FloatProperty(name="Thickness",
                                        description="Radius of tube around curve (zero disables)",
                                        soft_min=0,
                                        subtype="DISTANCE",
                                        unit="LENGTH")

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        #return True
        return ((ob is not None) and
                (ob.mode == "OBJECT") and
                (ob.type == "MESH") and
                (context.mode == "OBJECT"))

    def execute(self, context):
        obj = context.active_object
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        twists = get_celtic_twists(bm)
        curve_obj = create_bezier(context, bm, twists,
                      self.crossing_angle,
                      self.crossing_strength,
                      self.handle_type,
                      self.weave_up,
                      self.weave_down)

        # If thick, then give it a bevel_object and convert to mesh
        if self.thickness > 0:
            create_pipe_from_bezier(context, curve_obj, self.thickness)
        return {'FINISHED'}

def menu_func(self, context):
    self.layout.operator(CelticKnotOperator.bl_idname,
                         text="Celtic Knot From Mesh",
                         icon='PLUGIN')

def register():
    bpy.utils.register_module(__name__)
    bpy.types.INFO_MT_curve_add.append(menu_func)


def unregister():
    bpy.types.INFO_MT_curve_add.remove(menu_func)
    bpy.utils.unregister_module(__name__)

if __name__ == "__main__":
    register()
