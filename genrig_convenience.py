import bpy

from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator, Panel

from .hooks import add_post_generate_callback, remove_post_generate_callback

# ------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------

STATE_PROP_ROOT = "k_convenience_state"
STATE_PROP_COLL = "ARM_COLLECTIONS"
STATE_PROP_WP = "WP"
KEEP_CONSTRAINT_KEYWORD_DEFAULT = "[KEEP]"


def is_rigify_rig(obj):
    """Heuristic detection of a generated Rigify rig."""
    if not obj or obj.type != 'ARMATURE':
        return False
    # Rigify-specific custom property found on generated rig
    return "rig_id" in obj.data


def get_create_wp_state_container(arm_data, create=False):
    if create and STATE_PROP_ROOT not in arm_data:
        arm_data[STATE_PROP_ROOT] = {}
        
    if create and STATE_PROP_WP not in arm_data[STATE_PROP_ROOT]:
        arm_data[STATE_PROP_ROOT][STATE_PROP_WP] = {}
        
    state = arm_data.get(STATE_PROP_ROOT)
    if not state:
        return None
    return state.get(STATE_PROP_WP)


def get_create_collections_state_container(arm_data, create=False):
    if create and STATE_PROP_ROOT not in arm_data:
        arm_data[STATE_PROP_ROOT] = {}
        
    if create and STATE_PROP_COLL not in arm_data[STATE_PROP_ROOT]:
        arm_data[STATE_PROP_ROOT][STATE_PROP_COLL] = {}
    
    state = arm_data.get(STATE_PROP_ROOT)
    if not state:
        return None
    return state.get(STATE_PROP_COLL)


def get_wp_mode_flag(arm_data):
    """Return True/False without creating the property."""
    state = get_create_wp_state_container(arm_data)
    return bool(state.get("wp_mode_active", False)) if state else False


def set_wp_mode_flag(state, value: bool):
    state["wp_mode_active"] = bool(value)


def get_keep_keyword(context):
    """You could later expose this as a user preference; for now, fixed or scene-level."""
    # For now, just use a fixed keyword. You can extend this to preferences.
    return KEEP_CONSTRAINT_KEYWORD_DEFAULT


def iter_deform_pose_bones(obj):
    """Yield pose bones that are deform bones (use_deform=True on the edit bone)."""
    arm = obj.data
    for pb in obj.pose.bones:
        eb = arm.bones.get(pb.name)
        if eb and eb.use_deform:
            yield pb


def find_deform_bone_collections(obj):
    """Find bone collections that contain deform bones."""
    arm = obj.data
    deform_collections = []

    # Map bone -> collections
    for bcoll in arm.collections:
        if bcoll.name == 'DEF':
            deform_collections.append(bcoll)
            break

    return deform_collections


def store_bone_collection_state(obj):
    """Store visibility/solo state of all bone collections."""
    state = {}
    
    deform_bcolls = find_deform_bone_collections(obj)
    
    for bcoll in deform_bcolls:
        state[bcoll.name] = {
            "is_visible": bcoll.is_visible,
            "is_solo": bcoll.is_solo,
        }
    return state


def restore_bone_collection_state(state, arm_data):
    """Restore visibility/solo state of bone collections."""
    bcoll_state = state.get("bone_collections")
    if bcoll_state:
        for coll_name, coll_data in bcoll_state.items():
            collection = arm_data.collections.get(coll_name)
            if collection:
                collection.is_visible = coll_data["is_visible"]
                collection.is_solo = coll_data["is_solo"]
            

def reset_deform_bone_transforms(obj):
    """Reset location, rotation, and scale of all deform pose bones."""
    for pb in iter_deform_pose_bones(obj):

        # Reset location
        pb.location = (0.0, 0.0, 0.0)

        # Reset rotation depending on mode
        if pb.rotation_mode == 'QUATERNION':
            pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)

        elif pb.rotation_mode == 'AXIS_ANGLE':
            # Axis-angle: (angle, axis_x, axis_y, axis_z)
            pb.rotation_axis_angle = (0.0, 0.0, 1.0, 0.0)

        else:
            # Euler modes
            pb.rotation_euler = (0.0, 0.0, 0.0)

        # Reset scale
        pb.scale = (1.0, 1.0, 1.0)


