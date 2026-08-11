import bpy
import mathutils
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator, Panel

from .hooks import add_post_generate_callback, remove_post_generate_callback

import rigify
import pprint


def make_root_bone(armature, def_bones, export_collection):
    # find the bones that are parented to root
    root_childs = []
    for bone_name in def_bones:
        p_bone = armature.data.bones[bone_name]

        if p_bone.parent is not None and p_bone.parent.name == 'root':
            root_childs.append(bone_name)

    # create the new root bone
    bpy.ops.object.mode_set(mode='EDIT')
    root_bone = armature.data.edit_bones['root']
    def_root = armature.data.edit_bones.new('DEF-root')
    export_collection.assign(def_root)
    def_root.parent = None
    def_root.head = root_bone.head.copy()
    def_root.tail = def_root.head + mathutils.Vector((0.0, 0.0, 0.05))
    def_root.use_deform = False
    def_root_name = def_root.name

    # parent bones to the new root
    for bone_name in root_childs:
        armature.data.edit_bones[bone_name].use_connect = False
        armature.data.edit_bones[bone_name].parent = def_root

    # make new bone available as pose bone
    bpy.ops.object.mode_set(mode='OBJECT')

    # add modifiers to follow the Rigify root bone
    const = armature.pose.bones[def_root_name].constraints.new('COPY_SCALE')
    const.target = armature
    const.subtarget = 'root'
    const.owner_space = 'WORLD'
    const.target_space = 'WORLD'

    const = armature.pose.bones[def_root_name].constraints.new('COPY_LOCATION')
    const.target = armature
    const.subtarget = 'root'
    const.owner_space = 'WORLD'
    const.target_space = 'WORLD'

    # if configured this way it does what I need
    const = armature.pose.bones[def_root_name].constraints.new('TRANSFORM')
    const.target = armature
    const.subtarget = 'root'
    const.owner_space = 'POSE'
    const.target_space = 'POSE'
    const.map_from = const.map_to = 'ROTATION'
    const.to_max_x_rot = const.to_max_y_rot = const.to_max_z_rot = 180
    const.to_min_x_rot = const.to_min_y_rot = const.to_min_z_rot = -180
    const.from_max_x_rot = const.from_max_y_rot = const.from_max_z_rot = 180
    const.from_min_x_rot = const.from_min_y_rot = const.from_min_z_rot = -180


def reset_bbones(armature, bone_names):
    for bone_name in bone_names:
        bone = armature.data.bones.get(bone_name)
        if bone is not None:
            bone.bbone_segments = 1


def bone_names_from_rig(value):
    """
    Return a flat list of bone names.

    Rigify is inconsistent here: values may be
    - None
    - str
    - list
    - BoneDict (supports flatten())
    """
    if value is None:
        return []

    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        return value

    if hasattr(value, "flatten"):
        return value.flatten()

    raise TypeError(f"Unsupported bone container: {type(value)!r}")


def clear_stretch_to_constraint_rig(armature, rigs):
    for rig in rigs:
        bone_names_list = []

        bone_names_list += bone_names_from_rig(rig.bones.mch)
        bone_names_list += bone_names_from_rig(rig.bones.deform)
        bone_names_list += bone_names_from_rig(rig.bones.org)

        for bone_name in bone_names_list:
            if bone_name is None:
                continue

            bone_object = armature.pose.bones.get(bone_name)
            if not bone_object:
                print("missing bone " + bone_name)
                continue

            for constraint in bone_object.constraints:
                if constraint.type == 'STRETCH_TO':
                    constraint.enabled = False

                    # Replace with damped track which doesn't stretch
                    tracking = bone_object.constraints.new('DAMPED_TRACK')
                    tracking.target = armature
                    tracking.subtarget = constraint.subtarget


def clear_ik_stretch_rig(armature, rigs):
    for rig in rigs:
        if not rig.bones.ctrl:
            continue
        
        bone_names_list = []
        bone_names_list += bone_names_from_rig(rig.bones.ctrl)
        bone_names_list += bone_names_from_rig(rig.bones.mch)

        for bone_name in bone_names_list:
            if bone_name is None:
                continue

            bone_object = armature.pose.bones.get(bone_name)
            if not bone_object:
                print("missing bone " + bone_name)
                continue

            bone_object.ik_stretch = 0