def solo_deform_collections(state, obj):
    """Solo deform bone collections and store previous state."""
    arm = obj.data
    state["bone_collections"] = store_bone_collection_state(obj)

    deform_bcolls = find_deform_bone_collections(obj)

    if not deform_bcolls:
        # Fallback: if no explicit deform collections, just leave as-is.
        return

    # Solo deform collections: set them visible+solo, others not solo.
    for bcoll in arm.collections:
        if bcoll in deform_bcolls:
            bcoll.is_visible = True
            bcoll.is_solo = True


def get_rotation_locks(pb):
    """Return a dict of rotation locks depending on rotation mode."""
    mode = pb.rotation_mode

    if mode in ['QUATERNION', 'AXIS_ANGLE']:
        return {
            "mode": mode,
            "lock_rot_w": pb.lock_rotation_w,
            "lock_rot_axis":pb.lock_rotation,
        }
    else:  # Euler modes
        return {
            "mode": mode,
            "lock_rotation": pb.lock_rotation,
        }
        

def set_rotation_locks(pb, data):
    """Restore rotation locks based on stored data."""
    mode = data.get("mode")

    if mode in ['QUATERNION', 'AXIS_ANGLE']:
        pb.lock_rotation_w = data.get("lock_rot_w", False)
        axis = data.get("lock_rot_axis", [False, False, False])
        pb.lock_rotation = axis

    else:  # Euler
        locks = data.get("lock_rotation", [False, False, False])
        pb.lock_rotation = locks


def store_pose_bone_state(state, obj):
    locks_state = {}
    constraints_state = {}

    for pb in iter_deform_pose_bones(obj):

        # Store transform locks
        locks_state[pb.name] = {
            "lock_location": list(pb.lock_location),
            "lock_scale": list(pb.lock_scale),
            "rotation": get_rotation_locks(pb),
        }

        # Store constraints (IDProperty-safe)
        c_dict = {}
        for c in pb.constraints:
            c_dict[c.name] = c.mute
        constraints_state[pb.name] = c_dict

    state["locks"] = locks_state
    state["constraints"] = constraints_state


def restore_pose_bone_state(state, obj):
    locks_state = state.get("locks", {})
    constraints_state = state.get("constraints", {})

    for pb in iter_deform_pose_bones(obj):

        # Restore location & scale locks
        l_state = locks_state.get(pb.name)
        if l_state:
            pb.lock_location = l_state.get(
                "lock_location", (False, False, False))
            pb.lock_scale = l_state.get("lock_scale", (False, False, False))

            # Restore rotation locks
            rot_data = l_state.get("rotation")
            if rot_data:
                set_rotation_locks(pb, rot_data)

        # Restore constraints
        c_state = constraints_state.get(pb.name, {})
        for c_name, mute_val in c_state.items():
            c = pb.constraints.get(c_name)
            if c:
                c.mute = mute_val


def unlock_and_disable_constraints(obj, keep_keyword):
    """Unlock transforms and mute constraints on deform bones, except those with keep_keyword."""
    for pb in iter_deform_pose_bones(obj):
        # Unlock transforms
        pb.lock_location = (False, False, False)
        pb.lock_rotation = (False, False, False)
        pb.lock_rotation_w = False
        pb.lock_scale = (False, False, False)

        # Mute constraints except those with keep_keyword in name
        for c in pb.constraints:
            if keep_keyword and keep_keyword in c.name:
                continue
            c.mute = True


# ------------------------------------------------------------------------
# Operator
# ------------------------------------------------------------------------

class RIGIFY_OT_toggle_weight_paint_mode(Operator):
    """Toggle Rigify Weight Paint Mode"""
    bl_idname = "rigify.toggle_weight_paint_mode"
    bl_label = "Toggle Weight Paint Mode"
    bl_options = {'REGISTER', 'UNDO'}

    keep_keyword: StringProperty(
        name="Keep Constraint Keyword",
        description="Constraints containing this keyword in their name will NOT be disabled",
        default=KEEP_CONSTRAINT_KEYWORD_DEFAULT,
    )

    def execute(self, context):
        obj = context.object
        if not is_rigify_rig(obj):
            self.report(
                {'ERROR'}, "Active object does not look like a generated Rigify rig.")
            return {'CANCELLED'}

        arm = obj.data
        
        state = get_create_wp_state_container(
            arm, create=False)
        
        wp_active = get_wp_mode_flag(arm) if state else False

        # We need to operate in Pose mode for locks/constraints, but user may be in Weight Paint.
        prev_mode = obj.mode
        if prev_mode not in {'POSE', 'OBJECT'}:
            # Switch to Pose mode safely
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.mode_set(mode='POSE')

        if not wp_active:
            # ENTER weight paint mode
            # 0) get the data storage
            if not state:
                state = get_create_wp_state_container(
                    arm, create=True)
            
            # 1) Store state
            solo_deform_collections(state, obj)
            store_pose_bone_state(state, obj)

            # 2) Unlock and disable constraints
            keep_kw = self.keep_keyword
            unlock_and_disable_constraints(obj, keep_kw)

            # 3) Mark active
            set_wp_mode_flag(state, True)
        else:
            # EXIT weight paint mode
            if not state:
                self.report({'ERROR'}, "RIGIFY_OT_toggle_weight_paint_mode: Internal error")
                return {'CANCELLED'}

            # 1) Restore bone collections
            restore_bone_collection_state(state, arm)

            # 2) Restore pose bone locks and constraints
            restore_pose_bone_state(state, obj)
            
            # 3) Reset transforms of deform bones
            reset_deform_bone_transforms(obj)
            
            # 4) Clear old data and active flag
            state.clear()
            # set_wp_mode_flag(arm, False)

        # Return to previous mode if possible
        try:
            bpy.ops.object.mode_set(mode=prev_mode)
        except Exception:
            # If that fails, just stay where we are.
            pass

        return {'FINISHED'}
    

def store_unhidden_collections(arm_data, collections):
    """Store the names of collections we unhid so we can hide them again later."""
    state = get_create_collections_state_container(arm_data, True)

    state[STATE_PROP_COLL] = [
        c.name for c in collections]
    

def resolve_layer_collection(collection, context):
    ''' Returns only the first it finds '''
    def recursion(l_coll, result=None):
        for coll in l_coll.children:
            if coll.collection == collection:
                return coll
            result = recursion(coll, result)
        return result

    return recursion(context.view_layer.layer_collection)


class RIGIFY_OT_open_wgt_mesh(Operator):
    """Open the widget mesh of the active pose bone in Edit Mode"""
    bl_idname = "rigify.open_wgt_mesh"
    bl_label = "Edit Bone Widget"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not obj or obj.type != 'ARMATURE':
            return False
        if obj.mode != 'POSE':
            return False
        if not is_rigify_rig(obj):
            return False

        # Weight paint mode must NOT be active
        if get_wp_mode_flag(obj.data):
            return False

        pb = context.active_pose_bone
        if not pb:
            return False

        # Must have a custom widget assigned
        return pb.custom_shape is not None

    def execute(self, context):
        rig = context.object
        pb = context.active_pose_bone

        wgt_obj = pb.custom_shape
        if not wgt_obj:
            self.report({'ERROR'}, "This bone has no custom widget assigned.")
            return {'CANCELLED'}

        # Unhide all collections containing this widget
        unhidden = []
        for coll in wgt_obj.users_collection:
            layer = resolve_layer_collection(coll, context)
            if layer:
                layer.exclude = False
            coll.hide_viewport = False
            coll.hide_select = False
            unhidden.append(coll)
            
        # Remember them
        store_unhidden_collections(rig.data, unhidden)

        # Switch to object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Make widget object active
        context.view_layer.objects.active = wgt_obj
        for o in context.selected_objects:
            o.select_set(False)
        wgt_obj.select_set(True)

        # Enter edit mode
        try:
            bpy.ops.object.mode_set(mode='EDIT')
        except RuntimeError:
            self.report({'ERROR'}, "Failed to enter edit mode on widget mesh.")
            return {'CANCELLED'}

        return {'FINISHED'}
    

class RIGIFY_OT_hide_wgt_collections(Operator):
    """Re-hide WGTS collections previously unhidden"""
    bl_idname = "rigify.hide_wgt_collections"
    bl_label = "Hide Widget Collections"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.object
        if not is_rigify_rig(obj):
            return False
        
        state = get_create_collections_state_container(obj.data)
        return state and bool(state.get(STATE_PROP_COLL))


    def execute(self, context):
        rig = context.object
        arm_data = rig.data
        
        state = get_create_collections_state_container(arm_data)
        
        if not state or not bool(state.get(STATE_PROP_COLL, [])):
            self.report({'WARNING'}, "No collections to hide.")
            return {'CANCELLED'}

        coll_names = state.get(STATE_PROP_COLL, [])

        for name in coll_names:
            coll = bpy.data.collections.get(name)
            if coll:
                layer = resolve_layer_collection(coll, context)
                if layer:
                    layer.exclude = True


        # Clear the record
        state[STATE_PROP_COLL] = []

        self.report({'INFO'}, "Widget collections hidden.")
        return {'FINISHED'}