def reparent_base_deform(rig, armature):
    deform_name = "DEF-" + rig.base_bone.removeprefix('ORG-')
    defbone = armature.data.edit_bones.get(deform_name)
    orgbone = armature.data.edit_bones.get(rig.base_bone)
    orgparent = orgbone.parent

    if defbone is not None and orgparent is not None:
        defparent_name = "DEF-" + orgparent.name.removeprefix('ORG-')
        defparent = armature.data.edit_bones.get(defparent_name)
        if defparent is not None:
            old_parent = defbone.parent
            defbone.parent = defparent
            # print(
            #     f"Bone: {defbone.name}, old parent {old_parent.name}, new {defparent.name}")
            return (defbone.name, old_parent.name)


def pose_bone_has_transform_driver(armature, bone_name):
    """Return True if the pose bone has drivers on any transform channel."""

    ad = armature.animation_data
    if ad is None or ad.drivers is None:
        return False

    prefix = f'pose.bones["{bone_name}"].'

    transform_paths = {
        prefix + "location",
        prefix + "rotation_euler",
        prefix + "rotation_quaternion",
        prefix + "rotation_axis_angle",
        prefix + "scale",
    }

    for fcurve in ad.drivers:
        path = fcurve.data_path

        # Drivers may target the whole array or a single component.
        if path in transform_paths:
            return True

    return False


def add_reparent_constraints(armature, affected_bones):
    """
    affected_bones: iterable of (DEF bone name, ORG bone name)
    """

    for def_name, org_name in affected_bones:
        pbone = armature.pose.bones.get(def_name)
        if pbone is None:
            continue

        # Skip bones whose transforms are driven.
        if pose_bone_has_transform_driver(armature, def_name):
            continue

        # Already constrained?
        if any(c.type in {'COPY_LOCATION', 'COPY_TRANSFORMS'}
               for c in pbone.constraints):
            continue

        con = pbone.constraints.new('COPY_TRANSFORMS')
        con.name = "Rigify Previous Parent"
        con.target = armature
        con.subtarget = org_name
        
        # (questionable fix)
        con.owner_space = 'LOCAL'
        con.target_space = 'LOCAL'

        # Move to top of constraint stack
        while pbone.constraints[0] != con:
            pbone.constraints.move(
                pbone.constraints.find(con.name),0)
            

def rig_special_handling(armature, rigs):
    base_limb_rig = rigify.rigs.limbs.limb_rigs.BaseLimbRig

    for rig in rigs:
        if not isinstance(rig, base_limb_rig):
            continue

        if not hasattr(rig, 'segments') or rig.segments != 1:
            continue

        org_name = rig.base_bone
        deform_name = "DEF-" + org_name.removeprefix("ORG-")

        bone = armature.pose.bones.get(deform_name)
        if bone is None:
            continue

        # Find COPY_TRANSFORMS.
        transform_index = next(
            (
                index
                for index, constraint in enumerate(bone.constraints)
                if constraint.type == 'COPY_TRANSFORMS'
            ),
            -1
        )

        # Add rotation copy for ORG bone.
        # Purpose: rotation in FK mode.
        rt_const = bone.constraints.new('COPY_ROTATION')
        rt_const.name = "Rigify FK Rotation"
        rt_const.target = armature
        rt_const.subtarget = org_name
        rt_const.owner_space = 'WORLD'
        rt_const.target_space = 'WORLD'

        # Put COPY_ROTATION directly behind COPY_TRANSFORMS.
        if transform_index != -1:
            rotation_index = bone.constraints.find(rt_const.name)
            bone.constraints.move(rotation_index, transform_index + 1)


def is_rigify_metarig(obj):
    if not obj or obj.type != 'ARMATURE':
        return False
    # Rigify-specific custom property found on generated rig
    ret = "rigify_rig_ui" in obj.data
    return ret


class RIGIFY_PT_kr_postprocess(Panel):
    """Panel in Armature Data properties for KR-Postprocess."""
    bl_label = "kr Postprocess"
    bl_idname = "RIGIFY_PT_kr_postprocess"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"  # Armature Data tab

    @classmethod
    def poll(cls, context):
        return is_rigify_metarig(context.object)

    def draw(self, context):
        layout = self.layout
        obj = context.object
        arm = obj.data
        
        layout.prop(arm, "kr_enable_pp")
        layout.prop(arm, "kr_extra_root_bone")
        layout.prop(arm, "kr_process_group_name")