# Generation Callbacks
HIDE_METARIG_PROPNAME = "kr_hide_metarig"

def handle_post_generate(generator):
    hide_metarig = generator.obj.data.kr_hide_metarig

    if hide_metarig:
        generator.metarig.hide_set(True)
            
    state = get_create_wp_state_container(generator.obj.data)
    if state:
        state.clear()


def find_metarig_referencing_rig_data(generated_rig):
    """Return the first Object that uses this Armature datablock."""
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and obj.data.rigify_target_rig and obj.data.rigify_target_rig == generated_rig:
            return obj
    return None


class RIGIFY_OT_edit_metarig(bpy.types.Operator):
    """Switch to the metarig and enter Edit Mode"""
    bl_idname = "rigify.edit_metarig"
    bl_label = "Edit Metarig"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return is_rigify_rig(context.object)


    def execute(self, context):
        generated_rig = context.object
        
        # generated rig is selected, it is referenced by the
        # metarig data block custom property 'rigify_target_rig.
        metarig = find_metarig_referencing_rig_data(generated_rig)
        
        if not metarig:
            self.report({'ERROR'}, "Metarig not found.")
            return {'CANCELLED'}

        # Switch to object mode
        bpy.ops.object.mode_set(mode='OBJECT')

        # Make metarig active
        metarig.hide_set(False)
        context.view_layer.objects.active = metarig
        for o in context.selected_objects:
            o.select_set(False)
        metarig.select_set(True)

        # Enter edit mode
        bpy.ops.object.mode_set(mode='EDIT')
        return {'FINISHED'}


# ------------------------------------------------------------------------
# Panel
# ------------------------------------------------------------------------

class RIGIFY_PT_k_convenience(Panel):
    """Panel in Armature Data properties for Rigify Weight Paint Mode."""
    bl_label = "kr Convenience Tools"
    bl_idname = "RIGIFY_PT_k_convenience_tools"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "data"  # Armature Data tab

    @classmethod
    def poll(cls, context):
        return is_rigify_rig(context.object)

    def draw(self, context):
        layout = self.layout
        obj = context.object
        arm = obj.data

        wp_active = get_wp_mode_flag(arm)
            
        row = layout.row()
        if wp_active:
            row.operator(
                RIGIFY_OT_toggle_weight_paint_mode.bl_idname,
                text="Exit Weight Paint Mode",
                icon='MOD_VERTEX_WEIGHT'
            ).keep_keyword = KEEP_CONSTRAINT_KEYWORD_DEFAULT
        else:
            row.operator(
                RIGIFY_OT_toggle_weight_paint_mode.bl_idname,
                text="Enter Weight Paint Mode",
                icon='MOD_VERTEX_WEIGHT'
            ).keep_keyword = KEEP_CONSTRAINT_KEYWORD_DEFAULT

        row = layout.row()
        row.label(text="Constraint Keep Keyword:")
        row.label(text=KEEP_CONSTRAINT_KEYWORD_DEFAULT, icon='FILTER')
        
        if (
            obj.mode == 'POSE'
            and not wp_active
            and context.active_pose_bone
            and context.active_pose_bone.custom_shape
        ):
            layout.operator("rigify.open_wgt_mesh", icon='MESH_CUBE')
        
        state = get_create_collections_state_container(arm)

        if state and state.get(STATE_PROP_COLL):
            layout.operator("rigify.hide_wgt_collections", icon='HIDE_OFF')
            
        layout.operator("rigify.edit_metarig", icon='ARMATURE_DATA')

        layout.prop(arm, "kr_hide_metarig",
                     text="Hide Metarig After Generation")



classes = (
    RIGIFY_OT_toggle_weight_paint_mode,
    RIGIFY_OT_open_wgt_mesh,
    RIGIFY_PT_k_convenience,
    RIGIFY_OT_hide_wgt_collections,
    RIGIFY_OT_edit_metarig
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    add_post_generate_callback(handle_post_generate)
    
    bpy.types.Armature.kr_hide_metarig = BoolProperty(
        name="Hide Metarig",
        description="Hide Metarig After Generation",
        default=False)

# not used
def unregister():
    if hasattr(bpy.types.Armature, HIDE_METARIG_PROPNAME):
        del bpy.types.Armature.kr_hide_metarig
    
    remove_post_generate_callback(handle_post_generate)
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