def add_kr_properties(metarig):
    add_root_bone = metarig.data.get("kr_extra_root_bone")
    if add_root_bone is None:
        metarig.data["kr_extra_root_bone"] = False

    process_group = metarig.data.get("kr_process_group_name")
    if process_group is None:
        metarig.data["kr_process_group_name"] = "Export"

    enable_pp = metarig.data.get("kr_enable_pp")
    if enable_pp is None:
        metarig.data["kr_enable_pp"] = False


def handle_post_generate(generator):
    metarig = generator.metarig
    generated_armature = generator.obj

    # add properties
    add_kr_properties(metarig)

    add_root_bone = metarig.data.get("kr_extra_root_bone")
    process_group = metarig.data.get("kr_process_group_name")
    enable_pp = metarig.data.get("kr_enable_pp")

    if enable_pp and process_group != '':
        # actual postprocessing
        export_collection = generated_armature.data.collections.get(
            metarig.data["kr_process_group_name"])
        if not export_collection:
            print("Error: postprocess group not found!")
            return

        # find the rigs we need to process: if they are in "kr_process_group_name"
        # !! on the metarig !!
        export_rigs = set()
        export_bones = set()

        for rig in rigify.get_generator().rig_list:
            for bname in rig.rigify_org_bones:
                stripped = bname.removeprefix('ORG-')
                metarig_bone_object = metarig.data.bones.get(stripped)
                if not metarig_bone_object:
                    print("PP internal error " + stripped)
                    continue

                # heel
                if not generated_armature.data.bones.get("DEF-" + stripped):
                    continue

                if export_collection.name in metarig_bone_object.collections:
                    export_rigs.add(rig)
                    export_bones.add("DEF-" + stripped)

        # add additionally generated deform bones
        for rigify_rig in export_rigs:
            initial_bone_names = []
            for bname in rigify_rig.rigify_org_bones:
                initial_bone_names.append(bname.removeprefix('ORG-'))

            rig_deform = bone_names_from_rig(rigify_rig.bones.deform)

            for bname in rig_deform:
                if not bname.removeprefix('DEF-') in initial_bone_names:
                    export_bones.add(bname)

        # remove all remaining bones from the the group on the generated rig
        for bone_object in generated_armature.data.bones:
            if bone_object.name in export_collection.bones:
                export_collection.unassign(bone_object)

        # add the deform bones to the group
        for bone_name in export_bones:
            bone_object = generated_armature.data.bones.get(bone_name)
            export_collection.assign(bone_object)

        # root bone
        if add_root_bone:
            make_root_bone(generated_armature, export_bones, export_collection)

        # bbones
        reset_bbones(generated_armature, export_bones)

        # stretch
        clear_stretch_to_constraint_rig(generated_armature, export_rigs)
        clear_ik_stretch_rig(generated_armature, export_rigs)

        # change to DEF chain
        reparented_bones = []

        bpy.ops.object.mode_set(mode='EDIT')
        for rigify_rig in export_rigs:
            result = reparent_base_deform(rigify_rig, generated_armature)
            if result is not None:
                reparented_bones.append(result)
        bpy.ops.object.mode_set(mode='OBJECT')

        # constraint for sole ORG parent movement
        add_reparent_constraints(generated_armature, reparented_bones)
        
        # rigify rig-specific
        rig_special_handling(generated_armature, export_rigs)


classes = (
    RIGIFY_PT_kr_postprocess,

)


def register():
    bpy.types.Armature.kr_extra_root_bone = BoolProperty(
        name="Root Bone",
        description="Add an upward pointing deform root bone.",
        default=True)
    bpy.types.Armature.kr_enable_pp = BoolProperty(
        name="Enable kr postprocessing",
        description="Prepare the Rigify rig for export.",
        default=False)
    bpy.types.Armature.kr_process_group_name = StringProperty(
        name="Group",
        description="Name of the bone group that contains bones where deform should be exported.",
        default="Export")

    for cls in (classes):
        bpy.utils.register_class(cls)

    add_post_generate_callback(handle_post_generate)


def unregister():
    remove_post_generate_callback(handle_post_generate)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    if hasattr(bpy.types.Armature, "kr_extra_root_bone"):
        del bpy.types.Armature.kr_extra_root_bone
